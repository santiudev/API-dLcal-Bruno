#!/bin/bash

# Script de Actualización Rápida
# Usar cuando necesites actualizar el código en producción

set -e

echo "🔄 Actualizando Bruno dLocal API..."

APP_DIR="/root/app"

# Verificar que estamos en el directorio correcto
if [ ! -f "$APP_DIR/main.py" ]; then
    echo "❌ Error: No se encuentra main.py en $APP_DIR"
    exit 1
fi

cd "$APP_DIR"

# 1. Hacer backup del .env y credentials.json
echo "💾 Creando backup de archivos sensibles..."
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
cp credentials.json credentials.json.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# 2. Actualizar código (si usas Git)
if [ -d ".git" ]; then
    echo "📥 Pulling cambios de Git..."
    git pull
else
    echo "⚠️  No se encontró repositorio Git. Asume que subiste los archivos manualmente."
fi

# 3. Activar entorno virtual
echo "🐍 Activando entorno virtual..."
source venv/bin/activate

# 4. Actualizar dependencias (por si acaso)
echo "📦 Actualizando dependencias..."
pip install -r requirements.txt --upgrade --quiet

# 5. Restaurar archivos sensibles si fueron sobrescritos
echo "🔐 Verificando archivos sensibles..."
if [ ! -f ".env" ] && [ -f ".env.backup."* ]; then
    echo "⚠️  Restaurando .env desde backup..."
    cp .env.backup.* .env
fi

# 6. Reiniciar servicio
echo "🔄 Reiniciando servicio..."
systemctl restart bruno-api

# 7. Esperar y verificar
sleep 3
if systemctl is-active --quiet bruno-api; then
    echo "✅ Servicio actualizado y corriendo"
    systemctl status bruno-api --no-pager -l
else
    echo "❌ Error: El servicio no está corriendo después de la actualización"
    echo "Revirtiendo a la versión anterior..."
    # Aquí podrías agregar lógica de rollback si usas Git
    exit 1
fi

# 8. Verificar que responde
echo "🧪 Verificando API..."
sleep 2
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ API respondiendo correctamente"
else
    echo "⚠️  ADVERTENCIA: La API no responde"
fi

echo ""
echo "🎉 ¡Actualización completada!"
echo "📊 Ver logs: tail -f $APP_DIR/logs/access.log"

