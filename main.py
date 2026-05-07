"""
API Backend para integración con dLocal Go
Procesa pagos, recibe webhooks y envía notificaciones
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

from config import settings
from models import (
    PaymentRequest,
    PaymentResponse,
    WebhookNotification,
    HealthResponse,
)
from services.dlocal_service import dlocal_service
from services.webhook_service import webhook_service

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
    email: str = None
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
            f"Type: {payment_type}, Phone: {phone_number or 'Not provided'}"
        )
        
        # Crear el pago en dLocal
        payment_response = await dlocal_service.create_payment(
            phone_number=phone_number,
            country=country.upper(),
            payment_type=payment_type,
            customer_name=name,
            customer_email=email
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
    email: str = None
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
            f"Type: {payment_type}, Phone: {phone_number or 'Not provided'}"
        )
        
        # Crear el pago en dLocal
        payment_response = await dlocal_service.create_payment(
            phone_number=phone_number,
            country=country.upper(),
            payment_type=payment_type,
            customer_name=name,
            customer_email=email
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

