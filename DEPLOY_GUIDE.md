# 🚀 Guía Completa de Deploy - Digital Ocean

Esta guía te llevará paso a paso para deployar la API de dLocal Go en un Droplet de Digital Ocean.

---

## 📋 Requisitos Previos

Antes de comenzar, asegúrate de tener:

- ✅ Cuenta en Digital Ocean
- ✅ Credenciales de dLocal Go (API Key y Secret Key)
- ✅ Archivo `credentials.json` de Google Sheets API
- ✅ URL del webhook de terceros (AutomatiChat u otro)
- ✅ Dominio configurado (opcional pero recomendado)

---

## 🖥️ PASO 1: Crear Droplet en Digital Ocean

### 1.1 Accede a Digital Ocean

1. Ve a [Digital Ocean](https://cloud.digitalocean.com/)
2. Click en **"Create"** → **"Droplets"**

### 1.2 Configuración del Droplet

**Sistema Operativo:**
- Selecciona: **Ubuntu 22.04 LTS (x64)**

**Plan:**
- **Basic**: $6/mes (1 GB RAM, 1 vCPU, 25 GB SSD)
- Para mayor tráfico: $12/mes (2 GB RAM, 1 vCPU, 50 GB SSD)

**Región del Datacenter:**
- Elige la más cercana a tus usuarios (ej: New York, Toronto, etc.)

**Autenticación:**
- Selecciona **SSH Key** (más seguro) o **Password**
- Si usas password, elige una contraseña fuerte

**Hostname:**
- Ponle un nombre descriptivo: `bruno-dlocal-api`

**Opciones adicionales (recomendado):**
- ✅ Monitoring (gratis)
- ✅ IPv6

### 1.3 Crear Droplet

Click en **"Create Droplet"** y espera 1-2 minutos.

---

## 🔐 PASO 2: Conectarte al Servidor

### 2.1 Obtén la IP del Droplet

Una vez creado, copia la **dirección IP** del droplet.

### 2.2 Conéctate por SSH

**En Windows (PowerShell):**
```powershell
ssh root@TU_IP_DEL_DROPLET
```

**En Mac/Linux (Terminal):**
```bash
ssh root@TU_IP_DEL_DROPLET
```

Si usas SSH key, puede que necesites especificarla:
```bash
ssh -i ~/.ssh/tu_key root@TU_IP_DEL_DROPLET
```

---

## ⚙️ PASO 3: Configurar el Servidor

### 3.1 Actualizar el Sistema

```bash
apt update && apt upgrade -y
```

### 3.2 Instalar Dependencias del Sistema

```bash
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git
```

### 3.3 Crear Directorio de Aplicación

```bash
mkdir -p /root/app
cd /root/app
```

**Nota:** Esta configuración corre la aplicación como root. Para mayor seguridad en producción, considera crear un usuario dedicado.

### 3.4 Configurar Firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

Presiona `y` para confirmar.

---

## 📦 PASO 4: Subir el Código de la Aplicación

### Opción A: Usando Git (Recomendado)

Si tienes tu código en GitHub/GitLab:

```bash
cd /root
git clone https://github.com/TU_USUARIO/TU_REPO.git app
cd app
```

### Opción B: Subir archivos manualmente (SCP)

**Desde tu PC Windows (PowerShell), en el directorio del proyecto:**

```powershell
scp -r * root@TU_IP_DEL_DROPLET:/root/app/
```

---

## 🐍 PASO 5: Configurar la Aplicación Python

### 5.1 Crear Entorno Virtual

```bash
cd /root/app
python3 -m venv venv
source venv/bin/activate
```

### 5.2 Instalar Dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 Configurar Variables de Entorno

```bash
nano .env
```

Copia y pega esta configuración (ajusta con tus datos):

```env
# dLocal Go API Credentials
DLOCAL_API_KEY=tu_api_key_aqui
DLOCAL_SECRET_KEY=tu_secret_key_aqui
DLOCAL_API_URL=https://api.dlocalgo.com

# Webhook Configuration
THIRD_PARTY_WEBHOOK_URL=https://app.automatichat.com/api/webhook-scenario/TU_ID
APP_BASE_URL=https://tu-dominio.com

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
ENVIRONMENT=production
LOG_LEVEL=INFO
```

**Guardar:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 5.4 Subir Credenciales de Google Sheets

**Desde tu PC (PowerShell):**

```powershell
scp credentials.json root@TU_IP_DEL_DROPLET:/root/app/
```

**En el servidor:**

```bash
chmod 600 /root/app/credentials.json
```

---

## 🔧 PASO 6: Configurar Systemd (Para que corra como servicio)

### 6.1 Crear archivo de servicio

```bash
nano /etc/systemd/system/bruno-api.service
```

Pega este contenido:

```ini
[Unit]
Description=Bruno dLocal Payment API
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/app
Environment="PATH=/root/app/venv/bin"
ExecStart=/root/app/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/root/app/logs/access.log
StandardError=append:/root/app/logs/error.log

[Install]
WantedBy=multi-user.target
```

**Guardar:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 6.2 Crear directorio de logs

```bash
mkdir -p /root/app/logs
```

### 6.3 Activar y Arrancar el Servicio

```bash
systemctl daemon-reload
systemctl enable bruno-api
systemctl start bruno-api
```

### 6.4 Verificar que esté corriendo

```bash
systemctl status bruno-api
```

Deberías ver **"active (running)"** en verde.

**Ver logs en tiempo real:**
```bash
tail -f /root/app/logs/access.log
```

---

## 🌐 PASO 7: Configurar Nginx (Proxy Reverso)

### 7.1 Crear configuración de Nginx

```bash
nano /etc/nginx/sites-available/bruno-api
```

Pega este contenido:

```nginx
server {
    listen 80;
    server_name tu-dominio.com www.tu-dominio.com;

    # Aumentar tamaño máximo de body (para webhooks)
    client_max_body_size 10M;

    # Logs
    access_log /var/log/nginx/bruno-api-access.log;
    error_log /var/log/nginx/bruno-api-error.log;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts (importante para webhooks)
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**Nota:** Reemplaza `tu-dominio.com` con tu dominio real.

**Guardar:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 7.2 Activar el sitio

```bash
ln -s /etc/nginx/sites-available/bruno-api /etc/nginx/sites-enabled/
```

### 7.3 Verificar configuración

```bash
nginx -t
```

Si dice **"syntax is ok"** y **"test is successful"**, continúa:

```bash
systemctl reload nginx
```

---

## 🔒 PASO 8: Instalar Certificado SSL (HTTPS)

### 8.1 Configurar DNS

Antes de continuar, asegúrate de que tu dominio apunte a la IP de tu droplet:

**En tu proveedor de dominio (GoDaddy, Namecheap, etc.):**

| Tipo | Nombre | Valor                | TTL  |
|------|--------|----------------------|------|
| A    | @      | TU_IP_DEL_DROPLET   | 300  |
| A    | www    | TU_IP_DEL_DROPLET   | 300  |

**Espera 5-10 minutos** para que se propague.

**Verificar:**
```bash
ping tu-dominio.com
```

### 8.2 Obtener Certificado SSL con Let's Encrypt

```bash
certbot --nginx -d tu-dominio.com -d www.tu-dominio.com
```

Sigue las instrucciones:
1. Ingresa tu email
2. Acepta los términos (`y`)
3. Elige si quieres compartir tu email (`y` o `n`)
4. Elige opción `2`: **Redirect - Make all requests redirect to secure HTTPS**

### 8.3 Renovación Automática

Certbot instala un cron job automático. Verifica:

```bash
certbot renew --dry-run
```

Si dice **"Congratulations, all simulated renewals succeeded"**, estás listo.

---

## ✅ PASO 9: Verificar que Todo Funcione

### 9.1 Verificar Health Check

```bash
curl https://tu-dominio.com/health
```

Deberías ver:
```json
{"status":"ok","message":"API is running"}
```

### 9.2 Probar un Link de Pago

En tu navegador:
```
https://tu-dominio.com/pagar?tel=5255123456789&country=MX&type=cuotas
```

Deberías ser redirigido al checkout de dLocal.

### 9.3 Verificar Webhooks

Haz una transacción de prueba en dLocal y verifica:

1. **Logs del servidor:**
```bash
tail -f /root/app/logs/access.log
```

2. **Google Sheets:** Debe aparecer el pago registrado

3. **Webhook de terceros:** Debe recibir la notificación

---

## 📊 PASO 10: Comandos Útiles de Mantenimiento

### Ver estado del servicio
```bash
systemctl status bruno-api
```

### Ver logs en tiempo real
```bash
# Logs de la aplicación
tail -f /root/app/logs/access.log
tail -f /root/app/logs/error.log

# Logs de Nginx
tail -f /var/log/nginx/bruno-api-access.log
tail -f /var/log/nginx/bruno-api-error.log
```

### Reiniciar el servicio
```bash
systemctl restart bruno-api
```

### Detener el servicio
```bash
systemctl stop bruno-api
```

### Ver uso de recursos
```bash
htop
```
(Presiona `q` para salir)

### Actualizar código (si usas Git)
```bash
cd /root/app
git pull
systemctl restart bruno-api
```

### Actualizar dependencias
```bash
cd /root/app
source venv/bin/activate
pip install -r requirements.txt --upgrade
systemctl restart bruno-api
```

---

## 🔐 PASO 11: Seguridad Adicional (Recomendado)

### 11.1 Deshabilitar Login Root con Password

```bash
nano /etc/ssh/sshd_config
```

Busca y cambia:
```
PermitRootLogin yes
```

A:
```
PermitRootLogin prohibit-password
```

Reinicia SSH:
```bash
systemctl restart sshd
```

### 11.2 Instalar Fail2Ban (protección contra fuerza bruta)

```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

### 11.3 Configurar Backups Automáticos

En Digital Ocean:
1. Ve a tu Droplet
2. Click en **"Backups"**
3. Activa backups semanales automáticos ($1.20/mes adicional)

---

## 🎯 URLs Finales de tu API

Una vez deployado, tendrás estas URLs disponibles:

| Endpoint | URL | Uso |
|----------|-----|-----|
| Health Check | `https://tu-dominio.com/health` | Verificar que la API esté viva |
| Generar Link | `https://tu-dominio.com/api/pago?tel=PHONE&country=COUNTRY&type=TYPE` | Generar link de pago (JSON) |
| Redirect Pago | `https://tu-dominio.com/pagar?tel=PHONE&country=COUNTRY&type=TYPE` | Redirect directo al checkout |
| Webhook dLocal | `https://tu-dominio.com/api/webhook/dlocal` | Recibir notificaciones de dLocal |
| Documentación | `https://tu-dominio.com/docs` | Swagger UI (documentación interactiva) |

---

## 🆘 Troubleshooting

### Problema: El servicio no arranca

**Solución:**
```bash
# Ver logs detallados
journalctl -u bruno-api -n 50 --no-pager

# Verificar que las dependencias estén instaladas
cd /root/app
source venv/bin/activate
pip list
```

### Problema: Nginx muestra "502 Bad Gateway"

**Solución:**
```bash
# Verificar que la app esté corriendo
systemctl status bruno-api

# Verificar que escuche en el puerto 8000
netstat -tulpn | grep 8000

# Reiniciar todo
systemctl restart bruno-api
systemctl restart nginx
```

### Problema: Webhooks no llegan

**Solución:**
```bash
# Verificar logs
tail -f /root/app/logs/access.log

# Probar webhook manualmente
curl -X POST https://tu-dominio.com/api/webhook/dlocal \
  -H "Content-Type: application/json" \
  -d '{"payment_id":"TEST123","status":"PAID"}'
```

### Problema: Google Sheets no guarda datos

**Solución:**
```bash
# Verificar que el archivo existe y tiene permisos
ls -la /root/app/credentials.json

# Ver logs de error
tail -f /root/app/logs/error.log

# Verificar variables de entorno
cat /root/app/.env | grep GOOGLE
```

---

## 📞 Soporte

Si tienes problemas:

1. **Revisa los logs:** `tail -f /root/app/logs/error.log`
2. **Verifica el estado del servicio:** `systemctl status bruno-api`
3. **Revisa la documentación de dLocal:** [dLocal Go Docs](https://docs.dlocal.com/)

---

## 🎉 ¡Felicitaciones!

Tu API de pagos con dLocal Go ya está en producción en Digital Ocean con:

✅ SSL/HTTPS automático  
✅ Servicio que se reinicia automáticamente  
✅ Logs centralizados  
✅ Proxy reverso con Nginx  
✅ Webhooks funcionando  
✅ Google Sheets integrado  
✅ Firewall configurado  

**¡Ahora puedes aceptar pagos de manera profesional y segura!** 🚀💰

