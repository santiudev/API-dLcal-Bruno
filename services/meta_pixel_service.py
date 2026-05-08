"""
Servicio de integración con Meta Conversions API (server-side tracking).

¿Por qué server-side?
- No lo bloquean ad-blockers ni navegadores con anti-tracking (Safari ITP, Firefox, etc.).
- Es la fuente de verdad para conversiones (Pixel del lado cliente puede fallar).
- Permite hacer dedup con eventos del Pixel usando event_id.

Eventos típicos del flujo de upsell:
- "Purchase" cuando se confirma el cobro del upsell (server-side, acá).
- "ViewContent" / "InitiateCheckout" se disparan del lado cliente con el Pixel.
"""
import hashlib
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


def _sha256(value: Optional[str]) -> Optional[str]:
    """Hashea un valor a SHA-256 lowercase, como pide Meta para PII."""
    if not value:
        return None
    normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MetaPixelService:
    """Wrapper sobre Meta Conversions API para enviar eventos server-side."""

    def __init__(self):
        self.pixel_id = settings.meta_pixel_id
        self.access_token = settings.meta_access_token
        self.api_version = settings.meta_graph_api_version

    @property
    def is_configured(self) -> bool:
        """True si están seteadas las credenciales mínimas para enviar eventos."""
        return bool(self.pixel_id and self.access_token)

    async def send_purchase_event(
        self,
        event_id: str,
        amount: float,
        currency: str,
        order_id: str,
        client_ip: Optional[str] = None,
        client_user_agent: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        country: Optional[str] = None,
        event_source_url: Optional[str] = None,
    ) -> bool:
        """
        Envía un evento "Purchase" a Meta Conversions API.

        Args:
            event_id: ID único del evento. Se usa para deduplicar contra el
                Pixel del lado cliente (si ambos mandan el mismo event_id, Meta
                cuenta UNA sola conversión).
            amount, currency, order_id: datos del cobro.
            client_ip, client_user_agent: ayudan a Meta a hacer match con el usuario.
            email, phone, country: PII del cliente — se hashean antes de mandar.
            event_source_url: URL donde ocurrió el evento (la success page).

        Returns:
            True si Meta aceptó el evento (status 2xx), False si falló.
        """
        return await self._send_event(
            event_name="Purchase",
            event_id=event_id,
            client_ip=client_ip,
            client_user_agent=client_user_agent,
            email=email,
            phone=phone,
            country=country,
            event_source_url=event_source_url,
            custom_data={
                "currency": currency,
                "value": amount,
                "order_id": order_id,
            },
        )

    async def _send_event(
        self,
        event_name: str,
        event_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        client_user_agent: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        country: Optional[str] = None,
        event_source_url: Optional[str] = None,
        custom_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Envía un evento genérico a Meta Conversions API."""
        if not self.is_configured:
            logger.info(
                f"Meta Pixel not configured (META_PIXEL_ID/ACCESS_TOKEN missing) — "
                f"skipping {event_name} event"
            )
            return False

        # user_data: a más datos hasheados, mejor matching del lado de Meta.
        user_data: Dict[str, Any] = {}
        if client_ip:
            user_data["client_ip_address"] = client_ip
        if client_user_agent:
            user_data["client_user_agent"] = client_user_agent
        if email:
            user_data["em"] = [_sha256(email)]
        if phone:
            # Meta espera el teléfono sin el "+" ni espacios, solo dígitos.
            digits_only = "".join(ch for ch in phone if ch.isdigit())
            user_data["ph"] = [_sha256(digits_only)]
        if country:
            user_data["country"] = [_sha256(country)]

        event = {
            "event_name": event_name,
            "event_time": int(time.time()),
            "event_id": event_id or uuid.uuid4().hex,
            "action_source": "website",
            "user_data": user_data,
        }
        if event_source_url:
            event["event_source_url"] = event_source_url
        if custom_data:
            event["custom_data"] = custom_data

        payload = {"data": [event]}

        url = (
            f"https://graph.facebook.com/{self.api_version}/"
            f"{self.pixel_id}/events?access_token={self.access_token}"
        )

        logger.info(
            f"Sending Meta Conversions API event '{event_name}' "
            f"(event_id={event['event_id']})"
        )
        logger.debug(f"Meta CAPI payload: {payload}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if 200 <= response.status_code < 300:
                    logger.info(
                        f"Meta CAPI event '{event_name}' accepted: {response.text}"
                    )
                    return True
                logger.error(
                    f"Meta CAPI returned {response.status_code}: {response.text}"
                )
                return False
        except Exception as e:
            # Nunca dejamos que un fallo de tracking rompa el flujo principal.
            logger.error(f"Error sending Meta CAPI event '{event_name}': {e}")
            return False


meta_pixel_service = MetaPixelService()
