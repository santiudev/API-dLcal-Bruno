"""
Servicio de integración con dLocal Go API
"""
import httpx
import logging
from typing import Optional
import uuid

from config import settings
from utils.security import get_dlocal_headers
from models import PaymentResponse, PaymentDetails

logger = logging.getLogger(__name__)


class DLocalService:
    """Servicio para interactuar con la API de dLocal Go"""
    
    def __init__(self):
        self.api_url = settings.dlocal_api_url
        self.api_key = settings.dlocal_api_key
        self.secret_key = settings.dlocal_secret_key
        self.app_base_url = settings.app_base_url
    
    async def create_payment(
        self,
        phone_number: Optional[str],
        country: str,
        payment_type: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None
    ) -> PaymentResponse:
        """
        Crea un pago en dLocal
        
        Args:
            phone_number: Número de teléfono del cliente
            country: Código ISO del país (2 letras)
            payment_type: 'installments' para 12 cuotas o 'single' para pago único
            customer_name: Nombre del cliente (opcional)
            customer_email: Email del cliente (opcional)
            
        Returns:
            PaymentResponse con payment_id, redirect_url y otros datos
        """
        # Calcular monto según el tipo de pago
        if payment_type == "installments":
            # 497 USD en hasta 12 cuotas - SOLO CREDIT_CARD
            amount = 497.00
            max_installments = 12
        else:  # single
            # Pago único de 497 USD - Todos los métodos de pago disponibles
            amount = 497.00
            max_installments = 1
        
        # Generar order_id único
        order_id = f"order_{uuid.uuid4().hex[:16]}"
        
        # Construir el body del request
        payment_data = {
            "amount": amount,
            "currency": "USD",
            "country": country.upper(),
            "payment_method_flow": "REDIRECT",
            "order_id": order_id,
            "name": settings.merchant_name,  # Nombre que aparece en el checkout
            "description": settings.payment_description if payment_type == "installments" else f"{settings.payment_description} - Pago único",  # Descripción del pago
            "notification_url": f"{self.app_base_url}/api/webhook/dlocal",
            "success_url": settings.dlocal_success_url,
            "error_url": settings.dlocal_error_url,
            "pending_url": settings.dlocal_pending_url,
            "cancel_url": settings.dlocal_cancel_url
        }
        
        # Para pagos en cuotas, restringir a solo tarjeta de crédito
        if payment_type == "installments":
            payment_data["payment_type"] = "CREDIT_CARD"
        
        # Solo agregar el objeto payer si se proporcionó teléfono
        # Esto permite que el checkout esté limpio si no se pasa tel
        if phone_number:
            payment_data["payer"] = {
                "phone": phone_number  # Enviar solo el teléfono, otros campos quedan libres
            }
        
        # Agregar información de cuotas si aplica (solo max_installments)
        if payment_type == "installments":
            payment_data["max_installments"] = max_installments
        
        # Generar headers simples con Bearer token
        headers = get_dlocal_headers(self.api_key, self.secret_key)
        
        # Realizar la petición a dLocal Go
        url = f"{self.api_url}/v1/payments"
        
        logger.info(f"Creating payment for country {country}, type {payment_type}, amount {amount}")
        if payment_type == "installments":
            logger.info(f"Max installments offered: {max_installments} cuotas")
        logger.debug(f"Payment data being sent to dLocal: {payment_data}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payment_data,
                    headers=headers
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Payment created successfully: {result.get('id')}")
                
                # Construir response
                return PaymentResponse(
                    payment_id=result.get("id"),
                    redirect_url=result.get("redirect_url", ""),
                    status=result.get("status", "PENDING"),
                    amount=amount,
                    currency="USD",
                    installments=max_installments
                )
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating payment: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Error creating payment: {e.response.text}")
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            raise
    
    async def get_payment_details(self, payment_id: str) -> PaymentDetails:
        """
        Obtiene los detalles completos de un pago desde dLocal Go
        
        Args:
            payment_id: ID del pago a consultar
            
        Returns:
            PaymentDetails con toda la información del pago
        """
        # Generar headers simples
        headers = get_dlocal_headers(self.api_key, self.secret_key)
        
        url = f"{self.api_url}/v1/payments/{payment_id}"
        
        logger.info(f"Retrieving payment details for: {payment_id}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Payment details retrieved successfully: {payment_id}")
                
                # Construir PaymentDetails
                return PaymentDetails(
                    id=result.get("id"),
                    status=result.get("status"),
                    status_detail=result.get("status_detail"),
                    status_code=result.get("status_code"),
                    amount=result.get("amount"),
                    currency=result.get("currency"),
                    country=result.get("country"),
                    payment_method_id=result.get("payment_method_id"),
                    payment_method_type=result.get("payment_method_type"),
                    payment_method_flow=result.get("payment_method_flow"),
                    payer=result.get("payer"),
                    order_id=result.get("order_id"),
                    description=result.get("description"),
                    created_date=result.get("created_date"),
                    approved_date=result.get("approved_date"),
                    installments=result.get("installments"),
                    installments_amount=result.get("installments_amount"),
                    callback_url=result.get("callback_url"),
                    notification_url=result.get("notification_url"),
                    raw_data=result  # Guardar datos completos
                )
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error retrieving payment: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Error retrieving payment: {e.response.text}")
        except Exception as e:
            logger.error(f"Error retrieving payment: {str(e)}")
            raise


# Instancia singleton del servicio
dlocal_service = DLocalService()

