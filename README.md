# 🚀 Mentoría León - dLocal Go Payment API

API backend profesional para procesar pagos de **Mentoría León** con dLocal Go, con integración de webhooks.

## 📋 Características

- ✅ **Generación de links de pago** con dLocal Go
- ✅ **Tres planes de pago (USD)**:
  - **plan6**: 6 cuotas de USD 117 (total USD 702)
  - **plan9**: 9 cuotas de USD 87 (total USD 783)
  - **contado**: Pago único de USD 597
- ✅ **Todos los métodos de pago** disponibles del país (tarjeta crédito/débito, efectivo, transferencia). Las cuotas aplican solo a tarjetas de crédito; otros métodos cobran el total de una sola vez.
- ✅ **Webhooks automáticos** para notificaciones de pago
- ✅ **Reenvío a webhook de terceros** (AutomatiChat, etc.)
- ✅ **Redirect URLs configurables** para páginas de éxito/error
- ✅ **Branding personalizable** en el checkout de dLocal
- ✅ **One-Click Upsell (One Time Offer)**: cobro extra one-click después del pago principal sin volver a pedir datos de tarjeta (ventana de 15 minutos)

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

# One-Click Upsell (One Time Offer)
# Requiere que dLocal Go habilite la feature en la cuenta del merchant.
# Cuando UPSELL_ENABLED=true, el checkout solo permite tarjetas de crédito/débito.
UPSELL_ENABLED=true
UPSELL_AMOUNT=197
UPSELL_DESCRIPTION=Mentoría León - Extensión de 3 meses

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
  - `contado` / `single` / `597` → Pago único de USD 597

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

### 5. One-Click Upsell (One Time Offer)

Cuando `UPSELL_ENABLED=true` está activo en `.env`, todos los checkouts se crean con `allow_upsell: true`. La respuesta del create payment incluye un `merchant_checkout_token`:

```json
{
  "payment_id": "DP-123456",
  "redirect_url": "https://checkout.dlocalgo.com/...",
  "status": "PENDING",
  "amount": 702.0,
  "currency": "USD",
  "installments": 6,
  "merchant_checkout_token": "abc123..."
}
```

> ⚠️ Con upsell habilitado, el checkout **solo permite tarjetas de crédito/débito** (no efectivo, no transferencia). Es una limitación de dLocal Go.

Después del pago exitoso, dLocal redirige al cliente al `success_url` (página de Bruno con la oferta upsell). Si acepta, hay que pegarle a uno de estos dos endpoints **dentro de los 15 minutos** del pago original:

#### POST `/api/upsell/confirm/{merchant_checkout_token}`
Body opcional para overridear los valores fijos de `.env`:
```json
{ "amount": 197, "description": "Extensión de 3 meses", "order_id": "TEST_OTO_1", "installments": 3 }
```

#### GET `/api/upsell/confirm/{merchant_checkout_token}?amount=197&description=...&order_id=...&installments=3`
Versión simple (todos los query params opcionales). Útil para disparar el cobro desde un `<a href>` o un fetch sin body.

> 🧪 **`installments` es experimental**: dLocal Go no documenta cuotas para el endpoint de upsell. Si el cobro falla con `installments > 1`, hay que cobrar el upsell en 1 sola cuota (omitir el parámetro).

#### GET `/api/upsell/click/{payment_id}` — endpoint para el botón de la landing

Endpoint pensado específicamente para que sea el destino del botón **"Sí, sumar 3 meses"** (o equivalente) en la página de upsell. Recibe el `payment_id` que dLocal mete automáticamente en el query string del `success_url` y se encarga de todo:

1. Busca el `merchant_checkout_token` consultando el payment a dLocal
2. Cobra el upsell con los valores fijos de `.env` (`UPSELL_AMOUNT`, `UPSELL_DESCRIPTION`)
3. Redirige al cliente:
   - **Si paga OK** → `UPSELL_SUCCESS_URL` (o página HTML de éxito si no está seteada)
   - **Si falla con retry posible** → `redirect_url` que devuelve dLocal (cliente reintenta con otra tarjeta)
   - **Si falla sin retry** → `UPSELL_ERROR_URL` (o página HTML de error si no está seteada)

#### GET `/upsell/{payment_id}` — página HTML de la oferta (servida desde la API)

La API sirve directamente la página de upsell con el diseño completo (oscuro/violeta con timer y sello "SOLO UNA VEZ"). El template renderiza con los datos del cobro y los botones ya cableados.

**Para que dLocal redirija al cliente acá después del pago principal, configurá:**

```env
DLOCAL_SUCCESS_URL=https://dlocal.brunoelleon.com/upsell
```

> ⚠️ **dLocal Go redirige al success_url SIN agregar query params automáticamente.** Por eso, en `dlocal_service.create_payment()` la API inyecta automáticamente el `order_id` como query param antes de mandar el create_payment. El cliente termina redirigido a `https://dlocal.brunoelleon.com/upsell?order_id=order_xxxxx`.
>
> El `order_id` se usa como llave para buscar en un **cache en memoria** (`services/upsell_cache.py`) el `payment_id` y el `merchant_checkout_token` que devolvió dLocal al crear el checkout. El cache tiene TTL de 30 minutos (suficiente buffer sobre los 15 min de ventana de upsell que da dLocal).

> ⚠️ **Limitación del cache en memoria**: si el server se reinicia entre que el cliente paga y entra al `/upsell`, el cache se pierde y aparece el mensaje "La oferta ya no está disponible". En Render Free Plan, esto puede pasar si el server estuvo dormido. Para producción seria, conviene **upgradear a Render Starter** (no se duerme) o migrar el cache a Redis.

#### Personalizar la página

Variables del `.env`:

```env
UPSELL_AMOUNT=197                                  # Precio que se muestra
UPSELL_DESCRIPTION=Mentoría León - Extensión 3 meses
UPSELL_DECLINE_URL=https://bruno.11demayo.com/graciasn   # Botón "No, gracias"
UPSELL_SUCCESS_URL=https://...                     # Después del cobro OK
UPSELL_ERROR_URL=https://...                       # Después de cobro fallido sin retry
```

Si querés cambiar el copy del título/textos, editar directo en `templates/upsell.html`.

### 6. Meta Pixel + Conversions API

Tracking dual: **Pixel del lado cliente** (PageView, ViewContent, InitiateCheckout) + **Conversions API server-side** (Purchase) para deduplicación y robustez contra ad-blockers.

```env
META_PIXEL_ID=3592174154252037
META_ACCESS_TOKEN=EAAU...   # IMPORTANTE: secreto, nunca commitearlo
```

Eventos disparados automáticamente:

| Evento | Lado | Cuándo |
|---|---|---|
| `PageView` | Cliente | Al cargar `/upsell/{id}` |
| `ViewContent` | Cliente | Al cargar `/upsell/{id}` con `value=197, currency=USD` |
| `InitiateCheckout` | Cliente | Al hacer clic en "Sí, sumar 3 meses" |
| `Purchase` | Server (CAPI) | Cuando dLocal confirma el cobro como `PAID` |

El `event_id` del `Purchase` es el `payment_id` del upsell devuelto por dLocal, así que es estable y deduplicable.

### 7. A/B Test de precio del upsell

Tracking 50/50 transparente para comparar dos precios del upsell sin tocar código en cada experimento. La asignación de variante es **sticky por `order_id`** (cada cliente siempre ve el mismo precio aunque refresque o vuelva).

```env
UPSELL_AB_TEST_ENABLED=true   # Encender/apagar el test sin redeploy
UPSELL_AMOUNT=197             # Variante A (control)
UPSELL_AMOUNT_VARIANT_B=147   # Variante B (prueba)
```

Cuando está activo:
- Cada nuevo checkout se asigna al azar 50/50 a variante A o B
- La página `/upsell` muestra el precio correspondiente
- El cobro a dLocal lleva `[Variant A]` o `[Variant B]` en el `description`
- El evento `Purchase` de Meta CAPI lleva `custom_data.variant: A|B` y `content_name: "Upsell Extension 3 meses (Variant X)"`

**Cómo medir conversión por variante:**

| Lugar | Cómo filtrar |
|---|---|
| Logs de Render | Buscar `ab_variant=A` o `ab_variant=B` |
| Panel de dLocal | Filtrar pagos por description que contenga `[Variant A]` o `[Variant B]` |
| Meta Events Manager | Crear conversión custom filtrando `custom_data.variant = "A"` o `"B"` |

**Cuando termines el test:**
1. Setear `UPSELL_AB_TEST_ENABLED=false`
2. Si la variante B ganó, mover su precio a `UPSELL_AMOUNT` y ese queda como nuevo default

#### Dashboard del A/B test — `GET /admin/ab-test/stats`

Dashboard interno con resultados en tiempo real, protegido con HTTP Basic Auth.

```env
ADMIN_USERNAME=tu_usuario
ADMIN_PASSWORD=password_fuerte
AB_TEST_DATA_PATH=/data/ab_test_stats.json   # En Render: requiere Disk montado en /data
```

URL: `https://dlocal.brunoelleon.com/admin/ab-test/stats` — el browser pide usuario/password.

Métricas que muestra **por variante**:
- **Vistas** — entró a la página de upsell
- **Compras** — clickeó "Sí" Y el cobro fue PAID
- **Rechazos** — clickeó explícitamente "No, gracias"
- **Sin acción** — vio la página y cerró la pestaña sin elegir nada (calculado: `vistas - compras - rechazos`)
- **Conversion rate, decline rate, revenue total, revenue per visitor**

Métricas globales:
- **Ganador por revenue per visitor** (la métrica correcta para A/B de precios — un precio bajo puede convertir más pero rendir menos plata)
- **Confianza estadística** vía z-test de dos proporciones (recién a partir de ~95% se considera confiable)

Cómo interpretar:
- **Decline rate alto** → el precio se percibe caro (la oferta no convence)
- **Sin acción alto** → el copy o el diseño no enganchan (ni siquiera consideran responder)

Endpoints relacionados:
- `GET /admin/ab-test/stats` → dashboard HTML
- `GET /admin/ab-test/stats.json` → mismo summary en JSON (útil para scripts)
- `POST /admin/ab-test/reset` → resetea TODOS los counters a cero (también disponible como botón "↻ RESET TOTAL" en el dashboard, con doble confirmación — pensado para limpiar después de QA antes de salir a producción real)

Si `ADMIN_USERNAME`/`PASSWORD` no están seteados, los endpoints devuelven `503` (acceso deshabilitado por seguridad).

#### Persistencia del A/B test

Las stats se guardan en `AB_TEST_DATA_PATH` (default `/data/ab_test_stats.json`). Para que sobreviva redeploys de Render, hay que montar un Render Disk en `/data` (ver `render.yaml`). Render Disk cuesta **$1/mes** por 1GB y NO está disponible en plan Free — hay que estar al menos en Starter ($7/mes).

Si querés correr local, cambiá el path en `.env` a algo tipo `./data/ab_test_stats.json`.

**Respuesta** (igual en ambos):
```json
{
  "payment_id": "DP-789012",
  "status": "PAID",
  "amount": 97.0,
  "currency": "USD",
  "description": "Mentoría León - Bonus OTO",
  "order_id": "upsell_abc123",
  "merchant_checkout_token": "abc123...",
  "redirect_url": null
}
```

Si el cobro one-click falla (tarjeta rechazada, etc.), `redirect_url` viene con un link al checkout de dLocal para que el cliente complete el pago con otro método.

### 6. Documentación Interactiva

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

# Pago único de USD 597
curl "http://localhost:8001/api/pago?tel=5255123456789&country=MX&type=contado"
```

### Probar Webhook Manualmente
```bash
curl -X POST http://localhost:8001/debug/test-webhook?payment_id=TEST123&status=PAID
```

### Probar One-Click Upsell
```bash
# 1) Crear el checkout principal y guardar el merchant_checkout_token de la respuesta
curl "http://localhost:8001/api/pago?country=AR&type=plan6"

# 2) Después de pagar el checkout, confirmar el upsell (≤ 15 min)
# Opción A: GET (rápido para probar)
curl "http://localhost:8001/api/upsell/confirm/{TOKEN_DEL_PASO_1}"

# Opción B: POST con overrides
curl -X POST "http://localhost:8001/api/upsell/confirm/{TOKEN_DEL_PASO_1}" \
  -H "Content-Type: application/json" \
  -d '{"amount": 50, "description": "Bonus pack", "order_id": "TEST_OTO_1"}'
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
