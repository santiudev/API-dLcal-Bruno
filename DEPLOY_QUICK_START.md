# ⚡ Deploy Rápido - 10 Minutos

Si ya conoces los conceptos y solo necesitas los comandos, esta es tu guía.

---

## 🎯 Requisitos Previos

- Droplet Ubuntu 22.04 en Digital Ocean
- IP del droplet copiada
- Archivos `.env` y `credentials.json` configurados localmente
- Dominio apuntando a la IP (opcional pero recomendado)

---

## 🚀 Comandos de Deploy

### 1️⃣ Conectar y Preparar Servidor

```bash
# Conectar
ssh root@TU_IP

# Actualizar sistema
apt update && apt upgrade -y

# Instalar dependencias
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git

# Crear directorio
mkdir -p /root/app

# Configurar firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

### 2️⃣ Subir Código (desde tu PC)

```powershell
# En tu PC (PowerShell), desde el directorio del proyecto
scp -r * root@TU_IP:/root/app/
```

### 3️⃣ Configurar Aplicación (en el servidor)

```bash
# Ir al directorio
cd /root/app

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# Hacer deploy automatizado
chmod +x deploy.sh
./deploy.sh
```

### 4️⃣ Configurar Nginx

```bash
# Crear configuración
nano /etc/nginx/sites-available/bruno-api
```

Pegar:
```nginx
server {
    listen 80;
    server_name TU_DOMINIO.com www.TU_DOMINIO.com;
    
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
    }
}
```

```bash
# Activar sitio
ln -s /etc/nginx/sites-available/bruno-api /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### 5️⃣ Instalar SSL

```bash
certbot --nginx -d TU_DOMINIO.com -d www.TU_DOMINIO.com
# Elegir opción 2 (Redirect)
```

### 6️⃣ Verificar

```bash
# Health check
curl https://TU_DOMINIO.com/health

# Ver logs
tail -f /root/app/logs/access.log

# Estado del servicio
systemctl status bruno-api
```

---

## ✅ Listo!

Tu API ya está en producción en:
- `https://TU_DOMINIO.com/health` - Health check
- `https://TU_DOMINIO.com/pagar?tel=PHONE&country=COUNTRY&type=TYPE` - Generar pagos
- `https://TU_DOMINIO.com/docs` - Documentación

---

## 🔧 Comandos Útiles

```bash
# Ver logs en tiempo real
tail -f /root/app/logs/access.log

# Reiniciar servicio
systemctl restart bruno-api

# Ver estado
systemctl status bruno-api

# Actualizar código
cd /root/app
git pull  # Si usas Git
systemctl restart bruno-api
```

---

## 🆘 Si algo falla

```bash
# Ver errores
journalctl -u bruno-api -n 50

# Verificar que esté escuchando
netstat -tulpn | grep 8000

# Reiniciar todo
systemctl restart bruno-api
systemctl restart nginx
```

---

📖 **Para la guía completa:** Ver [DEPLOY_GUIDE.md](./DEPLOY_GUIDE.md)

