"""
Cache en memoria para resolver el flujo del upsell sin pedirle a dLocal Go.

¿Por qué hace falta?
- dLocal Go redirige al `success_url` SIN agregar query params (no manda
  payment_id, status, ni nada). Entonces, para identificar de qué pago vino
  el cliente, necesitamos meterle nosotros un identificador al success_url
  ANTES de mandar el create_payment.
- Como solo tenemos el `order_id` antes de mandar (lo generamos nosotros),
  usamos ese: success_url = "...?order_id={order_id}".
- Después de crear el checkout, guardamos en este cache la info necesaria
  para procesar el upsell (payment_id, merchant_checkout_token).
- Cuando el cliente vuelve a /upsell?order_id=..., levantamos del cache
  el merchant_checkout_token sin tener que volver a llamar a dLocal.

Limitaciones:
- Es in-memory: si el server se reinicia (ej: Render free tier que duerme
  después de 15 min), el cache se pierde. La ventana de upsell de dLocal
  es de 15 min igual, así que en la práctica esto no es crítico, pero
  conviene migrar a Redis si se quiere robustez total en el futuro.
- Es thread-safe (usa Lock) pero NO process-safe. Funciona OK con un solo
  worker de uvicorn.
"""
import logging
import time
from threading import Lock
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class UpsellCache:
    """Mapping en memoria de order_id → datos del checkout para procesar upsells."""

    def __init__(self, ttl_seconds: int = 1800):
        # 30 min de TTL: suficiente buffer sobre los 15 min de ventana de dLocal.
        self._cache: Dict[str, dict] = {}
        self._lock = Lock()
        self.ttl_seconds = ttl_seconds

    def store(
        self,
        order_id: str,
        payment_id: str,
        merchant_checkout_token: Optional[str],
        ab_variant: Optional[str] = None,
    ) -> None:
        """Guarda el mapping cuando se crea un checkout con allow_upsell=true.

        ab_variant: si hay A/B test activo, va "A" o "B". Determina qué precio
        se le muestra y cobra al cliente. Sticky: se asigna acá y nunca cambia
        para ese order_id, aunque el cliente refresque o vuelva.
        """
        with self._lock:
            self._cache[order_id] = {
                "payment_id": payment_id,
                "merchant_checkout_token": merchant_checkout_token,
                "ab_variant": ab_variant,
                "stored_at": time.time(),
            }
            self._cleanup_expired_unsafe()
            logger.info(
                f"Upsell cache stored: order_id={order_id} → "
                f"payment_id={payment_id}, has_token={bool(merchant_checkout_token)}, "
                f"ab_variant={ab_variant or '-'}, cache_size={len(self._cache)}"
            )

    def get_by_order_id(self, order_id: str) -> Optional[dict]:
        """Busca por el order_id que dLocal nos devuelve en el success_url."""
        with self._lock:
            entry = self._cache.get(order_id)
            if not entry:
                return None
            if time.time() - entry["stored_at"] > self.ttl_seconds:
                self._cache.pop(order_id, None)
                logger.info(f"Upsell cache entry expired for order_id={order_id}")
                return None
            return dict(entry)  # copia defensiva

    def get_by_payment_id(self, payment_id: str) -> Optional[dict]:
        """Búsqueda inversa por payment_id (usada en /api/upsell/click)."""
        with self._lock:
            now = time.time()
            for entry in self._cache.values():
                if entry["payment_id"] == payment_id:
                    if now - entry["stored_at"] > self.ttl_seconds:
                        return None
                    return dict(entry)
            return None

    def _cleanup_expired_unsafe(self) -> None:
        """Limpia entradas vencidas. Llamar SIEMPRE con el lock tomado."""
        now = time.time()
        expired = [
            k for k, v in self._cache.items()
            if now - v["stored_at"] > self.ttl_seconds
        ]
        for k in expired:
            self._cache.pop(k, None)


upsell_cache = UpsellCache()
