#!/bin/bash

# Script de Deploy Automatizado para Digital Ocean
# Ejecutar este script en el servidor después de subir los archivos

set -e  # Detener si hay errores

echo "🚀 Iniciando deploy de Bruno dLocal API..."

# Variables
APP_DIR="/root/app"
USER="root"
VENV_DIR="$APP_DIR/venv"

# Verificar que estamos en el directorio correcto
if [ ! -f "$APP_DIR/main.py" ]; then
    echo "❌ Error: No se encuentra main.py en $APP_DIR"
    exit 1
fi

echo "📁 Directorio de aplicación: $APP_DIR"

# 1. Activar entorno virtual o crearlo si no existe
echo "🐍 Configurando entorno virtual..."
if [ ! -d "$VENV_DIR" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# 2. Actualizar pip
echo "⬆️  Actualizando pip..."
pip install --upgrade pip --quiet

# 3. Instalar/actualizar dependencias
echo "📦 Instalando dependencias..."
pip install -r "$APP_DIR/requirements.txt" --quiet

# 4. Verificar que existe .env
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  ADVERTENCIA: No se encuentra el archivo .env"
    echo "Por favor, crea el archivo .env antes de continuar"
    exit 1
fi

# 5. Verificar que existe credentials.json
if [ ! -f "$APP_DIR/credentials.json" ]; then
    echo "⚠️  ADVERTENCIA: No se encuentra credentials.json"
    echo "Por favor, sube el archivo credentials.json antes de continuar"
    exit 1
fi

# 6. Crear directorio de logs si no existe
echo "📋 Configurando logs..."
mkdir -p "$APP_DIR/logs"

# 7. Ajustar permisos
echo "🔐 Ajustando permisos..."
chown -R $USER:$USER "$APP_DIR"
chmod 600 "$APP_DIR/.env"
chmod 600 "$APP_DIR/credentials.json"

# 8. Verificar/crear servicio systemd
SERVICE_FILE="/etc/systemd/system/bruno-api.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo "📝 Creando servicio systemd..."
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Bruno dLocal Payment API
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

StandardOutput=append:$APP_DIR/logs/access.log
StandardError=append:$APP_DIR/logs/error.log

[Install]
WantedBy=multi-user.target
EOF
fi

# 9. Recargar systemd y reiniciar servicio
echo "🔄 Reiniciando servicio..."
systemctl daemon-reload
systemctl enable bruno-api
systemctl restart bruno-api

# 10. Esperar un momento y verificar estado
sleep 3
if systemctl is-active --quiet bruno-api; then
    echo "✅ Servicio iniciado correctamente"
    systemctl status bruno-api --no-pager -l
else
    echo "❌ Error: El servicio no está corriendo"
    echo "Ver logs con: journalctl -u bruno-api -n 50"
    exit 1
fi

# 11. Verificar que responde
echo ""
echo "🧪 Probando API..."
sleep 2
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ API respondiendo correctamente"
else
    echo "⚠️  ADVERTENCIA: La API no responde en /health"
fi

echo ""
echo "🎉 ¡Deploy completado exitosamente!"
echo ""
echo "📊 Comandos útiles:"
echo "  - Ver logs en tiempo real:  tail -f $APP_DIR/logs/access.log"
echo "  - Ver estado del servicio:  systemctl status bruno-api"
echo "  - Reiniciar servicio:       systemctl restart bruno-api"
echo "  - Ver logs del sistema:     journalctl -u bruno-api -f"
echo ""
echo "🌐 No olvides configurar Nginx si aún no lo has hecho"
echo "📖 Ver guía completa en: DEPLOY_GUIDE.md"

