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


def _empty_variant() -> Dict[str, Any]:
    """Counters por variante. Mantener sincronizado con `_migrate_state()`."""
    return {
        "views": 0,              # entró a la página de upsell
        "purchases": 0,          # cliqueó "Sí" Y el cobro fue PAID
        "declines": 0,           # cliqueó explícitamente "No, gracias"
        "advisor_requests": 0,   # cliqueó "Hablar con asesor" (FAB de WhatsApp)
        "revenue": 0.0,
    }


def _empty_state() -> Dict[str, Any]:
    """Estructura inicial vacía del archivo de stats."""
    return {
        "started_at": time.time(),
        "last_event_at": None,
        "variants": {
            "A": _empty_variant(),
            "B": _empty_variant(),
        },
    }


def _migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Asegura que el state cargado de disco tenga los campos nuevos.

    Cuando agregamos campos (ej: 'declines'), los archivos viejos en disco
    no los tienen. Acá los rellenamos con defaults sin perder data anterior.
    """
    state.setdefault("started_at", time.time())
    state.setdefault("last_event_at", None)
    state.setdefault("variants", {})
    for variant_key in ("A", "B"):
        existing = state["variants"].get(variant_key, {})
        merged = _empty_variant()
        merged.update({k: existing[k] for k in existing if k in merged})
        state["variants"][variant_key] = merged
    return state


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
        """Carga el state desde disco. Si no existe o está corrupto, arranca limpio.

        Aplica migración para agregar campos nuevos a archivos viejos sin
        perder los counts ya acumulados.
        """
        if not self.data_path.exists():
            logger.info(
                f"AB test stats file not found at {self.data_path}, starting fresh"
            )
            return
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self._state = _migrate_state(loaded)
            logger.info(f"AB test stats loaded from {self.data_path}")
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

    def record_decline(self, variant: Optional[str]) -> None:
        """Suma un click explícito en 'No, gracias' al contador de la variante."""
        if variant not in ("A", "B"):
            return
        with self._lock:
            self._state["variants"][variant]["declines"] += 1
            self._state["last_event_at"] = time.time()
            self._save_unsafe()

    def record_advisor_request(self, variant: Optional[str]) -> None:
        """Suma un click en 'Hablar con asesor' al contador de la variante.

        OJO: este NO suma a 'declines' ni a 'purchases' — es una métrica aparte
        ('aún no decidió, está pidiendo info'). Permite distinguir entre
        clientes que rechazan vs los que necesitan más info.
        """
        if variant not in ("A", "B"):
            return
        with self._lock:
            self._state["variants"][variant]["advisor_requests"] += 1
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

        def _per_variant(v: Dict[str, Any]) -> Dict[str, Any]:
            views = v["views"]
            purchases = v["purchases"]
            declines = v["declines"]
            advisor_requests = v["advisor_requests"]
            revenue = v["revenue"]
            # "Sin acción" = visitas que no clickearon NADA (cerraron pestaña).
            # Cualquier interacción (sí, no, asesor) cuenta como "tomó acción".
            # Puede dar negativo en casos de borde (cliente recarga después de
            # interactuar) — lo clampeamos a 0 para que no confunda en el dashboard.
            no_action = max(0, views - purchases - declines - advisor_requests)
            return {
                "views": views,
                "purchases": purchases,
                "declines": declines,
                "advisor_requests": advisor_requests,
                "no_action": no_action,
                "revenue": revenue,
                "conversion_rate": (purchases / views) if views > 0 else 0.0,
                "decline_rate": (declines / views) if views > 0 else 0.0,
                "advisor_rate": (advisor_requests / views) if views > 0 else 0.0,
                "revenue_per_visitor": (revenue / views) if views > 0 else 0.0,
            }

        a = _per_variant(state["variants"]["A"])
        b = _per_variant(state["variants"]["B"])

        # Diferencias relativas (%) para mostrar uplifts
        cr_uplift = ((b["conversion_rate"] / a["conversion_rate"]) - 1) * 100 \
            if a["conversion_rate"] > 0 else None
        rpv_uplift = ((b["revenue_per_visitor"] / a["revenue_per_visitor"]) - 1) * 100 \
            if a["revenue_per_visitor"] > 0 else None

        # Z-test simple sobre proporciones (CR). Solo es significativo con muestras grandes.
        confidence_pct, winner_by_cr = _two_proportion_confidence(
            a["purchases"], a["views"], b["purchases"], b["views"]
        )

        # El "ganador" se decide por RPV (revenue per visitor), no por CR sola.
        # Es lo correcto para A/B de precios: a veces precio bajo convierte más
        # pero rinde menos plata por visitante.
        if a["revenue_per_visitor"] == 0 and b["revenue_per_visitor"] == 0:
            winner_by_rpv = None
        elif a["revenue_per_visitor"] >= b["revenue_per_visitor"]:
            winner_by_rpv = "A"
        else:
            winner_by_rpv = "B"

        return {
            "started_at": state["started_at"],
            "last_event_at": state["last_event_at"],
            "variants": {"A": a, "B": b},
            "comparison": {
                "cr_uplift_pct": cr_uplift,
                "rpv_uplift_pct": rpv_uplift,
                "winner_by_cr": winner_by_cr,
                "winner_by_rpv": winner_by_rpv,
                "confidence_pct": confidence_pct,
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
