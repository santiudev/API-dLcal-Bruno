# 🚀 Bruno - dLocal Go Payment API

API backend profesional para procesar pagos con dLocal Go, con integración de webhooks y registro automático en Google Sheets.

## 📋 Características

- ✅ **Generación de links de pago** con dLocal Go
- ✅ **Dos modalidades de pago**: Cuotas (12x $497 USD) o Pago único ($497 USD)
- ✅ **Webhooks automáticos** para notificaciones de pago
- ✅ **Registro en Google Sheets** de todos los pagos (PENDING, PAID, REJECTED, etc.)
- ✅ **Reenvío a webhook de terceros** (AutomatiChat, etc.)
- ✅ **Redirect URLs configurables** para páginas de éxito/error
- ✅ **Branding personalizable** en el checkout de dLocal

## 🏗️ Stack Tecnológico

- **Python 3.10+**
- **FastAPI** - Framework web moderno y rápido
- **Uvicorn** - Servidor ASGI
- **dLocal Go API** - Procesamiento de pagos
- **Google Sheets API** - Persistencia de datos
- **Pydantic** - Validación de datos
- **httpx** - Cliente HTTP asíncrono

## 📁 Estructura del Proyecto

```
.
├── main.py                 # Aplicación principal FastAPI
├── config.py               # Configuración y variables de entorno
├── models.py               # Modelos Pydantic
├── requirements.txt        # Dependencias Python
├── services/
│   ├── dlocal_service.py   # Integración con dLocal API
│   ├── sheets_service.py   # Integración con Google Sheets
│   └── webhook_service.py  # Manejo de webhooks
├── utils/
│   └── security.py         # Utilidades de seguridad (headers, auth)
├── .env                    # Variables de entorno (no incluido en repo)
├── credentials.json        # Credenciales Google Sheets (no incluido en repo)
├── DEPLOY_GUIDE.md        # Guía completa de deployment
└── README.md              # Este archivo
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

# dLocal Redirect URLs
DLOCAL_SUCCESS_URL=https://tu-dominio.com/pago-exitoso
DLOCAL_ERROR_URL=https://tu-dominio.com/pago-error
DLOCAL_PENDING_URL=https://tu-dominio.com/pago-pendiente
DLOCAL_CANCEL_URL=https://tu-dominio.com/pago-cancelado

# dLocal Checkout Branding
MERCHANT_NAME=ALQUIMIA - Johnny Abraham
PAYMENT_DESCRIPTION=Pago de servicio

# Google Sheets Configuration
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_SHEETS_NAME=Rejected Payments
GOOGLE_SHEETS_WORKSHEET=Sheet1

# Application Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 4. Configurar Google Sheets

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto nuevo
3. Habilita las APIs: "Google Sheets API" y "Google Drive API"
4. Crea credenciales de tipo "Service Account"
5. Descarga el archivo JSON de credenciales
6. Renómbralo a `credentials.json` y colócalo en la raíz del proyecto
7. Comparte tu Google Sheet con el email del service account

### 5. Ejecutar

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

**Parámetros:**
- `tel`: Número de teléfono (con código de país, ej: 5255123456789)
- `country`: Código del país (AR, MX, CO, CL, etc.)
- `type`: Tipo de pago (`cuotas` o `single`)

**Respuesta:**
```json
{
  "payment_id": "DP-123456",
  "redirect_url": "https://checkout.dlocalgo.com/...",
  "status": "PENDING",
  "amount": 497.0,
  "currency": "USD",
  "installments": 12
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

## 🚀 Deploy en Producción

Para deployar en un servidor (Digital Ocean, AWS, etc.), sigue la guía completa:

📖 **[Ver DEPLOY_GUIDE.md](./DEPLOY_GUIDE.md)**

La guía incluye:
- Configuración de droplet en Digital Ocean
- Instalación de dependencias del sistema
- Configuración de Nginx como proxy reverso
- Instalación de certificado SSL con Let's Encrypt
- Configuración de systemd para ejecutar como servicio
- Seguridad y firewall
- Troubleshooting

### Deploy Rápido (Resumen)

1. **Crear droplet Ubuntu 22.04** en Digital Ocean
2. **Subir archivos** al servidor
3. **Ejecutar script de deploy:**
   ```bash
   chmod +x deploy.sh
   sudo ./deploy.sh
   ```
4. **Configurar Nginx** (ver guía)
5. **Instalar SSL** con certbot
6. ✅ ¡Listo!

## 🔐 Seguridad

- ✅ Archivo `.env` no se incluye en el repositorio
- ✅ Credenciales de Google Sheets protegidas
- ✅ Autenticación Bearer con dLocal Go
- ✅ Headers de seguridad en Nginx
- ✅ Firewall configurado (UFW)
- ✅ SSL/TLS automático con Let's Encrypt

## 📊 Monitoreo

### Ver Logs

**En desarrollo:**
Los logs se muestran en consola.

**En producción:**
```bash
# Logs de la aplicación
tail -f /root/app/logs/access.log
tail -f /root/app/logs/error.log

# Logs del sistema
journalctl -u bruno-api -f
```

### Estado del Servicio

```bash
systemctl status bruno-api
```

## 🛠️ Mantenimiento

### Reiniciar Servicio
```bash
sudo systemctl restart bruno-api
```

### Actualizar Código
```bash
cd /root/app
git pull  # Si usas Git
systemctl restart bruno-api
```

### Actualizar Dependencias
```bash
cd /root/app
source venv/bin/activate
pip install -r requirements.txt --upgrade
systemctl restart bruno-api
```

## 🧪 Testing

### Probar Health Check
```bash
curl http://localhost:8001/health
```

### Probar Generación de Link
```bash
curl "http://localhost:8001/api/pago?tel=5255123456789&country=MX&type=cuotas"
```

### Probar Webhook Manualmente
```bash
curl -X POST http://localhost:8001/debug/test-webhook?payment_id=TEST123&status=PAID
```

## 📞 Soporte

Para problemas o dudas:

1. **Revisa los logs** para identificar el error
2. **Consulta la documentación** de dLocal Go
3. **Verifica la configuración** del archivo `.env`
4. **Consulta la guía de deploy** para troubleshooting

## 📄 Licencia

Este proyecto es privado y de uso exclusivo para ALQUIMIA.

## 🎯 Autor

**Desarrollado para:** ALQUIMIA - Johnny Abraham  
**Año:** 2025

---

## 🔗 Links Útiles

- [dLocal Go Documentación](https://docs.dlocal.com/)
- [FastAPI Documentación](https://fastapi.tiangolo.com/)
- [Google Sheets API](https://developers.google.com/sheets/api)
- [Digital Ocean Tutorials](https://www.digitalocean.com/community/tutorials)

---

**¡Listo para procesar pagos de manera profesional!** 💰🚀
