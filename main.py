"""
API Backend para integración con dLocal Go
Procesa pagos, recibe webhooks y envía notificaciones
"""
from pathlib import Path

import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from datetime import datetime
from typing import Optional
import logging

from config import settings
from models import (
    PaymentRequest,
    PaymentResponse,
    WebhookNotification,
    HealthResponse,
    UpsellRequest,
    UpsellResponse,
)
from services.dlocal_service import dlocal_service
from services.webhook_service import webhook_service
from services.meta_pixel_service import meta_pixel_service
from services.upsell_cache import upsell_cache
from services.ab_test_stats import ab_test_stats

# Templates Jinja2 para servir HTML (página de upsell, etc.)
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Configurar logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="dLocal Go Payment API",
    description="API backend para procesar pagos con dLocal Go",
    version="1.0.0"
)


def _normalize_payment_type(raw_type: str) -> str:
    """Normaliza el parámetro `type` de la URL al payment_type interno.

    Acepta sinónimos para los planes vigentes de Mentoría León:
    - plan6 / 6 / 6cuotas / 117             -> "plan6" (6 cuotas de USD 117)
    - plan9 / 9 / 9cuotas / 87              -> "plan9" (9 cuotas de USD 87)
    - contado / single / unico / 597        -> "contado" (USD 597 pago único)
    Por defecto devuelve "plan6".
    """
    value = (raw_type or "").lower().strip()
    if value in ("plan9", "9", "9cuotas", "87"):
        return "plan9"
    if value in ("contado", "single", "unico", "único", "597"):
        return "contado"
    return "plan6"


@app.get("/", tags=["Health"])
async def root():
    """Endpoint raíz"""
    return {
        "message": "dLocal Go Payment API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint para verificar que la API está funcionando
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


@app.post("/debug/test-webhook", tags=["Debug"])
async def test_webhook_manually(payment_id: str, status: str = "REJECTED"):
    """
    Endpoint para probar manualmente el procesamiento de webhooks
    Simula que dLocal envió un webhook de pago rechazado
    """
    logger.info(f"🧪 TEST: Simulating webhook for payment {payment_id} with status {status}")
    
    # Simular el body que enviaría dLocal
    fake_body = {
        "payment_id": payment_id,
        "status": status,
        "status_detail": "Test rejection",
        "amount": 702.0,  # Monto de testing por defecto (Mentoría León - plan6)
        "currency": "USD",
        "country": "AR"
    }
    
    # Crear un request falso
    from fastapi import Request
    class FakeRequest:
        async def json(self):
            return fake_body
    
    fake_request = FakeRequest()
    
    # Llamar al webhook handler
    try:
        result = await dlocal_webhook(fake_request)
        return {"message": "Test webhook processed", "result": result}
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug/payment-data", tags=["Debug"])
async def debug_payment_data(tel: str, country: str, type: str):
    """
    Endpoint de debug para ver exactamente qué datos se enviarían a dLocal
    sin crear el pago realmente
    """
    import uuid
    
    phone_number = tel if tel.startswith('+') else f'+{tel}'
    payment_type = _normalize_payment_type(type)
    
    # Calcular lo mismo que en el servicio (Mentoría León)
    if payment_type == "plan9":
        amount = 783.00
        max_installments = 9
        installment_amount = 87.00
        description = f"{settings.payment_description} - 9 cuotas de USD 87"
    elif payment_type == "contado":
        amount = 597.00
        max_installments = 1
        installment_amount = 597.00
        description = f"{settings.payment_description} - Pago de contado"
    else:  # plan6
        amount = 702.00
        max_installments = 6
        installment_amount = 117.00
        description = f"{settings.payment_description} - 6 cuotas de USD 117"
    
    order_id = f"order_{uuid.uuid4().hex[:16]}"
    
    # Construir el mismo payload
    payment_data = {
        "amount": amount,
        "currency": "USD",
        "country": country.upper(),
        "payment_method_flow": "REDIRECT",
        "payer": {
            "phone": phone_number
        },
        "order_id": order_id,
        "name": settings.merchant_name,
        "description": description,
        "notification_url": f"{settings.app_base_url}/api/webhook/dlocal",
    }
    if max_installments > 1:
        payment_data["max_installments"] = max_installments
    
    # URLs de retorno opcionales: solo se incluyen si están seteadas
    optional_redirect_urls = {
        "success_url": settings.dlocal_success_url,
        "error_url": settings.dlocal_error_url,
        "pending_url": settings.dlocal_pending_url,
        "cancel_url": settings.dlocal_cancel_url,
    }
    for key, value in optional_redirect_urls.items():
        if value:
            payment_data[key] = value
    
    return {
        "message": "Esto es lo que se enviaría a dLocal",
        "payment_type": payment_type,
        "installments_info": {
            "max_installments": max_installments,
            "amount_per_installment": installment_amount,
            "total_amount": amount
        },
        "full_payload": payment_data
    }


@app.get("/api/pago", response_model=PaymentResponse, tags=["Payments"])
async def create_payment_get(
    tel: str = None,
    country: str = "MX",
    type: str = "plan6",
    name: str = None,
    email: str = None,
    force_ab: Optional[str] = None,
):
    """
    Crea un link de pago en dLocal y devuelve JSON con los datos
    
    Parámetros URL (TODOS OPCIONALES):
    - **tel**: Número de teléfono con código de país (ej: 5255123456789). Si no se envía, el usuario completa sus datos
    - **country**: Código del país (AR, MX, CO, CL, etc.). Por defecto: MX
    - **type**: Plan de pago de Mentoría León. Las cuotas aplican solo si el cliente
      paga con tarjeta de crédito; otros métodos cobran el total de una sola vez.
        - "plan6" / "6" / "6cuotas": 6 cuotas de USD 117 — total USD 702 (DEFAULT)
        - "plan9" / "9" / "9cuotas": 9 cuotas de USD 87  — total USD 783
        - "contado" / "single" / "597": Pago único de USD 597
    - **name**: Nombre del cliente (opcional)
    - **email**: Email del cliente (opcional)
    
    Ejemplos:
    - /api/pago?tel=5255123456789&country=MX&type=plan6  → Teléfono precargado, 6 cuotas
    - /api/pago?country=AR&type=plan9                    → Sin teléfono, 9 cuotas
    - /api/pago?type=contado                             → Pago único USD 597
    - /api/pago                                          → Checkout limpio, plan6, país MX

    Param de testing (solo si UPSELL_AB_FORCE_ENABLED=true en .env):
    - **force_ab**: "A" o "B" — fuerza la variante de A/B test del upsell para
      esta compra (útil para hacer QA controlado: 1 compra por variante).
    """
    try:
        # Normalizar el teléfono (solo si se proporciona)
        phone_number = None
        if tel:
            phone_number = tel if tel.startswith('+') else f'+{tel}'
        
        # Normalizar el tipo de pago
        payment_type = _normalize_payment_type(type)
        
        logger.info(
            f"Creating payment via GET - Country: {country}, "
            f"Type: {payment_type}, Phone: {phone_number or 'Not provided'}, "
            f"force_ab={force_ab or '-'}"
        )
        
        # Crear el pago en dLocal
        payment_response = await dlocal_service.create_payment(
            phone_number=phone_number,
            country=country.upper(),
            payment_type=payment_type,
            customer_name=name,
            customer_email=email,
            force_ab_variant=force_ab,
        )
        
        logger.info(f"Payment created successfully: {payment_response.payment_id}")
        
        return payment_response
        
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment: {str(e)}"
        )


@app.get("/pagar", tags=["Payments"])
async def redirect_to_checkout(
    tel: str = None,
    country: str = "MX",
    type: str = "plan6",
    name: str = None,
    email: str = None,
    force_ab: Optional[str] = None,
):
    """
    Crea un pago y REDIRIGE automáticamente al checkout de dLocal
    
    Parámetros URL (TODOS OPCIONALES):
    - **tel**: Número de teléfono con código de país (ej: 5255123456789). Si no se envía, el usuario completa sus datos
    - **country**: Código del país (AR, MX, CO, CL, etc.). Por defecto: MX
    - **type**: Plan de pago de Mentoría León. Las cuotas aplican solo si el cliente
      paga con tarjeta de crédito; otros métodos cobran el total de una sola vez.
        - "plan6" / "6" / "6cuotas": 6 cuotas de USD 117 — total USD 702 (DEFAULT)
        - "plan9" / "9" / "9cuotas": 9 cuotas de USD 87  — total USD 783
        - "contado" / "single" / "597": Pago único de USD 597
    - **name**: Nombre del cliente (opcional)
    - **email**: Email del cliente (opcional)
    
    Ejemplos:
    - /pagar?tel=5255123456789&country=MX&type=plan6  → Teléfono precargado, 6 cuotas
    - /pagar?country=AR&type=plan9                    → Sin teléfono, 9 cuotas
    - /pagar?type=contado                             → Pago único USD 597
    - /pagar                                          → Checkout limpio, plan6, país MX

    Param de testing (solo si UPSELL_AB_FORCE_ENABLED=true en .env):
    - **force_ab**: "A" o "B" — fuerza la variante de A/B test del upsell para
      esta compra (útil para hacer QA controlado: 1 compra por variante).
    """
    from fastapi.responses import RedirectResponse
    
    try:
        # Normalizar el teléfono (solo si se proporciona)
        phone_number = None
        if tel:
            phone_number = tel if tel.startswith('+') else f'+{tel}'
        
        # Normalizar el tipo de pago
        payment_type = _normalize_payment_type(type)
        
        logger.info(
            f"Creating payment with redirect - Country: {country}, "
            f"Type: {payment_type}, Phone: {phone_number or 'Not provided'}, "
            f"force_ab={force_ab or '-'}"
        )
        
        # Crear el pago en dLocal
        payment_response = await dlocal_service.create_payment(
            phone_number=phone_number,
            country=country.upper(),
            payment_type=payment_type,
            customer_name=name,
            customer_email=email,
            force_ab_variant=force_ab,
        )
        
        logger.info(f"Payment created, redirecting to checkout: {payment_response.payment_id}")
        
        # Redirigir al checkout de dLocal
        return RedirectResponse(url=payment_response.redirect_url)
        
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment: {str(e)}"
        )


@app.post("/api/create-payment", response_model=PaymentResponse, tags=["Payments"])
async def create_payment_post(payment_request: PaymentRequest):
    """
    Crea un link de pago en dLocal usando POST con JSON body
    
    - **phone_number**: Número de teléfono del cliente
    - **country**: Código ISO del país (2 letras, ej: BR, MX, AR)
    - **payment_type**: Plan de pago de Mentoría León (cuotas solo en tarjeta de crédito)
        - "plan6": 6 cuotas de USD 117 — total USD 702
        - "plan9": 9 cuotas de USD 87  — total USD 783
        - "contado": Pago único de USD 597
    - **customer_name**: Nombre del cliente (opcional)
    - **customer_email**: Email del cliente (opcional)
    
    Retorna el link de pago para redirigir al cliente
    """
    try:
        logger.info(
            f"Creating payment - Country: {payment_request.country}, "
            f"Type: {payment_request.payment_type}, Phone: {payment_request.phone_number}"
        )
        
        # Crear el pago en dLocal
        payment_response = await dlocal_service.create_payment(
            phone_number=payment_request.phone_number,
            country=payment_request.country,
            payment_type=payment_request.payment_type,
            customer_name=payment_request.customer_name,
            customer_email=payment_request.customer_email
        )
        
        logger.info(f"Payment created successfully: {payment_response.payment_id}")
        
        return payment_response
        
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment: {str(e)}"
        )


@app.post("/api/webhook/dlocal", tags=["Webhooks"])
async def dlocal_webhook(request: Request):
    """
    Webhook para recibir notificaciones de dLocal Go sobre cambios en el estado de los pagos
    
    Cuando un pago cambia de estado, dLocal Go envía una notificación a este endpoint.
    
    Proceso:
    1. Obtiene los detalles completos del pago desde dLocal Go
    2. Envía los datos completos al webhook de terceros (AutomatiChat)
    3. Loguea el estado final del pago
    """
    logger.info("="*80)
    logger.info("🔔 WEBHOOK RECEIVED FROM DLOCAL")
    logger.info("="*80)
    try:
        # Obtener el body del request
        body = await request.json()
        
        # Extraer payment_id (puede venir como 'payment_id' o 'id')
        payment_id = body.get("payment_id") or body.get("id")
        status = body.get("status", "UNKNOWN")
        
        logger.info(f"Webhook received from dLocal Go: Payment ID: {payment_id} - Status: {status}")
        logger.debug(f"Webhook full body: {body}")
        
        if not payment_id:
            logger.error("Webhook notification missing payment ID")
            logger.error(f"Body received: {body}")
            raise HTTPException(status_code=400, detail="Missing payment ID")
        
        # Parsear la notificación (opcional, para validación)
        try:
            notification = WebhookNotification(**body)
        except Exception as e:
            logger.warning(f"Error parsing webhook notification (continuing anyway): {str(e)}")
            notification = None
        
        # Obtener detalles completos del pago desde dLocal
        try:
            logger.info(f"Retrieving payment details from dLocal for payment {payment_id}...")
            payment_details = await dlocal_service.get_payment_details(payment_id)
            payment_data = payment_details.model_dump()
            logger.info(f"Payment details retrieved: Status={payment_data.get('status')}, Status Detail={payment_data.get('status_detail')}")
        except Exception as e:
            logger.error(f"Error retrieving payment details: {str(e)}")
            # Si no podemos obtener los detalles, usar los datos del webhook
            payment_data = body
            logger.warning(f"Using webhook body as payment_data instead")
        
        # Agregar información extra al payload antes de enviarlo a terceros
        # Incluir el teléfono que se usó para crear el pago
        webhook_payload = {
            **payment_data,
            "original_phone": body.get("phone") or (payment_data.get("payer", {}).get("phone") if isinstance(payment_data.get("payer"), dict) else None)
        }
        
        # Enviar datos completos al webhook de terceros
        try:
            await webhook_service.send_payment_data(webhook_payload)
        except Exception as e:
            logger.error(f"Error sending to third party webhook: {str(e)}")
            # No fallar si el webhook de terceros falla
        
        payment_status = (body.get("status") or payment_data.get("status", "")).upper()
        logger.info(f"Payment status detected: '{payment_status}'")
        logger.info(f"Webhook processed successfully for payment {payment_id} (Status: {payment_status})")
        
        # Retornar 200 OK para confirmar recepción
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Webhook processed"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        # Retornar 200 de todas formas para que dLocal no reintente indefinidamente
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": str(e)}
        )


async def _process_upsell_confirmation(
    merchant_checkout_token: str,
    amount: Optional[float],
    description: Optional[str],
    order_id: Optional[str],
    installments: Optional[int],
) -> UpsellResponse:
    """Lógica compartida entre los endpoints GET y POST de confirmación de upsell.

    Si no se reciben overrides, usa el monto/descripción fijos de config (.env).
    La ventana válida es de 15 minutos desde el pago original (la valida dLocal).
    `installments` es experimental: dLocal Go no documenta cuotas en upsells.
    """
    if not settings.upsell_enabled:
        # Defensa por si alguien llama el endpoint con la feature desactivada
        # en config: cortamos antes de pegarle a dLocal.
        raise HTTPException(
            status_code=400,
            detail="Upsell feature is disabled (UPSELL_ENABLED=false in config)"
        )

    logger.info(
        f"Processing upsell confirmation - token={merchant_checkout_token[:12]}..., "
        f"amount_override={amount}, order_id_override={order_id}, "
        f"installments={installments}"
    )
    try:
        result = await dlocal_service.confirm_upsell(
            merchant_checkout_token=merchant_checkout_token,
            amount=amount,
            description=description,
            order_id=order_id,
            installments=installments,
        )
        logger.info(
            f"Upsell confirmation result: payment_id={result.payment_id}, "
            f"status={result.status}"
        )
        return result
    except Exception as e:
        logger.error(f"Error confirming upsell: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error confirming upsell: {str(e)}"
        )


@app.post(
    "/api/upsell/confirm/{merchant_checkout_token}",
    response_model=UpsellResponse,
    tags=["Upsell"],
)
async def confirm_upsell_post(
    merchant_checkout_token: str,
    upsell_request: Optional[UpsellRequest] = None,
):
    """
    Confirma el cobro de un One-Click Upsell (One Time Offer) usando POST.

    Se debe ejecutar dentro de los 15 minutos posteriores al pago original.
    El cliente NO necesita reingresar datos de tarjeta — dLocal usa la tarjeta
    del checkout original asociado al `merchant_checkout_token`.

    - **merchant_checkout_token**: token devuelto al crear el checkout original
    - **body** (opcional): permite overridear `amount`, `description` y `order_id`.
      Si no se manda body o los campos están vacíos, se usan los valores fijos
      configurados en `.env` (UPSELL_AMOUNT, UPSELL_DESCRIPTION).

    Si el cobro one-click falla, la respuesta incluye un `redirect_url` para que
    el cliente complete el pago con otro método.
    """
    body = upsell_request or UpsellRequest()
    return await _process_upsell_confirmation(
        merchant_checkout_token=merchant_checkout_token,
        amount=body.amount,
        description=body.description,
        order_id=body.order_id,
        installments=body.installments,
    )


def _extract_merchant_checkout_token(payment_details_raw: dict) -> Optional[str]:
    """Busca el merchant_checkout_token dentro del response del GET payment.

    dLocal Go puede devolverlo en el root del payload o en un sub-objeto.
    Como la doc del endpoint GET /v1/payments/{id} no documenta exactamente
    dónde aparece, probamos varios paths comunes.
    """
    if not isinstance(payment_details_raw, dict):
        return None

    direct = payment_details_raw.get("merchant_checkout_token")
    if direct:
        return direct

    # Algunos providers anidan el token dentro de "checkout" o "metadata"
    for nested_key in ("checkout", "checkout_data", "metadata", "data"):
        nested = payment_details_raw.get(nested_key)
        if isinstance(nested, dict) and nested.get("merchant_checkout_token"):
            return nested["merchant_checkout_token"]

    return None


def _render_upsell_fallback_html(success: bool, message: str, retry_url: Optional[str] = None) -> str:
    """Renderiza una página HTML simple cuando no hay URLs de redirect configuradas."""
    color = "#7c3aed" if success else "#dc2626"
    icon = "✓" if success else "✕"
    retry_button = (
        f'<a href="{retry_url}" style="display:inline-block;margin-top:24px;padding:12px 24px;'
        f'background:#7c3aed;color:white;text-decoration:none;border-radius:8px;'
        f'font-weight:600;">Reintentar pago</a>'
        if retry_url else ""
    )
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{'Compra confirmada' if success else 'Hubo un problema'}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: #0f0f1a;
                color: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                padding: 24px;
            }}
            .card {{
                background: #1a1a2e;
                padding: 48px;
                border-radius: 16px;
                max-width: 480px;
                text-align: center;
                border: 1px solid #2d2d44;
            }}
            .icon {{
                width: 64px;
                height: 64px;
                border-radius: 50%;
                background: {color};
                color: white;
                font-size: 32px;
                line-height: 64px;
                margin: 0 auto 24px;
            }}
            h1 {{ margin: 0 0 12px; font-size: 24px; }}
            p {{ margin: 0; color: #9ca3af; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">{icon}</div>
            <h1>{'¡Listo!' if success else 'Hubo un problema'}</h1>
            <p>{message}</p>
            {retry_button}
        </div>
    </body>
    </html>
    """


def _extract_payer_info(payment_details_raw: dict) -> dict:
    """Extrae email/phone/country del payment para enriquecer eventos de Meta CAPI.

    Cuanta más PII hasheada mande Meta, mejor matching de conversiones contra
    los usuarios de Facebook/Instagram.
    """
    if not isinstance(payment_details_raw, dict):
        return {}
    payer = payment_details_raw.get("payer") or {}
    return {
        "email": payer.get("email"),
        "phone": payer.get("phone"),
        "country": payment_details_raw.get("country"),
    }


def _resolve_upsell_pricing(ab_variant: Optional[str]) -> dict:
    """Devuelve el precio y descripción a usar según la variante de A/B test.

    Si no hay test activo o no hay variante asignada, usa la variante A (control)
    pero NO modifica la descripción (no agrega tag). Si hay variante asignada,
    le agrega `[Variant X]` al description para poder filtrar en el panel de
    dLocal y en el log.
    """
    if ab_variant == "B":
        return {
            "amount": settings.upsell_amount_variant_b,
            "description": f"{settings.upsell_description} [Variant B]",
            "variant": "B",
        }
    if ab_variant == "A":
        return {
            "amount": settings.upsell_amount,
            "description": f"{settings.upsell_description} [Variant A]",
            "variant": "A",
        }
    # Sin test activo
    return {
        "amount": settings.upsell_amount,
        "description": settings.upsell_description,
        "variant": None,
    }


def _render_upsell_template(
    request: Request,
    payment_id: str,
    pricing: Optional[dict] = None,
):
    """Helper que arma el contexto y renderiza el template `upsell.html`.

    Si se pasa `pricing` (resultado de `_resolve_upsell_pricing`), usa esos
    valores; si no, defaultea al precio normal (variante A / sin test).
    """
    if pricing is None:
        pricing = _resolve_upsell_pricing(None)

    decline_url = settings.upsell_decline_url or "/"
    return templates.TemplateResponse(
        "upsell.html",
        {
            "request": request,
            "payment_id": payment_id,
            "upsell_amount": pricing["amount"],
            "upsell_description": pricing["description"],
            "decline_url": decline_url,
            "meta_pixel_id": settings.meta_pixel_id,
        },
    )


@app.get("/upsell", tags=["Upsell"], summary="Página de oferta upsell (vía query param)")
async def render_upsell_page_querystring(request: Request):
    """
    Página de upsell servida cuando dLocal redirige al cliente después del pago.

    Esta es la URL pensada para `DLOCAL_SUCCESS_URL`:
        DLOCAL_SUCCESS_URL=https://dlocal.brunoelleon.com/upsell

    IMPORTANTE: dLocal Go redirige al success_url SIN agregar query params
    automáticamente. Por eso, en `dlocal_service.create_payment()` le inyectamos
    NOSOTROS el `order_id` como query param antes de mandar el create_payment.
    Cuando el cliente vuelve acá, leemos el order_id y buscamos en el upsell
    cache el merchant_checkout_token correspondiente.

    Casos:
    - Sin order_id en la URL → el flujo de upsell no fue inicializado correctamente
    - order_id no encontrado en cache → el server se reinició o pasó >30 min
    - Todo OK → renderiza la página de oferta
    """
    from fastapi.responses import HTMLResponse

    query_params = dict(request.query_params)
    logger.info(f"Upsell page received query params: {query_params}")

    order_id = query_params.get("order_id")
    if not order_id:
        logger.warning(
            f"Upsell page hit without order_id query param. "
            f"Query params received: {query_params}"
        )
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=False,
                message="No se pudo identificar tu compra. Si pagaste, contactanos a soporte."
            ),
            status_code=400,
        )

    cache_entry = upsell_cache.get_by_order_id(order_id)
    if not cache_entry:
        logger.warning(
            f"Upsell page: order_id={order_id} not found in cache "
            f"(server probably restarted or >30 min passed since payment creation)"
        )
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=False,
                message="La oferta ya no está disponible. Si recién pagaste, intentá refrescar la página."
            ),
            status_code=410,  # Gone
        )

    payment_id = cache_entry["payment_id"]
    pricing = _resolve_upsell_pricing(cache_entry.get("ab_variant"))
    logger.info(
        f"Rendering upsell page for order_id={order_id} → payment_id={payment_id}, "
        f"ab_variant={pricing['variant'] or '-'}, amount=USD {pricing['amount']}"
    )

    # Contar la vista para el dashboard del A/B test (no-op si no hay variante).
    ab_test_stats.record_view(pricing["variant"])

    return _render_upsell_template(request, payment_id, pricing=pricing)


@app.get("/upsell/{payment_id}", tags=["Upsell"], summary="Página de oferta upsell (vía path param)")
async def render_upsell_page(request: Request, payment_id: str):
    """
    Renderiza la página de oferta de upsell ("Pero antes... préstame atención acá").

    Versión con path param — útil para linkear directo. El flujo "real" desde
    dLocal usa `GET /upsell?payment_id=...` (ver endpoint de arriba).

    El template incluye:
    - Pixel de Meta (PageView + ViewContent + InitiateCheckout en el botón)
    - Timer de 10 minutos persistido en localStorage
    - Botón "Sí, sumar 3 meses" → /api/upsell/click/{payment_id}
    - Botón "No, gracias" → UPSELL_DECLINE_URL
    """
    return _render_upsell_template(request, payment_id)


@app.get(
    "/api/upsell/decline/{payment_id}",
    tags=["Upsell"],
    summary="Endpoint para el botón 'No, gracias' de la página de upsell",
)
async def upsell_decline_redirect(payment_id: str):
    """
    Endpoint para el botón "No, gracias" — registra el rechazo en las stats
    del A/B test y redirige al cliente al UPSELL_DECLINE_URL configurado.

    El registro del decline es best-effort: si falla por cualquier razón,
    igual redirigimos al cliente para no romper su experiencia.
    """
    from fastapi.responses import RedirectResponse

    decline_url = settings.upsell_decline_url or "/"

    # Best-effort: intentamos registrar el decline, pero si falla redirigimos igual.
    try:
        cache_entry = upsell_cache.get_by_payment_id(payment_id)
        if cache_entry:
            ab_variant = cache_entry.get("ab_variant")
            ab_test_stats.record_decline(ab_variant)
            logger.info(
                f"Upsell DECLINED for payment {payment_id} "
                f"(ab_variant={ab_variant or '-'}) → redirecting to decline URL"
            )
        else:
            logger.warning(
                f"Upsell decline registered but payment_id={payment_id} not in cache "
                f"(server restart o >30 min); decline will not be counted in stats"
            )
    except Exception as e:
        logger.error(f"Failed to record decline for payment {payment_id}: {e}")

    return RedirectResponse(url=decline_url)


@app.get(
    "/api/upsell/click/{payment_id}",
    tags=["Upsell"],
    summary="Endpoint para el botón 'Sí, sumar 3 meses' de la página de upsell",
)
async def upsell_click_redirect(request: Request, payment_id: str):
    """
    Endpoint pensado para ser el destino del botón "Sí, quiero el upsell" en la
    página de gracias / one-time-offer de Bruno.

    Flujo:
    1. Recibe el `payment_id` del checkout original.
    2. Llama a dLocal para obtener los detalles del pago y extraer el
       `merchant_checkout_token`.
    3. Llama al endpoint de confirmación de upsell (cobra los USD configurados).
    4. Si el cobro es exitoso, dispara un evento `Purchase` server-side a Meta
       Conversions API (más confiable que el Pixel del lado cliente).
    5. Redirige al cliente:
        - Si todo OK → `UPSELL_SUCCESS_URL` (o página HTML de fallback)
        - Si falla pero dLocal devuelve `redirect_url` → manda al cliente a ese
          link para que reintente con otro método de pago.
        - Si falla sin retry → `UPSELL_ERROR_URL` (o HTML de fallback)
    """
    from fastapi.responses import RedirectResponse, HTMLResponse

    logger.info(f"Upsell click received for payment_id={payment_id}")

    if not settings.upsell_enabled:
        logger.warning("Upsell click endpoint hit but UPSELL_ENABLED=false")
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=False,
                message="La oferta no está disponible en este momento."
            ),
            status_code=400,
        )

    # 1. Obtener el merchant_checkout_token. PRIORIDAD: cache (fast path),
    # con fallback a dLocal por si el server se reinició y el cache se perdió.
    token: Optional[str] = None
    payment_details = None

    cache_entry = upsell_cache.get_by_payment_id(payment_id)
    if cache_entry and cache_entry.get("merchant_checkout_token"):
        token = cache_entry["merchant_checkout_token"]
        logger.info(f"Upsell click: token resolved from cache for payment_id={payment_id}")

    # Siempre traemos los detalles del payment para tener PII (email/phone) que
    # le mandamos a Meta CAPI más abajo. Si el token vino del cache, esto es
    # solo enriquecimiento; si no vino, también lo usamos como fallback de token.
    try:
        payment_details = await dlocal_service.get_payment_details(payment_id)
    except Exception as e:
        logger.error(f"Could not retrieve payment {payment_id} for upsell click: {e}")
        if not token:
            # Si tampoco lo teníamos en cache, no hay forma de seguir.
            if settings.upsell_error_url:
                return RedirectResponse(url=settings.upsell_error_url)
            return HTMLResponse(
                _render_upsell_fallback_html(
                    success=False,
                    message="No pudimos encontrar tu compra. Si pagaste, contactanos a soporte."
                ),
                status_code=404,
            )

    # Fallback: si no había token en el cache, intentar extraerlo del payload
    # del GET payment (depende de que dLocal lo devuelva, lo cual no es 100% seguro).
    if not token and payment_details:
        token = _extract_merchant_checkout_token(payment_details.raw_data or {})

    if not token:
        logger.error(
            f"merchant_checkout_token not found in cache nor in payment {payment_id} response. "
            f"Verificar que el checkout fue creado con allow_upsell=true."
        )
        if settings.upsell_error_url:
            return RedirectResponse(url=settings.upsell_error_url)
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=False,
                message="Esta compra no es elegible para la oferta. Si creés que es un error, contactanos."
            ),
            status_code=400,
        )

    # 2. Resolver el precio según la variante de A/B test asignada (sticky por order_id).
    # Si el A/B test no está activo o el cache se perdió, cae a la variante A.
    ab_variant = cache_entry.get("ab_variant") if cache_entry else None
    pricing = _resolve_upsell_pricing(ab_variant)
    logger.info(
        f"Upsell click pricing for payment_id={payment_id}: "
        f"ab_variant={pricing['variant'] or '-'}, amount=USD {pricing['amount']}"
    )

    # 3. Confirmar el cobro del upsell con el precio/descripción de la variante.
    try:
        result = await dlocal_service.confirm_upsell(
            merchant_checkout_token=token,
            amount=pricing["amount"],
            description=pricing["description"],
        )
    except Exception as e:
        logger.error(f"Error confirming upsell for payment {payment_id}: {e}")
        if settings.upsell_error_url:
            return RedirectResponse(url=settings.upsell_error_url)
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=False,
                message="No pudimos procesar el cobro. Tu compra principal sigue activa."
            ),
            status_code=500,
        )

    # 4. Decidir el redirect según el estado del cobro
    status_upper = (result.status or "").upper()

    if status_upper == "PAID":
        logger.info(
            f"Upsell PAID for original payment {payment_id} "
            f"(ab_variant={pricing['variant'] or '-'}) → redirecting to success"
        )

        # Contar la compra para el dashboard del A/B test.
        ab_test_stats.record_purchase(pricing["variant"], result.amount)

        # Disparar Purchase event a Meta Conversions API (server-side).
        # Usamos el payment_id del upsell como event_id para que sea estable
        # y deduplicable si en el futuro se agrega el Pixel del lado cliente.
        # Si hay A/B test activo, agregamos la variante al custom_data para
        # filtrar conversiones por variante en Meta Events Manager.
        try:
            raw = payment_details.raw_data if payment_details else {}
            payer_info = _extract_payer_info(raw or {})
            await meta_pixel_service.send_purchase_event(
                event_id=result.payment_id or f"upsell_{payment_id}",
                amount=result.amount,
                currency=result.currency,
                order_id=result.order_id,
                client_ip=request.client.host if request.client else None,
                client_user_agent=request.headers.get("user-agent"),
                email=payer_info.get("email"),
                phone=payer_info.get("phone"),
                country=payer_info.get("country"),
                event_source_url=str(request.url),
                ab_variant=pricing["variant"],
            )
        except Exception as e:
            # Nunca dejamos que un fallo en tracking rompa el redirect al cliente.
            logger.error(f"Failed to send Meta Purchase event: {e}")

        if settings.upsell_success_url:
            return RedirectResponse(url=settings.upsell_success_url)
        return HTMLResponse(
            _render_upsell_fallback_html(
                success=True,
                message="Tu extensión de 3 meses ya quedó sumada a la mentoría. ¡Nos vemos adentro!"
            )
        )

    # Si el cobro falló pero dLocal nos dio un link para reintentar manualmente,
    # priorizamos llevar al cliente ahí (puede pagar con otra tarjeta/método).
    if result.redirect_url:
        logger.info(
            f"Upsell {status_upper} for payment {payment_id}, "
            f"redirecting customer to dLocal retry URL"
        )
        return RedirectResponse(url=result.redirect_url)

    # Cobro falló sin opción de retry
    logger.warning(f"Upsell failed for payment {payment_id}, status={status_upper}")
    if settings.upsell_error_url:
        return RedirectResponse(url=settings.upsell_error_url)
    return HTMLResponse(
        _render_upsell_fallback_html(
            success=False,
            message="No pudimos procesar el cobro de la extensión. Tu compra principal sigue activa."
        ),
        status_code=200,
    )


@app.get(
    "/api/upsell/confirm/{merchant_checkout_token}",
    response_model=UpsellResponse,
    tags=["Upsell"],
)
async def confirm_upsell_get(
    merchant_checkout_token: str,
    amount: Optional[float] = None,
    description: Optional[str] = None,
    order_id: Optional[str] = None,
    installments: Optional[int] = None,
):
    """
    Confirma el cobro de un One-Click Upsell usando GET con query params.

    Versión "simple" del endpoint para llamar desde la success page con un
    `<a href>` o un `fetch` sin body. Funcionalmente idéntico al POST.

    Query params (todos opcionales):
    - **amount**: override del monto (default: UPSELL_AMOUNT del .env)
    - **description**: override de la descripción (default: UPSELL_DESCRIPTION)
    - **order_id**: order id custom (default: se autogenera)
    - **installments**: (EXPERIMENTAL) cantidad de cuotas a cobrar el upsell.
      dLocal Go no documenta cuotas para upsells, lo mandamos igual y vemos
      si lo respeta. Si no funciona, omitir el parámetro.

    Ejemplo:
        GET /api/upsell/confirm/abc123token
        GET /api/upsell/confirm/abc123token?installments=3

    Si el cobro one-click falla, la respuesta incluye un `redirect_url` para que
    el cliente complete el pago con otro método.
    """
    return await _process_upsell_confirmation(
        merchant_checkout_token=merchant_checkout_token,
        amount=amount,
        description=description,
        order_id=order_id,
        installments=installments,
    )


_basic_auth = HTTPBasic(realm="Mentoría León Admin")


def _require_admin(credentials: HTTPBasicCredentials = Depends(_basic_auth)) -> str:
    """Dependencia de FastAPI: valida Basic Auth contra ADMIN_USERNAME/PASSWORD.

    Si las variables de entorno no están seteadas, devuelve 503 — preferimos
    cortar el acceso a "dejar el dashboard expuesto sin querer".
    Usamos `secrets.compare_digest` para comparación constant-time
    (evita timing attacks contra el password).
    """
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints disabled (ADMIN_USERNAME/ADMIN_PASSWORD not configured)",
        )

    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.admin_username.encode("utf-8"),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.admin_password.encode("utf-8"),
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic realm=\"Mentoría León Admin\""},
        )
    return credentials.username


def _format_ts(epoch: Optional[float]) -> Optional[str]:
    """Formatea un timestamp UNIX a string legible UTC. None si epoch es None."""
    if not epoch:
        return None
    return datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S UTC")


@app.get(
    "/admin/ab-test/stats",
    tags=["Admin"],
    summary="Dashboard del A/B test del upsell (HTML, requiere Basic Auth)",
)
async def ab_test_dashboard(request: Request, _user: str = Depends(_require_admin)):
    """
    Dashboard interno con resultados del A/B test del upsell.

    Autenticación: HTTP Basic Auth con ADMIN_USERNAME/ADMIN_PASSWORD del .env.
    Si esas variables no están seteadas, devuelve 503 (acceso deshabilitado).

    Métricas que muestra:
    - Vistas, compras, conversion rate, revenue total, revenue per visitor por variante
    - Ganador por revenue per visitor (la métrica correcta para A/B de precios)
    - Confianza estadística (z-test de dos proporciones)
    """
    summary = ab_test_stats.get_summary()
    return templates.TemplateResponse(
        "ab_test_dashboard.html",
        {
            "request": request,
            "started_at_str": _format_ts(summary["started_at"]) or "—",
            "last_event_at_str": _format_ts(summary["last_event_at"]),
            "variants": summary["variants"],
            "comparison": summary["comparison"],
            "prices": {
                "A": settings.upsell_amount,
                "B": settings.upsell_amount_variant_b,
            },
        },
    )


@app.get(
    "/admin/ab-test/stats.json",
    tags=["Admin"],
    summary="Dashboard del A/B test en formato JSON (requiere Basic Auth)",
)
async def ab_test_stats_json(_user: str = Depends(_require_admin)):
    """Versión JSON del dashboard, útil para automatizaciones / integraciones."""
    return ab_test_stats.get_summary()


@app.post(
    "/admin/ab-test/reset",
    tags=["Admin"],
    summary="Resetea los counters del A/B test a cero (requiere Basic Auth)",
)
async def ab_test_reset(_user: str = Depends(_require_admin)):
    """Útil cuando se cierra un test y se quiere arrancar uno nuevo desde cero."""
    ab_test_stats.reset()
    logger.info(f"AB test stats reset by admin user '{_user}'")
    return {"status": "ok", "message": "AB test stats reseteadas"}


@app.get("/api/payment/{payment_id}", tags=["Payments"])
async def get_payment(payment_id: str):
    """
    Obtiene los detalles de un pago específico
    
    - **payment_id**: ID del pago a consultar
    """
    try:
        logger.info(f"Retrieving payment: {payment_id}")
        
        payment_details = await dlocal_service.get_payment_details(payment_id)
        
        return payment_details
        
    except Exception as e:
        logger.error(f"Error retrieving payment {payment_id}: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=f"Payment not found or error retrieving: {str(e)}"
        )


# Manejador de errores global
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Manejador global de excepciones"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc) if settings.environment == "development" else None
        }
    )


if __name__ == "__main__":
    import os
    import uvicorn
    
    # En plataformas como Render/Heroku el puerto lo inyecta la variable PORT.
    # En local cae al 8001 por defecto.
    port = int(os.getenv("PORT", "8001"))
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.environment == "development"
    )

