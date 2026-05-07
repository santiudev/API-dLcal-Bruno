"""
Modelos Pydantic para validación de datos
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Dict, Any


class PaymentRequest(BaseModel):
    """Request para crear un pago"""
    phone_number: str = Field(..., description="Número de teléfono del cliente")
    country: str = Field(..., min_length=2, max_length=2, description="Código ISO del país (ej: BR, MX, AR)")
    payment_type: Literal["plan6", "plan9", "contado"] = Field(
        ...,
        description="Tipo de pago: plan6 (6x USD 117), plan9 (9x USD 87) o contado (USD 597 pago único)"
    )
    
    # Campos opcionales adicionales del cliente
    customer_name: Optional[str] = Field(None, description="Nombre del cliente")
    customer_email: Optional[str] = Field(None, description="Email del cliente")
    
    @field_validator('country')
    @classmethod
    def validate_country(cls, v: str) -> str:
        """Valida y convierte el país a mayúsculas"""
        return v.upper()


class PaymentResponse(BaseModel):
    """Response al crear un pago"""
    payment_id: str = Field(..., description="ID del pago generado")
    redirect_url: str = Field(..., description="URL para redirigir al cliente al checkout")
    status: str = Field(..., description="Estado del pago")
    amount: float = Field(..., description="Monto del pago")
    currency: str = Field(..., description="Moneda del pago")
    installments: int = Field(..., description="Número de cuotas")


class WebhookNotification(BaseModel):
    """Notificación webhook de dLocal Go"""
    # dLocal Go puede enviar 'payment_id' o 'id'
    payment_id: Optional[str] = Field(None, description="Payment ID")
    id: Optional[str] = Field(None, description="Payment ID alternativo")
    status: Optional[str] = Field(None, description="Estado del pago")
    status_detail: Optional[str] = Field(None, description="Detalle del estado")
    status_code: Optional[str] = Field(None, description="Código de estado")
    amount: Optional[float] = None
    currency: Optional[str] = None
    country: Optional[str] = None
    payment_method_id: Optional[str] = None
    payment_method_type: Optional[str] = None
    payment_method_flow: Optional[str] = None
    created_date: Optional[str] = None
    approved_date: Optional[str] = None
    order_id: Optional[str] = None
    notification_url: Optional[str] = None
    
    # Campos adicionales que pueden venir en el webhook
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    def get_payment_id(self) -> Optional[str]:
        """Obtiene el payment_id del campo que esté presente"""
        return self.payment_id or self.id


class PaymentDetails(BaseModel):
    """Detalles completos de un pago obtenidos de dLocal"""
    id: str
    status: str
    status_detail: Optional[str] = None
    status_code: Optional[str] = None
    amount: float
    currency: str
    country: str
    payment_method_id: Optional[str] = None
    payment_method_type: Optional[str] = None
    payment_method_flow: Optional[str] = None
    payer: Optional[Dict[str, Any]] = None
    order_id: str
    description: Optional[str] = None
    created_date: str
    approved_date: Optional[str] = None
    installments: Optional[int] = None
    installments_amount: Optional[float] = None
    callback_url: Optional[str] = None
    notification_url: Optional[str] = None
    
    # Campos adicionales
    raw_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Datos raw completos de dLocal")


class HealthResponse(BaseModel):
    """Response del health check"""
    status: str = "ok"
    timestamp: str
    version: str = "1.0.0"

