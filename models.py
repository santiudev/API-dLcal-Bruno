"""
Modelos Pydantic para validación de datos
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Dict, Any


class PaymentRequest(BaseModel):
    """Request para crear un pago"""
    phone_number: Optional[str] = Field(
        None,
        description="Número de teléfono del cliente (opcional; si no se envía, el checkout queda sin tel precargado)",
    )
    country: str = Field(..., min_length=2, max_length=2, description="Código ISO del país (ej: BR, MX, AR)")
    payment_type: Literal["plan6", "plan9", "contado", "lead300"] = Field(
        ...,
        description="Tipo de pago: plan6 (6x USD 117), plan9 (9x USD 87), contado (USD 597) o lead300 (USD 300 único)"
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
    # Token necesario para confirmar un upsell asociado a este checkout.
    # Solo viene presente cuando el checkout se cre\u00f3 con allow_upsell=true.
    merchant_checkout_token: Optional[str] = Field(
        None,
        description="Token para confirmar el cobro de un upsell sobre este checkout (allow_upsell=true)"
    )


class UpsellRequest(BaseModel):
    """Request opcional para confirmar un upsell con datos custom (POST con body)."""
    # Todos opcionales: si no se mandan, se usan los valores fijos de config (.env).
    amount: Optional[float] = Field(None, description="Monto del upsell (override del valor de config)")
    description: Optional[str] = Field(None, description="Descripción del upsell (override del valor de config)")
    order_id: Optional[str] = Field(None, description="Order ID del upsell (si no se manda se genera uno)")
    # EXPERIMENTAL: cuotas en el upsell. dLocal Go no documenta este campo en el
    # endpoint de upsell. Lo mandamos igual y vemos si lo respeta en sandbox.
    # Si dLocal lo rechaza, hay que cobrar el upsell en 1 sola cuota.
    installments: Optional[int] = Field(
        None,
        ge=1,
        description="(Experimental) Cantidad de cuotas a cobrar el upsell con tarjeta de crédito"
    )


class UpsellResponse(BaseModel):
    """Response al confirmar un upsell."""
    payment_id: str = Field(..., description="ID del pago de upsell generado por dLocal")
    status: str = Field(..., description="Estado del pago de upsell (PAID, REJECTED, etc.)")
    amount: float = Field(..., description="Monto cobrado en el upsell")
    currency: str = Field(..., description="Moneda del cobro")
    description: str = Field(..., description="Descripción del cargo")
    order_id: str = Field(..., description="Order ID del upsell")
    merchant_checkout_token: str = Field(..., description="Token del checkout original al que se asoció el upsell")
    # Si el cobro one-click falla, dLocal devuelve una redirect_url donde el
    # cliente puede completar el pago con otro método.
    redirect_url: Optional[str] = Field(
        None,
        description="URL de fallback si el cobro one-click falla y el cliente debe reintentar manualmente"
    )


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

