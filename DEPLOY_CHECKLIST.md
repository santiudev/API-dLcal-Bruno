# ✅ Checklist de Deploy - Digital Ocean

Usa este checklist para asegurarte de que completaste todos los pasos del deploy.

---

## 📋 Pre-Deploy (Preparación)

- [ ] Tengo cuenta en Digital Ocean
- [ ] Tengo credenciales de dLocal Go (API Key y Secret Key)
- [ ] Tengo archivo `credentials.json` de Google Sheets
- [ ] He compartido mi Google Sheet con el email del service account
- [ ] Tengo URL del webhook de terceros (AutomatiChat, etc.)
- [ ] Tengo dominio configurado (o voy a usar IP temporal)
- [ ] He actualizado el archivo `.env` con mis credenciales reales

---

## 🖥️ Paso 1: Crear Droplet

- [ ] Droplet creado con Ubuntu 22.04 LTS
- [ ] Plan seleccionado (mínimo: $6/mes - 1GB RAM)
- [ ] Región del datacenter elegida
- [ ] SSH Key configurado (o password establecido)
- [ ] Monitoring activado
- [ ] Copié la dirección IP del droplet: `___________________`

---

## 🔐 Paso 2: Conectar al Servidor

- [ ] Conectado por SSH: `ssh root@TU_IP`
- [ ] Acceso verificado

---

## ⚙️ Paso 3: Configurar Servidor

- [ ] Sistema actualizado: `apt update && apt upgrade -y`
- [ ] Dependencias instaladas: `apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git`
- [ ] Directorio `/root/app` creado
- [ ] Firewall configurado y activado

---

## 📦 Paso 4: Subir Código

- [ ] Código subido al servidor (Git o SCP)
- [ ] Archivos en: `/root/app/`

---

## 🐍 Paso 5: Configurar Python

- [ ] Entorno virtual creado en `/root/app/venv`
- [ ] Dependencias instaladas: `pip install -r requirements.txt`
- [ ] Archivo `.env` creado y configurado con datos de producción
- [ ] Archivo `credentials.json` subido y con permisos 600

**Verifica tu `.env`:**
- [ ] `DLOCAL_API_KEY` configurado
- [ ] `DLOCAL_SECRET_KEY` configurado
- [ ] `DLOCAL_API_URL` apunta a producción (`https://api.dlocalgo.com`)
- [ ] `APP_BASE_URL` apunta a tu dominio
- [ ] `THIRD_PARTY_WEBHOOK_URL` configurado
- [ ] URLs de redirect configuradas
- [ ] `MERCHANT_NAME` personalizado
- [ ] `GOOGLE_SHEETS_NAME` correcto
- [ ] `ENVIRONMENT=production`

---

## 🔧 Paso 6: Configurar Systemd

- [ ] Servicio creado: `/etc/systemd/system/bruno-api.service`
- [ ] Directorio de logs creado: `/root/app/logs`
- [ ] Servicio habilitado: `systemctl enable bruno-api`
- [ ] Servicio iniciado: `systemctl start bruno-api`
- [ ] Estado verificado: `systemctl status bruno-api` (debe estar en verde "active (running)")

---

## 🌐 Paso 7: Configurar Nginx

- [ ] Archivo de configuración creado: `/etc/nginx/sites-available/bruno-api`
- [ ] Dominio reemplazado en la configuración
- [ ] Sitio habilitado: `ln -s /etc/nginx/sites-available/bruno-api /etc/nginx/sites-enabled/`
- [ ] Configuración verificada: `nginx -t` (debe decir "syntax is ok")
- [ ] Nginx recargado: `systemctl reload nginx`

---

## 🔒 Paso 8: Configurar SSL (HTTPS)

### DNS
- [ ] Registro A creado apuntando a la IP del droplet
- [ ] Registro A para `www` creado (opcional)
- [ ] DNS propagado (verificado con `ping tu-dominio.com`)

### Certificado
- [ ] Certificado SSL obtenido: `certbot --nginx -d tu-dominio.com -d www.tu-dominio.com`
- [ ] Opción de redirect seleccionada (opción 2)
- [ ] Renovación automática verificada: `certbot renew --dry-run`

---

## ✅ Paso 9: Verificación Final

### Health Check
- [ ] `curl https://tu-dominio.com/health` responde con `{"status":"ok"}`

### Link de Pago
- [ ] Puedo generar un link: `https://tu-dominio.com/pagar?tel=5255123456789&country=MX&type=cuotas`
- [ ] Me redirige correctamente al checkout de dLocal

### Webhooks
- [ ] Webhook de prueba funciona: `curl -X POST https://tu-dominio.com/debug/test-webhook?payment_id=TEST&status=PAID`
- [ ] Logs muestran actividad: `tail -f /root/app/logs/access.log`

### Google Sheets
- [ ] Hice una transacción de prueba
- [ ] El pago aparece registrado en Google Sheet

### Webhook de Terceros
- [ ] El webhook de terceros recibió la notificación

---

## 📊 Paso 10: Monitoreo

- [ ] Sé cómo ver logs: `tail -f /root/app/logs/access.log`
- [ ] Sé cómo reiniciar: `systemctl restart bruno-api`
- [ ] Sé cómo ver estado: `systemctl status bruno-api`

---

## 🔐 Paso 11: Seguridad (Opcional pero Recomendado)

- [ ] Login root con password deshabilitado
- [ ] Fail2Ban instalado
- [ ] Backups automáticos activados en Digital Ocean
- [ ] Claves SSH guardadas en lugar seguro

---

## 🎯 URLs Finales

Anota aquí tus URLs de producción:

| Endpoint | URL |
|----------|-----|
| Health Check | `https://________________________________/health` |
| API Pago | `https://________________________________/api/pago` |
| Redirect Pago | `https://________________________________/pagar` |
| Webhook dLocal | `https://________________________________/api/webhook/dlocal` |
| Documentación | `https://________________________________/docs` |

---

## 🆘 Troubleshooting Rápido

Si algo no funciona:

1. **Ver logs de la aplicación:**
   ```bash
   tail -f /root/app/logs/error.log
   ```

2. **Ver logs del sistema:**
   ```bash
   journalctl -u bruno-api -n 50
   ```

3. **Reiniciar todo:**
   ```bash
   systemctl restart bruno-api
   systemctl restart nginx
   ```

4. **Verificar que todo esté corriendo:**
   ```bash
   systemctl status bruno-api
   systemctl status nginx
   netstat -tulpn | grep 8000
   ```

---

## 🎉 ¡Deploy Completado!

- [ ] **TODO FUNCIONANDO** ✅

Una vez marcada esta última casilla, ¡tu API está en producción y lista para procesar pagos!

**Guardá este checklist para futuros deploys o actualizaciones.**

---

## 📞 Contactos Importantes

- **dLocal Soporte:** [support@dlocal.com](mailto:support@dlocal.com)
- **Digital Ocean Docs:** https://docs.digitalocean.com/
- **Documentación del Proyecto:** Ver README.md

---

**Fecha de deploy:** _______________  
**Versión:** 1.0.0  
**Deployado por:** _______________

