"""
Servicio de integración con dLocal Go API
"""
import httpx
import logging
from typing import Optional
import uuid

from config import settings
from utils.security import get_dlocal_headers
from models import PaymentResponse, PaymentDetails, UpsellResponse

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
            payment_type: 'plan6' (6x USD 117), 'plan9' (9x USD 87) o 'contado' (USD 597 pago único)
            customer_name: Nombre del cliente (opcional)
            customer_email: Email del cliente (opcional)
            
        Returns:
            PaymentResponse con payment_id, redirect_url y otros datos
        """
        # Mentoría León: 3 planes posibles. Las cuotas aplican solo si el cliente
        # paga con tarjeta de crédito; otros métodos cobran el total de una sola vez.
        if payment_type == "plan9":
            # 9 cuotas de USD 87 = USD 783 total
            amount = 783.00
            max_installments = 9
            installment_amount = 87.00
            description = f"{settings.payment_description} - 9 cuotas de USD 87"
        elif payment_type == "contado":
            # Pago de contado: USD 597 sin cuotas
            amount = 597.00
            max_installments = 1
            installment_amount = 597.00
            description = f"{settings.payment_description} - Pago de contado"
        else:  # plan6 (default)
            # 6 cuotas de USD 117 = USD 702 total
            amount = 702.00
            max_installments = 6
            installment_amount = 117.00
            description = f"{settings.payment_description} - 6 cuotas de USD 117"
        
        # Generar order_id único
        order_id = f"order_{uuid.uuid4().hex[:16]}"
        
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
        }

        # max_installments solo tiene sentido en planes con cuotas (>1)
        if max_installments > 1:
            payment_data["max_installments"] = max_installments

        # One-Click Upsell: si está habilitado en la cuenta del merchant, se pide
        # allow_upsell=true para que dLocal devuelva el merchant_checkout_token y
        # permita cobrar el OTO con un solo click después del pago original.
        # IMPORTANTE: con allow_upsell=true, el checkout solo permite tarjetas de
        # crédito/débito (no efectivo, no transferencia).
        if settings.upsell_enabled:
            payment_data["allow_upsell"] = True
        
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
                    installments=max_installments,
                    merchant_checkout_token=result.get("merchant_checkout_token"),
                )
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating payment: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Error creating payment: {e.response.text}")
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            raise

    async def confirm_upsell(
        self,
        merchant_checkout_token: str,
        amount: Optional[float] = None,
        description: Optional[str] = None,
        order_id: Optional[str] = None,
        installments: Optional[int] = None,
    ) -> UpsellResponse:
        """
        Confirma el cobro de un One-Click Upsell sobre un checkout previamente
        creado con allow_upsell=true.

        Solo funciona dentro de los 15 minutos posteriores al pago original.
        Si el cobro falla, la respuesta incluye un redirect_url para que el cliente
        complete el pago con otro método.

        Args:
            merchant_checkout_token: Token devuelto en el create_payment original
            amount: Monto del upsell (si None, usa settings.upsell_amount)
            description: Descripción del cargo (si None, usa settings.upsell_description)
            order_id: Order ID custom (si None, se genera uno nuevo)
            installments: (EXPERIMENTAL) cantidad de cuotas a cobrar con tarjeta de
                crédito. dLocal Go no documenta este campo para el endpoint de
                upsell, lo mandamos igual y vemos si lo respeta en sandbox.

        Returns:
            UpsellResponse con el estado del cobro
        """
        # Valores por defecto desde config (.env)
        final_amount = amount if amount is not None else settings.upsell_amount
        final_description = description or settings.upsell_description
        final_order_id = order_id or f"upsell_{uuid.uuid4().hex[:16]}"

        # dLocal Go espera "orderId" en camelCase para el endpoint de upsell
        # (no order_id como en el create_payment estándar).
        upsell_data = {
            "amount": final_amount,
            "description": final_description,
            "orderId": final_order_id,
        }

        # EXPERIMENTAL: probar si dLocal acepta cuotas en el upsell one-click.
        # Mandamos los dos nombres de campo posibles porque la doc no especifica
        # cuál es el correcto para este endpoint en particular.
        if installments is not None and installments > 1:
            upsell_data["installments"] = installments
            upsell_data["max_installments"] = installments

        headers = get_dlocal_headers(self.api_key, self.secret_key)
        url = f"{self.api_url}/v1/payments/upsell/{merchant_checkout_token}"

        logger.info(
            f"Confirming upsell for token {merchant_checkout_token[:12]}... "
            f"amount=USD {final_amount}, order_id={final_order_id}, "
            f"installments={installments or 1}"
        )
        logger.debug(f"Upsell data being sent to dLocal: {upsell_data}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=upsell_data, headers=headers)
                response.raise_for_status()
                result = response.json()

                logger.info(
                    f"Upsell processed: payment_id={result.get('id')}, "
                    f"status={result.get('status')}"
                )

                return UpsellResponse(
                    payment_id=result.get("id", ""),
                    status=result.get("status", "UNKNOWN"),
                    amount=result.get("amount", final_amount),
                    currency=result.get("currency", "USD"),
                    description=result.get("description", final_description),
                    order_id=result.get("order_id") or result.get("orderId") or final_order_id,
                    merchant_checkout_token=merchant_checkout_token,
                    redirect_url=result.get("redirect_url"),
                )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error confirming upsell: {e.response.status_code} - {e.response.text}"
            )
            raise Exception(f"Error confirming upsell: {e.response.text}")
        except Exception as e:
            logger.error(f"Error confirming upsell: {str(e)}")
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

