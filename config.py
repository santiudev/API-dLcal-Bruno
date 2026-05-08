"""
Configuración de la aplicación y variables de entorno
"""
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings para la aplicación cargados desde variables de entorno"""
    
    # dLocal Go API Credentials (solo 2 keys necesarias)
    dlocal_api_key: str
    dlocal_secret_key: str
    dlocal_api_url: str = "https://api-sbx.dlocalgo.com"  # Sandbox por defecto
    
    # Webhook Configuration
    third_party_webhook_url: str
    app_base_url: str
    
    # dLocal Redirect URLs (todas opcionales).
    # Si quedan en None/"", dLocal muestra su propia pantalla de estado y no redirige.
    dlocal_success_url: Optional[str] = None  # URL cuando el pago es exitoso
    dlocal_error_url: Optional[str] = None    # URL cuando el pago falla
    dlocal_pending_url: Optional[str] = None  # URL cuando el pago queda pendiente
    dlocal_cancel_url: Optional[str] = None   # URL cuando el usuario cancela
    
    # dLocal Checkout Branding (títulos que aparecen en el checkout)
    merchant_name: str = "Mentoría León"  # Nombre que aparece en el checkout
    payment_description: str = "Mentoría León"     # Descripción del pago

    # One-Click Upsell (One Time Offer)
    # Requiere que dLocal Go habilite la feature en la cuenta del merchant.
    # Cuando está activo, todos los checkouts se crean con allow_upsell=true,
    # por lo que el checkout solo permitirá tarjetas de crédito/débito.
    # Hay una ventana de 15 minutos desde el pago original para confirmar el upsell.
    upsell_enabled: bool = True
    upsell_amount: float = 197.00                                          # Monto del producto upsell (USD) — variante A (control)
    upsell_description: str = "Mentoría León - Extensión de 3 meses"       # Descripción del cargo upsell

    # A/B test de precio (transparente al cliente, sticky por order_id 50/50).
    # Si está habilitado, cada nuevo checkout queda asignado al azar a variante A
    # ($197) o B (precio configurable abajo). La variante se guarda en el cache
    # del upsell y se respeta a lo largo de todo el flujo del cliente.
    upsell_ab_test_enabled: bool = False
    upsell_amount_variant_b: float = 147.00  # Precio alternativo (USD) para la variante B

    # URLs a las que se redirige al cliente DESPUÉS de hacer clic en el botón
    # de upsell (endpoint /api/upsell/click/{payment_id}). Si quedan vacías,
    # la API devuelve una página HTML simple de fallback.
    upsell_success_url: Optional[str] = None   # Cuando el upsell se cobra OK
    upsell_error_url: Optional[str] = None     # Cuando el upsell falla y NO hay redirect_url de dLocal
    upsell_decline_url: Optional[str] = None   # A donde va el botón "No, gracias" de la página de oferta

    # Meta (Facebook) Pixel + Conversions API
    # El pixel_id se inyecta en el HTML para tracking del lado cliente.
    # El access_token se usa server-side para mandar eventos via Conversions API
    # (más confiable porque no se ve afectado por bloqueadores ni iOS 14.5+).
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    # Endpoint de Conversions API. Versión congelada para evitar breaking changes
    # cuando Meta saca una nueva versión de Graph API.
    meta_graph_api_version: str = "v18.0"

    # Dashboard del A/B test (Basic Auth)
    # Si querés ver las stats en /admin/ab-test/stats hay que setear estas variables.
    # Si quedan vacías, el endpoint devuelve 401 — el dashboard no es accesible.
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    # Path donde se persisten los counters del A/B test. En Render, hay que
    # montar un Disk en /data y dejar este path así para que sobreviva redeploys.
    ab_test_data_path: str = "/data/ab_test_stats.json"

    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Instancia global de configuración
settings = Settings()

