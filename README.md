# 🚀 Mentoría León - dLocal Go Payment API

API backend profesional para procesar pagos de **Mentoría León** con dLocal Go, con integración de webhooks.

## 📋 Características

- ✅ **Generación de links de pago** con dLocal Go
- ✅ **Dos planes de pago (USD)**:
  - **plan6**: 6 cuotas de USD 117 (total USD 702)
  - **plan9**: 9 cuotas de USD 87 (total USD 783)
- ✅ **Todos los métodos de pago** disponibles del país (tarjeta crédito/débito, efectivo, transferencia). Las cuotas aplican solo a tarjetas de crédito; otros métodos cobran el total de una sola vez.
- ✅ **Webhooks automáticos** para notificaciones de pago
- ✅ **Reenvío a webhook de terceros** (AutomatiChat, etc.)
- ✅ **Redirect URLs configurables** para páginas de éxito/error
- ✅ **Branding personalizable** en el checkout de dLocal

## 🏗️ Stack Tecnológico

- **Python 3.10+**
- **FastAPI** - Framework web moderno y rápido
- **Uvicorn** - Servidor ASGI
- **dLocal Go API** - Procesamiento de pagos
- **Pydantic** - Validación de datos
- **httpx** - Cliente HTTP asíncrono

> ⚠️ La API es **stateless** (no usa base de datos). Los pagos viven en dLocal; cualquier consulta histórica se hace contra la API de dLocal vía `GET /api/payment/{id}`.

## 📁 Estructura del Proyecto

```
.
├── main.py                 # Aplicación principal FastAPI
├── config.py               # Configuración y variables de entorno
├── models.py               # Modelos Pydantic
├── requirements.txt        # Dependencias Python
├── render.yaml             # Blueprint de deploy en Render
├── .env.example            # Plantilla de variables de entorno
├── services/
│   ├── dlocal_service.py   # Integración con dLocal API
│   └── webhook_service.py  # Manejo de webhooks
├── utils/
│   └── security.py         # Utilidades de seguridad (headers, auth)
├── .env                    # Variables de entorno locales (no incluido en repo)
└── README.md               # Este archivo
```

## 🔧 Configuración Local (Desarrollo)

### 1. Requisitos

- Python 3.10 o superior
- pip

### 2. Instalación

```bash
# Clonar o descargar el proyecto
cd "ruta/al/proyecto"

# Crear entorno virtual
python -m venv env

# Activar entorno virtual
# Windows:
env\Scripts\activate
# Linux/Mac:
source env/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# dLocal Go API Credentials
DLOCAL_API_KEY=tu_api_key_aqui
DLOCAL_SECRET_KEY=tu_secret_key_aqui
DLOCAL_API_URL=https://api-sbx.dlocalgo.com  # Sandbox
# DLOCAL_API_URL=https://api.dlocalgo.com    # Producción

# Webhook Configuration
THIRD_PARTY_WEBHOOK_URL=https://app.automatichat.com/api/webhook-scenario/TU_ID
APP_BASE_URL=http://localhost:8001  # En producción: https://tu-dominio.com

# dLocal Redirect URLs (TODAS OPCIONALES — si quedan vacías, dLocal usa su pantalla de estado)
# DLOCAL_SUCCESS_URL=https://tu-dominio.com/pago-exitoso
# DLOCAL_ERROR_URL=https://tu-dominio.com/pago-error
# DLOCAL_PENDING_URL=https://tu-dominio.com/pago-pendiente
# DLOCAL_CANCEL_URL=https://tu-dominio.com/pago-cancelado

# dLocal Checkout Branding
MERCHANT_NAME=Mentoría León
PAYMENT_DESCRIPTION=Mentoría León

# Application Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 4. Ejecutar

```bash
# En Windows
python main.py

# En Linux/Mac
python3 main.py
```

La API estará disponible en: `http://localhost:8001`

## 📡 Endpoints Principales

### 1. Health Check
```
GET /health
```
Verifica que la API esté funcionando.

### 2. Generar Link de Pago (JSON)
```
GET /api/pago?tel=TELEFONO&country=PAIS&type=TIPO
```

**Parámetros (todos opcionales):**
- `tel`: Número de teléfono (con código de país, ej: 5255123456789)
- `country`: Código del país (AR, MX, CO, CL, etc.). Default: `MX`
- `type`: Plan de pago. Sinónimos aceptados:
  - `plan6` / `6` / `6cuotas` → 6 cuotas de USD 117 (total USD 702) — **default**
  - `plan9` / `9` / `9cuotas` → 9 cuotas de USD 87 (total USD 783)

**Respuesta (ejemplo plan6):**
```json
{
  "payment_id": "DP-123456",
  "redirect_url": "https://checkout.dlocalgo.com/...",
  "status": "PENDING",
  "amount": 702.0,
  "currency": "USD",
  "installments": 6
}
```

### 3. Redirect Directo al Checkout
```
GET /pagar?tel=TELEFONO&country=PAIS&type=TIPO
```

Redirige automáticamente al usuario al checkout de dLocal.

### 4. Webhook de dLocal
```
POST /api/webhook/dlocal
```

Endpoint para recibir notificaciones de dLocal automáticamente.

### 5. Documentación Interactiva

Una vez corriendo, visita:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## 🚀 Deploy en Render

El repo incluye un **Render Blueprint** (`render.yaml`) listo para usar.

### Pasos rápidos

1. Tener el repo pusheado a GitHub.
2. En [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint** → seleccionar este repo.
3. Render detecta `render.yaml` y pide los valores de las variables marcadas como secret:
   - `DLOCAL_API_KEY`, `DLOCAL_SECRET_KEY`
   - `THIRD_PARTY_WEBHOOK_URL`
   - `APP_BASE_URL` (la dejás vacía y la completás después con la URL real de Render)
   - URLs de retorno (opcionales)
4. Esperar el primer build (~2-5 min). Cuando esté live, copiás la URL pública (ej: `https://mentoria-leon-api.onrender.com`).
5. Editás `APP_BASE_URL` con esa URL (con `https://`, sin slash final) → redeploy automático.
6. Health check final: `curl https://mentoria-leon-api.onrender.com/health`.

### Pasaje a producción

Cuando estés listo para procesar pagos reales, en Render → Environment:

```
DLOCAL_API_URL=https://api.dlocalgo.com
DLOCAL_API_KEY=<key_de_PRODUCCIÓN>
DLOCAL_SECRET_KEY=<secret_de_PRODUCCIÓN>
```

> ⚠️ **Plan Free de Render**: el servicio se duerme tras 15 min sin tráfico y tarda ~30-60s en despertar. Para producción seria, pasar a **Starter (USD 7/mes)** y evitar perder webhooks de dLocal.

## 🔐 Seguridad

- ✅ `.env` y secrets no se incluyen en el repositorio (gitignoreados).
- ✅ Variables sensibles cargadas vía dashboard de Render (no en código).
- ✅ Autenticación Bearer con dLocal Go.
- ✅ HTTPS automático provisto por Render (Let's Encrypt).

## 📊 Monitoreo

**En desarrollo:** los logs se muestran en consola.

**En Render:** panel del servicio → tab **Logs** (en vivo) o **Events** (deploys, restarts). También hay **Metrics** (CPU/RAM/respuestas).

## 🧪 Testing

### Probar Health Check
```bash
curl http://localhost:8001/health
```

### Probar Generación de Link
```bash
# Plan por defecto (plan6 - 6 cuotas de USD 117)
curl "http://localhost:8001/api/pago?tel=5255123456789&country=MX&type=plan6"

# Plan 9 cuotas de USD 87
curl "http://localhost:8001/api/pago?tel=5255123456789&country=MX&type=plan9"
```

### Probar Webhook Manualmente
```bash
curl -X POST http://localhost:8001/debug/test-webhook?payment_id=TEST123&status=PAID
```

## 📞 Soporte

Para problemas o dudas:

1. **Revisa los logs** en Render (tab "Logs") o en consola si corre local.
2. **Consulta la documentación** de dLocal Go.
3. **Verifica la configuración** del archivo `.env` (local) o de las env vars en Render.

## 📄 Licencia

Este proyecto es privado y de uso exclusivo para **Mentoría León**.

## 🎯 Autor

**Desarrollado para:** Mentoría León
**Año:** 2025

---

## 🔗 Links Útiles

- [dLocal Go Documentación](https://docs.dlocal.com/)
- [FastAPI Documentación](https://fastapi.tiangolo.com/)
- [Render — Blueprint Spec](https://render.com/docs/blueprint-spec)
- [Render — Variables de entorno](https://render.com/docs/configure-environment-variables)

---

**¡Listo para procesar pagos de manera profesional!** 💰🚀
