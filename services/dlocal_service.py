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
            payment_type: 'plan6' (6 cuotas de USD 117) o 'plan9' (9 cuotas de USD 87)
            customer_name: Nombre del cliente (opcional)
            customer_email: Email del cliente (opcional)
            
        Returns:
            PaymentResponse con payment_id, redirect_url y otros datos
        """
        # Mentoría León: dos planes con cuotas vía tarjeta de crédito;
        # otros métodos de pago cobran el total de una sola vez.
        if payment_type == "plan9":
            # 9 cuotas de USD 87 = USD 783 total
            amount = 783.00
            max_installments = 9
            installment_amount = 87.00
        else:  # plan6 (default)
            # 6 cuotas de USD 117 = USD 702 total
            amount = 702.00
            max_installments = 6
            installment_amount = 117.00
        
        # Generar order_id único
        order_id = f"order_{uuid.uuid4().hex[:16]}"
        
        # Descripción que aparece en el checkout (incluye el plan elegido)
        description = (
            f"{settings.payment_description} - {max_installments} cuotas de USD {installment_amount:.0f}"
        )
        
        # Construir el body del request
        # No restringimos `payment_type`: el checkout muestra todos los métodos disponibles
        # en el país. Con tarjeta de crédito el cliente puede elegir cuotas (hasta max_installments).
        # Con métodos sin cuotas (débito, efectivo, transferencia) paga el total de una sola vez.
        payment_data = {
            "amount": amount,
            "currency": "USD",
            "country": country.upper(),
            "payment_method_flow": "REDIRECT",
            "order_id": order_id,
            "name": settings.merchant_name,  # Nombre que aparece en el checkout
            "description": description,
            "notification_url": f"{self.app_base_url}/api/webhook/dlocal",
            "max_installments": max_installments,
        }
        
        # Las URLs de retorno son opcionales: si no están seteadas en .env,
        # dLocal usa su propia pantalla de estado y no redirige al cliente.
        optional_redirect_urls = {
            "success_url": settings.dlocal_success_url,
            "error_url": settings.dlocal_error_url,
            "pending_url": settings.dlocal_pending_url,
            "cancel_url": settings.dlocal_cancel_url,
        }
        for key, value in optional_redirect_urls.items():
            if value:
                payment_data[key] = value
        
        # Solo agregar el objeto payer si se proporcionó teléfono
        # Esto permite que el checkout esté limpio si no se pasa tel
        if phone_number:
            payment_data["payer"] = {
                "phone": phone_number  # Enviar solo el teléfono, otros campos quedan libres
            }
        
        # Generar headers simples con Bearer token
        headers = get_dlocal_headers(self.api_key, self.secret_key)
        
        # Realizar la petición a dLocal Go
        url = f"{self.api_url}/v1/payments"
        
        logger.info(
            f"Creating payment for country {country}, plan {payment_type}, "
            f"total USD {amount} ({max_installments} cuotas de USD {installment_amount:.0f})"
        )
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

