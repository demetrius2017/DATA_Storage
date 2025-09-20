#!/bin/bash
# Скрипт автоматического развертывания коллектора на удаленном сервере
# Использование: ./deploy_remote_collector.sh [server_ip] [user]

set -e  # Остановка при любой ошибке

# Параметры по умолчанию
SERVER_IP="${1:-YOUR_SERVER_IP}"
SERVER_USER="${2:-root}" 
PROJECT_NAME="data_collector"
REMOTE_PATH="/opt/$PROJECT_NAME"
DB_URL="${DATABASE_URL:-postgresql://user:password@host:port/database}"

echo "🚀 Развертывание коллектора на удаленном сервере"
echo "=================================================="
echo "Сервер: $SERVER_USER@$SERVER_IP"
echo "Путь: $REMOTE_PATH"
echo ""

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверка подключения к серверу
log "🔍 Проверка подключения к серверу..."
if ! ssh -o ConnectTimeout=10 "$SERVER_USER@$SERVER_IP" "echo 'Подключение успешно'"; then
    echo "❌ Ошибка: Не удалось подключиться к серверу $SERVER_IP"
    exit 1
fi

# Подготовка файлов для отправки
log "📦 Подготовка файлов..."
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Копируем необходимые файлы
cp -r collector/ "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/" 2>/dev/null || echo "requirements.txt не найден, создаем..."

# Создаем requirements.txt если не существует
cat > "$TEMP_DIR/requirements.txt" << EOF
asyncpg>=0.29.0
websockets>=12.0
numpy>=1.24.0
pandas>=2.0.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
psutil>=5.9.0
python-multipart>=0.0.6
websocket-client>=1.6.0
EOF

# Создаем конфигурационные файлы
mkdir -p "$TEMP_DIR/config"

# Конфигурация systemd сервиса
cat > "$TEMP_DIR/config/collector.service" << EOF
[Unit]
Description=Market Data Collector
After=network.target
Wants=network.target

[Service]
Type=simple
User=collector
Group=collector
WorkingDirectory=$REMOTE_PATH
Environment=PYTHONPATH=$REMOTE_PATH
Environment=DATABASE_URL=$DB_URL
ExecStart=$REMOTE_PATH/venv/bin/python $REMOTE_PATH/collector/ingestion/enhanced_multi_stream_collector.py
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=collector

[Install]
WantedBy=multi-user.target
EOF

# Конфигурация systemd для API
cat > "$TEMP_DIR/config/collector-api.service" << EOF
[Unit]
Description=Collector Management API
After=network.target
Wants=network.target

[Service]
Type=simple
User=collector
Group=collector
WorkingDirectory=$REMOTE_PATH
Environment=PYTHONPATH=$REMOTE_PATH
Environment=DATABASE_URL=$DB_URL
ExecStart=$REMOTE_PATH/venv/bin/python $REMOTE_PATH/collector/management/collector_api.py
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=collector-api

[Install]
WantedBy=multi-user.target
EOF

# Конфигурация nginx
cat > "$TEMP_DIR/config/nginx_collector.conf" << EOF
server {
    listen 80;
    server_name _;
    
    # API проксирование
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # WebSocket проксирование
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Dashboard
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Скрипт для развертывания на сервере
cat > "$TEMP_DIR/deploy.sh" << 'EOF'
#!/bin/bash
set -e

REMOTE_PATH="/opt/data_collector"
DB_URL="$DATABASE_URL"

echo "🏗️ Начинаем развертывание на сервере..."

# Обновляем систему
echo "📦 Обновление системы..."
apt update && apt upgrade -y

# Устанавливаем необходимые пакеты
echo "📋 Установка зависимостей..."
apt install -y python3 python3-pip python3-venv nginx supervisor htop curl git

# Создаем пользователя для коллектора
if ! id "collector" &>/dev/null; then
    echo "👤 Создание пользователя collector..."
    useradd -r -s /bin/bash -d $REMOTE_PATH collector
fi

# Создаем директории
echo "📁 Создание директорий..."
mkdir -p $REMOTE_PATH/{logs,data,config}
chown -R collector:collector $REMOTE_PATH

# Переходим в рабочую директорию
cd $REMOTE_PATH

# Создаем виртуальное окружение
echo "🐍 Создание Python окружения..."
sudo -u collector python3 -m venv venv
sudo -u collector $REMOTE_PATH/venv/bin/pip install --upgrade pip

# Устанавливаем зависимости
echo "📚 Установка Python пакетов..."
sudo -u collector $REMOTE_PATH/venv/bin/pip install -r requirements.txt

# Копируем systemd сервисы
echo "⚙️ Настройка systemd сервисов..."
cp config/collector.service /etc/systemd/system/
cp config/collector-api.service /etc/systemd/system/
systemctl daemon-reload

# Настраиваем nginx
echo "🌐 Настройка nginx..."
cp config/nginx_collector.conf /etc/nginx/sites-available/collector
ln -sf /etc/nginx/sites-available/collector /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Настраиваем firewall
echo "🔒 Настройка firewall..."
ufw allow ssh
ufw allow http
ufw allow https
ufw --force enable

# Запускаем сервисы
echo "▶️ Запуск сервисов..."
systemctl enable collector-api
systemctl start collector-api

echo "✅ Развертывание завершено!"
echo ""
echo "🎯 Доступные endpoints:"
echo "   Dashboard: http://$(curl -s ifconfig.me)"
echo "   API: http://$(curl -s ifconfig.me)/api/collector/status"
echo ""
echo "📋 Управление сервисами:"
echo "   systemctl status collector-api"
echo "   systemctl status collector"
echo "   journalctl -f -u collector-api"
echo ""
EOF

chmod +x "$TEMP_DIR/deploy.sh"

# Создаем скрипт мониторинга
cat > "$TEMP_DIR/monitor.sh" << 'EOF'
#!/bin/bash
# Скрипт мониторинга коллектора

check_service() {
    local service=$1
    if systemctl is-active --quiet $service; then
        echo "✅ $service: запущен"
    else
        echo "❌ $service: остановлен"
        systemctl status $service --no-pager -l
    fi
}

echo "🔍 Мониторинг коллектора $(date)"
echo "=================================="

# Проверяем сервисы
check_service collector-api
check_service collector
check_service nginx

# Проверяем подключение к БД
echo ""
echo "🗄️ Проверка БД..."
if /opt/data_collector/venv/bin/python -c "
import asyncpg
import asyncio

async def check():
    try:
        conn = await asyncpg.connect('$DATABASE_URL')
        result = await conn.fetchval('SELECT count(*) FROM book_ticker WHERE ts_exchange > now() - interval \'5 minutes\'')
        await conn.close()
        print(f'✅ БД доступна, свежих записей: {result}')
    except Exception as e:
        print(f'❌ Ошибка БД: {e}')

asyncio.run(check())
"; then
    :
else
    echo "❌ Ошибка проверки БД"
fi

# Проверяем место на диске
echo ""
echo "💾 Место на диске:"
df -h / | tail -1

# Проверяем память
echo ""
echo "🧠 Память:"
free -h

# Проверяем CPU
echo ""
echo "⚡ CPU Load:"
uptime

# Последние логи
echo ""
echo "📋 Последние логи коллектора:"
journalctl -u collector --no-pager -n 5

echo ""
echo "📋 Последние логи API:"
journalctl -u collector-api --no-pager -n 5
EOF

chmod +x "$TEMP_DIR/monitor.sh"

# Отправляем файлы на сервер
log "📤 Отправка файлов на сервер..."
rsync -avz --progress "$TEMP_DIR/" "$SERVER_USER@$SERVER_IP:$REMOTE_PATH/"

# Выполняем развертывание на сервере
log "🏗️ Выполнение развертывания на сервере..."
ssh "$SERVER_USER@$SERVER_IP" "cd $REMOTE_PATH && bash deploy.sh"

# Проверяем статус развертывания
log "🔍 Проверка статуса сервисов..."
ssh "$SERVER_USER@$SERVER_IP" "cd $REMOTE_PATH && bash monitor.sh"

# Получаем IP сервера
SERVER_PUBLIC_IP=$(ssh "$SERVER_USER@$SERVER_IP" "curl -s ifconfig.me" 2>/dev/null || echo "$SERVER_IP")

log "✅ Развертывание завершено успешно!"
echo ""
echo "🎯 Коллектор развернут и доступен:"
echo "   Dashboard: http://$SERVER_PUBLIC_IP"
echo "   API Status: http://$SERVER_PUBLIC_IP/api/collector/status"
echo "   WebSocket: ws://$SERVER_PUBLIC_IP/ws/monitoring"
echo ""
echo "📋 Полезные команды для управления:"
echo "   ssh $SERVER_USER@$SERVER_IP 'systemctl status collector-api'"
echo "   ssh $SERVER_USER@$SERVER_IP 'journalctl -f -u collector'"
echo "   ssh $SERVER_USER@$SERVER_IP 'cd $REMOTE_PATH && bash monitor.sh'"
echo ""
echo "🔧 Для запуска сбора данных:"
echo "   curl -X POST http://$SERVER_PUBLIC_IP/api/collector/start \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"symbols\":[\"BTCUSDT\",\"ETHUSDT\",\"SOLUSDT\"], \"database_url\":\"$DB_URL\", \"log_level\":\"INFO\"}'"
echo ""