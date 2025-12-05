"""
Configuración de la aplicación y variables de entorno
"""
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
    
    # dLocal Redirect URLs (páginas de retorno después del pago)
    dlocal_success_url: str  # URL cuando el pago es exitoso
    dlocal_error_url: str    # URL cuando el pago falla
    dlocal_pending_url: str  # URL cuando el pago queda pendiente
    dlocal_cancel_url: str   # URL cuando el usuario cancela
    
    # dLocal Checkout Branding (títulos que aparecen en el checkout)
    merchant_name: str = "Trading Nivel Inicial - Bruno el León"  # Nombre que aparece en el checkout
    payment_description: str = "Pago de servicio"     # Descripción del pago
    
    # Google Sheets Configuration
    google_sheets_credentials_file: str = "credentials.json"
    google_sheets_name: str = "Rejected Payments"  # Cambio de nombre sugerido
    google_sheets_worksheet: str = "Sheet1"
    
    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Instancia global de configuración
settings = Settings()

