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
    RejectedPayment
)
from services.dlocal_service import dlocal_service
from services.sheets_service import sheets_service
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
        "amount": 497.0,
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
    from services.dlocal_service import dlocal_service
    import uuid
    
    phone_number = tel if tel.startswith('+') else f'+{tel}'
    payment_type = "installments" if type.lower() in ["installments", "cuotas"] else "single"
    
    # Calcular lo mismo que en el servicio
    if payment_type == "installments":
        amount = 497.00
        max_installments = 4
    else:
        amount = 497.00
        max_installments = 1
    
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
        "description": settings.payment_description,
        "notification_url": f"{settings.app_base_url}/api/webhook/dlocal",
        "success_url": settings.dlocal_success_url,
        "error_url": settings.dlocal_error_url,
        "pending_url": settings.dlocal_pending_url,
        "cancel_url": settings.dlocal_cancel_url
    }
    
    if payment_type == "installments":
        payment_data["max_installments"] = max_installments
        payment_data["payment_type"] = "CREDIT_CARD"  # Solo tarjeta de crédito para cuotas
    
    return {
        "message": "Esto es lo que se enviaría a dLocal",
        "payment_type": payment_type,
        "installments_info": {
            "max_installments": max_installments,
            "amount_per_installment": round(amount / max_installments, 2),
            "total_amount": amount
        },
        "full_payload": payment_data
    }


@app.get("/api/pago", response_model=PaymentResponse, tags=["Payments"])
async def create_payment_get(
    tel: str = None,
    country: str = "MX",
    type: str = "cuotas",
    name: str = None,
    email: str = None
):
    """
    Crea un link de pago en dLocal y devuelve JSON con los datos
    
    Parámetros URL (TODOS OPCIONALES):
    - **tel**: Número de teléfono con código de país (ej: 5255123456789). Si no se envía, el usuario completa sus datos
    - **country**: Código del país (AR, MX, CO, CL, etc.). Por defecto: MX
    - **type**: Tipo de pago
        - "installments" o "cuotas": $497 USD en hasta 4 cuotas - SOLO CREDIT_CARD (DEFAULT)
        - "single" o "unico": $497 USD en un solo pago - Todos los métodos
    - **name**: Nombre del cliente (opcional)
    - **email**: Email del cliente (opcional)
    
    Ejemplos:
    - /api/pago?tel=5255123456789&country=MX&type=cuotas  → Con teléfono precargado
    - /api/pago?country=AR&type=single                     → Sin teléfono, pago único
    - /api/pago                                            → Checkout limpio, 12 cuotas, país MX
    """
    try:
        # Normalizar el teléfono (solo si se proporciona)
        phone_number = None
        if tel:
            phone_number = tel if tel.startswith('+') else f'+{tel}'
        
        # Normalizar el tipo de pago
        payment_type = "installments" if type.lower() in ["installments", "cuotas"] else "single"
        
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
    type: str = "cuotas",
    name: str = None,
    email: str = None
):
    """
    Crea un pago y REDIRIGE automáticamente al checkout de dLocal
    
    Parámetros URL (TODOS OPCIONALES):
    - **tel**: Número de teléfono con código de país (ej: 5255123456789). Si no se envía, el usuario completa sus datos
    - **country**: Código del país (AR, MX, CO, CL, etc.). Por defecto: MX
    - **type**: Tipo de pago
        - "cuotas"/"installments": $497 USD en hasta 4 cuotas - SOLO CREDIT_CARD (DEFAULT)
        - "single"/"unico": $497 USD en un solo pago - Todos los métodos
    - **name**: Nombre del cliente (opcional)
    - **email**: Email del cliente (opcional)
    
    Ejemplos:
    - /pagar?tel=5255123456789&country=MX&type=cuotas  → Con teléfono precargado
    - /pagar?country=AR&type=single                     → Sin teléfono, pago único
    - /pagar                                            → Checkout limpio, 12 cuotas, país MX
    """
    from fastapi.responses import RedirectResponse
    
    try:
        # Normalizar el teléfono (solo si se proporciona)
        phone_number = None
        if tel:
            phone_number = tel if tel.startswith('+') else f'+{tel}'
        
        # Normalizar el tipo de pago
        payment_type = "installments" if type.lower() in ["installments", "cuotas"] else "single"
        
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
    - **payment_type**: Tipo de pago
        - "installments": 497 USD en hasta 4 cuotas - SOLO CREDIT_CARD
        - "single": 497 USD en un solo pago - Todos los métodos
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
    2. Envía los datos completos al webhook de terceros
    3. Si el pago fue rechazado, lo guarda en Google Sheets
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
        
        # Guardar TODOS los pagos en Google Sheets (sin importar el estado)
        payment_status = (body.get("status") or payment_data.get("status", "")).upper()
        logger.info(f"Payment status detected: '{payment_status}' (from webhook or payment_data)")
        logger.info(f"Saving payment {payment_id} to Google Sheets (Status: {payment_status})")
        
        try:
            # Extraer información del pago
            payer = payment_data.get("payer", {})
            
            # Obtener el teléfono del payer o del webhook original
            customer_phone = None
            if isinstance(payer, dict):
                customer_phone = payer.get("phone")
            if not customer_phone:
                customer_phone = body.get("phone")
            
            # Crear el registro del pago (todos los estados)
            payment_record = RejectedPayment(
                payment_id=payment_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                status=payment_status or "UNKNOWN",  # Estado del pago
                amount=payment_data.get("amount", 0),
                currency=payment_data.get("currency", "USD"),
                country=payment_data.get("country", "N/A"),
                status_detail=payment_data.get("status_detail") or payment_data.get("status_code") or body.get("status_detail") or "N/A",
                status_code=payment_data.get("status_code") or body.get("status_code"),
                payment_method_type=payment_data.get("payment_method_type"),
                customer_email=payer.get("email") if isinstance(payer, dict) else None,
                customer_phone=customer_phone,
                order_id=payment_data.get("order_id")
            )
            
            result = sheets_service.save_rejected_payment_from_model(payment_record)
            if result:
                logger.info(f"✅ Payment {payment_id} (Status: {payment_status}) successfully saved to Google Sheets")
            else:
                logger.error(f"❌ Failed to save payment {payment_id} to Google Sheets")
            
        except Exception as e:
            logger.error(f"Error saving payment to Sheets: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # No fallar si Google Sheets falla
        
        logger.info(f"Webhook processed successfully for payment {payment_id}")
        
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
    import uvicorn
    
    # Ejecutar el servidor
    # Cambia el puerto aquí si el 8000 está ocupado
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,  # Cambiado a 8001, puedes usar el que quieras
        reload=settings.environment == "development"
    )

