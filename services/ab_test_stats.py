"""
Servicio de estadísticas del A/B test del upsell.

Cuenta vistas y compras por variante, persiste a disco como JSON, y expone
un summary con conversion rate, revenue, etc.

Diseño:
- Persistencia: JSON local (path configurable). En Render se monta como Disk.
- Concurrency: thread-safe con un Lock.
- Auto-save: después de cada update se reescribe el archivo (los volúmenes
  son chicos así que no es problema de performance, y es más seguro que
  esperar a un flush periódico).
- Recovery: si el archivo no existe o está corrupto, arranca desde cero.
"""
import json
import logging
import math
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _empty_state() -> Dict[str, Any]:
    """Estructura inicial vacía del archivo de stats."""
    return {
        "started_at": time.time(),
        "last_event_at": None,
        "variants": {
            "A": {"views": 0, "purchases": 0, "revenue": 0.0},
            "B": {"views": 0, "purchases": 0, "revenue": 0.0},
        },
    }


class ABTestStats:
    """Contador persistente de vistas/compras/revenue por variante."""

    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self._lock = Lock()
        self._state: Dict[str, Any] = _empty_state()
        self._load()

    # -----------------------------
    # Persistencia
    # -----------------------------
    def _load(self) -> None:
        """Carga el state desde disco. Si no existe o está corrupto, arranca limpio."""
        if not self.data_path.exists():
            logger.info(
                f"AB test stats file not found at {self.data_path}, starting fresh"
            )
            return
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Validar estructura mínima
            if "variants" in loaded and "A" in loaded["variants"] and "B" in loaded["variants"]:
                self._state = loaded
                logger.info(f"AB test stats loaded from {self.data_path}")
            else:
                logger.warning(
                    f"AB test stats file at {self.data_path} has unexpected schema, ignoring"
                )
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Could not load AB test stats from {self.data_path}: {e}")

    def _save_unsafe(self) -> None:
        """Escribe el state a disco. SIEMPRE llamar con el lock tomado."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            # Write-rename atómico para evitar corrupción en caso de crash a mitad
            tmp_path = self.data_path.with_suffix(self.data_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self.data_path)
        except OSError as e:
            # Persistencia best-effort: si falla, no rompemos el flujo principal.
            logger.error(f"Could not save AB test stats to {self.data_path}: {e}")

    # -----------------------------
    # Recording
    # -----------------------------
    def record_view(self, variant: Optional[str]) -> None:
        """Suma una vista al contador de la variante. Ignora si variant es None."""
        if variant not in ("A", "B"):
            return
        with self._lock:
            self._state["variants"][variant]["views"] += 1
            self._state["last_event_at"] = time.time()
            self._save_unsafe()

    def record_purchase(self, variant: Optional[str], amount: float) -> None:
        """Suma una compra (con su monto) al contador de la variante."""
        if variant not in ("A", "B"):
            return
        with self._lock:
            v = self._state["variants"][variant]
            v["purchases"] += 1
            v["revenue"] = round(float(v["revenue"]) + float(amount), 2)
            self._state["last_event_at"] = time.time()
            self._save_unsafe()

    def reset(self) -> None:
        """Resetea todas las stats a cero. Útil cuando empieza un test nuevo."""
        with self._lock:
            self._state = _empty_state()
            self._save_unsafe()

    # -----------------------------
    # Summary / análisis
    # -----------------------------
    def get_summary(self) -> Dict[str, Any]:
        """
        Devuelve un summary completo: counts, conversion rates, revenue,
        diferencias relativas, ganador y nivel de confianza estadística básico.
        """
        with self._lock:
            state = json.loads(json.dumps(self._state))  # copia profunda

        a = state["variants"]["A"]
        b = state["variants"]["B"]

        a_cr = (a["purchases"] / a["views"]) if a["views"] > 0 else 0.0
        b_cr = (b["purchases"] / b["views"]) if b["views"] > 0 else 0.0

        # Revenue per visitor (RPV): mejor métrica que CR sola para A/B test de
        # precios — captura el trade-off "más conversiones a menos plata".
        a_rpv = (a["revenue"] / a["views"]) if a["views"] > 0 else 0.0
        b_rpv = (b["revenue"] / b["views"]) if b["views"] > 0 else 0.0

        # Diferencias relativas
        cr_uplift = ((b_cr / a_cr) - 1) * 100 if a_cr > 0 else None
        rpv_uplift = ((b_rpv / a_rpv) - 1) * 100 if a_rpv > 0 else None

        # Z-test simple sobre proporciones (CR). Devuelve nivel de confianza
        # aproximado. Solo significa algo si hay suficientes muestras.
        confidence_pct, winner_by_cr = _two_proportion_confidence(
            a["purchases"], a["views"], b["purchases"], b["views"]
        )

        # Para revenue, el "ganador" se decide por RPV (revenue per visitor),
        # no por CR. Es lo correcto para A/B de precios.
        if a_rpv == 0 and b_rpv == 0:
            winner_by_rpv = None
        elif a_rpv >= b_rpv:
            winner_by_rpv = "A"
        else:
            winner_by_rpv = "B"

        return {
            "started_at": state["started_at"],
            "last_event_at": state["last_event_at"],
            "variants": {
                "A": {
                    **a,
                    "conversion_rate": a_cr,
                    "revenue_per_visitor": a_rpv,
                },
                "B": {
                    **b,
                    "conversion_rate": b_cr,
                    "revenue_per_visitor": b_rpv,
                },
            },
            "comparison": {
                "cr_uplift_pct": cr_uplift,         # +X% si B convierte mejor en %
                "rpv_uplift_pct": rpv_uplift,       # +X% si B trae más plata por visitante
                "winner_by_cr": winner_by_cr,       # quien convierte más
                "winner_by_rpv": winner_by_rpv,     # quien trae más revenue (lo que importa para precio)
                "confidence_pct": confidence_pct,   # cuán confiable es la diferencia (0-99.9%)
            },
        }


def _two_proportion_confidence(
    a_success: int, a_total: int, b_success: int, b_total: int
) -> tuple[Optional[float], Optional[str]]:
    """
    Z-test aproximado de dos proporciones independientes. Devuelve (confianza%, ganador).

    Nota: es una aproximación rápida que asume distribución normal. Para tamaños
    de muestra >30 por variante, es bastante razonable. No reemplaza un análisis
    bayesiano serio pero sirve para tomar decisiones operativas día a día.
    """
    if a_total < 1 or b_total < 1:
        return None, None
    if a_success + b_success == 0:
        return None, None

    p_a = a_success / a_total
    p_b = b_success / b_total
    p_pool = (a_success + b_success) / (a_total + b_total)

    se = math.sqrt(p_pool * (1 - p_pool) * (1 / a_total + 1 / b_total))
    if se == 0:
        return None, None

    z = (p_b - p_a) / se
    # CDF normal estándar via función de error
    confidence = (1 + math.erf(abs(z) / math.sqrt(2))) / 2
    confidence_pct = round(confidence * 100, 2)
    winner = "B" if p_b > p_a else "A"
    return confidence_pct, winner


# Singleton inicializado al importar. El path lo lee de settings al final del módulo.
from config import settings  # noqa: E402

ab_test_stats = ABTestStats(data_path=settings.ab_test_data_path)
