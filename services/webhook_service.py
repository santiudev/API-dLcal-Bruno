"""
Servicio para enviar datos a webhooks de terceros
"""
import httpx
import logging
from typing import Dict, Any
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)


class WebhookService:
    """Servicio para enviar datos a webhooks de terceros"""
    
    def __init__(self):
        self.webhook_url = settings.third_party_webhook_url
    
    async def send_payment_data(
        self,
        payment_data: Dict[str, Any],
        max_retries: int = 3
    ) -> bool:
        """
        Envía datos de pago a un webhook de terceros
        
        Args:
            payment_data: Diccionario con todos los datos del pago
            max_retries: Número máximo de intentos en caso de fallo
            
        Returns:
            bool: True si se envió exitosamente
        """
        if not self.webhook_url:
            logger.warning("Third party webhook URL not configured")
            return False
        
        # Agregar metadata adicional
        payload = {
            "event": "payment_update",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": payment_data
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "dLocal-Integration/1.0"
        }
        
        # Intentar enviar con reintentos
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Sending payment data to third party webhook (attempt {attempt}/{max_retries})")
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.webhook_url,
                        json=payload,
                        headers=headers
                    )
                    
                    # Considerar exitoso si es 2xx
                    if 200 <= response.status_code < 300:
                        logger.info(f"Payment data sent successfully: {response.status_code}")
                        return True
                    else:
                        logger.warning(
                            f"Third party webhook returned status {response.status_code}: {response.text}"
                        )
                        
            except httpx.TimeoutException:
                logger.error(f"Timeout sending to third party webhook (attempt {attempt}/{max_retries})")
            except httpx.RequestError as e:
                logger.error(f"Request error sending to webhook (attempt {attempt}/{max_retries}): {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error sending to webhook (attempt {attempt}/{max_retries}): {str(e)}")
            
            # Si no es el último intento, esperar antes de reintentar
            if attempt < max_retries:
                await self._wait_before_retry(attempt)
        
        logger.error("Failed to send payment data after all retries")
        return False
    
    async def _wait_before_retry(self, attempt: int):
        """
        Espera antes de reintentar (backoff exponencial)
        
        Args:
            attempt: Número del intento actual
        """
        import asyncio
        wait_time = min(2 ** attempt, 10)  # Max 10 segundos
        logger.info(f"Waiting {wait_time} seconds before retry...")
        await asyncio.sleep(wait_time)
    
    async def send_notification(
        self,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Envía una notificación genérica a terceros
        
        Args:
            event_type: Tipo de evento (ej: "payment_created", "payment_rejected")
            data: Datos del evento
            
        Returns:
            bool: True si se envió exitosamente
        """
        payload = {
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data
        }
        
        return await self.send_payment_data(payload)


# Instancia singleton del servicio
webhook_service = WebhookService()

