#!/bin/bash
# Скрипт установки зависимостей для удаленного коллектора
# Использование: ./install_dependencies.sh

set -e

echo "🔧 УСТАНОВКА ЗАВИСИМОСТЕЙ ДЛЯ УДАЛЕННОГО КОЛЛЕКТОРА"
echo "==================================================="

# Определяем ОС
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    echo "❌ Неподдерживаемая ОС: $OSTYPE"
    exit 1
fi

echo "🖥️ Обнаружена ОС: $OS"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Проверка Python
log "🐍 Проверка Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите Python 3.8+ перед продолжением."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log "✅ Python $PYTHON_VERSION обнаружен"

# Проверка pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не найден. Установите pip перед продолжением."
    exit 1
fi

# Создаем виртуальное окружение если не существует
if [ ! -d "venv" ]; then
    log "📦 Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
log "🔄 Активация виртуального окружения..."
source venv/bin/activate

# Обновляем pip
log "⬆️ Обновление pip..."
pip install --upgrade pip

# Создаем требования для клиента
log "📋 Создание requirements.txt для клиента..."
cat > requirements_client.txt << EOF
# Основные зависимости для клиента управления
requests>=2.31.0
websockets>=12.0
asyncio-mqtt>=0.13.0

# Для API сервера (если запускается локально)
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6

# Для работы с данными
pandas>=2.0.0
numpy>=1.24.0

# Для мониторинга системы
psutil>=5.9.0

# Для работы с БД
asyncpg>=0.29.0

# Утилиты
python-dotenv>=1.0.0
pydantic>=2.0.0
aiofiles>=23.0.0
EOF

# Устанавливаем зависимости клиента
log "📚 Установка Python пакетов для клиента..."
pip install -r requirements_client.txt

# Создаем requirements для удаленного сервера
log "📋 Создание requirements.txt для удаленного сервера..."
cat > requirements_server.txt << EOF
# Основные зависимости для удаленного сервера
asyncpg>=0.29.0
websockets>=12.0
numpy>=1.24.0
pandas>=2.0.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
psutil>=5.9.0
python-multipart>=0.0.6
websocket-client>=1.6.0
aiofiles>=23.0.0
python-dotenv>=1.0.0
pydantic>=2.0.0

# Binance API для сбора данных
python-binance>=1.0.19
aiohttp>=3.9.0

# Сжатие и архивация
lz4>=4.0.0
zstandard>=0.22.0

# Мониторинг и логирование
prometheus-client>=0.19.0
structlog>=23.0.0
EOF

# Копируем requirements в collector
cp requirements_server.txt collector/requirements.txt

# Проверяем установку основных пакетов
log "🔍 Проверка установленных пакетов..."

# Проверяем каждый ключевой пакет
PACKAGES=("requests" "websockets" "fastapi" "uvicorn" "psutil" "asyncpg" "pandas" "numpy")
FAILED_PACKAGES=()

for package in "${PACKAGES[@]}"; do
    if python -c "import $package" 2>/dev/null; then
        echo "  ✅ $package"
    else
        echo "  ❌ $package"
        FAILED_PACKAGES+=("$package")
    fi
done

if [ ${#FAILED_PACKAGES[@]} -ne 0 ]; then
    echo "⚠️ Некоторые пакеты не установлены: ${FAILED_PACKAGES[*]}"
    log "🔄 Попытка переустановки проблемных пакетов..."
    for package in "${FAILED_PACKAGES[@]}"; do
        pip install --force-reinstall "$package"
    done
fi

# Установка системных зависимостей для разных ОС
if [[ "$OS" == "linux" ]]; then
    log "🐧 Проверка системных зависимостей для Linux..."
    
    # Проверяем наличие curl
    if ! command -v curl &> /dev/null; then
        echo "⚠️ curl не найден. Рекомендуется установить: sudo apt install curl"
    fi
    
    # Проверяем наличие htop
    if ! command -v htop &> /dev/null; then
        echo "💡 htop не найден. Рекомендуется установить: sudo apt install htop"
    fi
    
elif [[ "$OS" == "macos" ]]; then
    log "🍎 Проверка системных зависимостей для macOS..."
    
    # Проверяем наличие brew
    if ! command -v brew &> /dev/null; then
        echo "💡 Homebrew не найден. Рекомендуется установить для управления пакетами."
    fi
fi

# Создаем конфигурационный файл
log "⚙️ Создание конфигурационного файла..."
cat > .env.example << EOF
# Конфигурация удаленного коллектора

# URL удаленного сервера управления
REMOTE_SERVER_URL=http://YOUR_SERVER_IP:8000

# База данных (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/database

# Настройки сбора данных
DEFAULT_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,DOTUSDT
LOG_LEVEL=INFO

# Мониторинг
MONITORING_INTERVAL=5
HEALTH_CHECK_INTERVAL=60

# Безопасность
API_KEY=your_secure_api_key_here
ALLOWED_IPS=127.0.0.1,YOUR_MANAGEMENT_IP
EOF

# Проверяем возможность подключения к тестовому серверу
log "🔗 Проверка сетевого подключения..."
if command -v curl &> /dev/null; then
    if curl -s --connect-timeout 5 https://httpbin.org/status/200 > /dev/null; then
        echo "  ✅ Интернет подключение работает"
    else
        echo "  ⚠️ Проблемы с интернет подключением"
    fi
else
    echo "  💡 curl не доступен для проверки сети"
fi

# Создаем скрипт тестирования
log "🧪 Создание тестового скрипта..."
cat > test_client.py << 'EOF'
#!/usr/bin/env python3
"""Тестирование клиента удаленного коллектора"""

import sys
import json
from datetime import datetime

def test_imports():
    """Тестирование импортов"""
    print("🧪 Тестирование импортов...")
    
    try:
        import requests
        print("  ✅ requests")
    except ImportError as e:
        print(f"  ❌ requests: {e}")
        return False
    
    try:
        import websockets
        print("  ✅ websockets")
    except ImportError as e:
        print(f"  ❌ websockets: {e}")
        return False
    
    try:
        import asyncio
        print("  ✅ asyncio")
    except ImportError as e:
        print(f"  ❌ asyncio: {e}")
        return False
    
    try:
        from dataclasses import dataclass
        print("  ✅ dataclasses")
    except ImportError as e:
        print(f"  ❌ dataclasses: {e}")
        return False
    
    return True

def test_client_functionality():
    """Тестирование функциональности клиента"""
    print("\n🔧 Тестирование функциональности клиента...")
    
    try:
        # Импортируем наш клиент
        sys.path.append('scripts')
        from remote_collector_client import RemoteCollectorClient, CollectorStatus
        
        # Создаем тестовый клиент
        client = RemoteCollectorClient("http://localhost:8000")
        print("  ✅ Клиент создан успешно")
        
        # Создаем тестовый статус
        status = CollectorStatus(
            is_running=True,
            symbols=["BTCUSDT", "ETHUSDT"],
            start_time=datetime.now().isoformat(),
            uptime_seconds=3600,
            error=None
        )
        print("  ✅ Структуры данных работают")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ КЛИЕНТА УДАЛЕННОГО КОЛЛЕКТОРА")
    print("=" * 50)
    
    success = True
    
    # Тестируем импорты
    if not test_imports():
        success = False
    
    # Тестируем функциональность
    if not test_client_functionality():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Все тесты прошли успешно!")
        print("\n💡 Следующие шаги:")
        print("1. Скопируйте .env.example в .env и настройте параметры")
        print("2. Запустите развертывание: ./scripts/deploy_remote_collector.sh SERVER_IP")
        print("3. Используйте клиент: python scripts/remote_collector_client.py --help")
    else:
        print("❌ Некоторые тесты не прошли. Проверьте установку зависимостей.")
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

chmod +x test_client.py

# Запускаем тестирование
log "🧪 Запуск тестов..."
python test_client.py

log "✅ Установка зависимостей завершена!"
echo ""
echo "🎯 ГОТОВО К РАЗВЕРТЫВАНИЮ"
echo "========================="
echo ""
echo "📁 Созданные файлы:"
echo "   - requirements_client.txt (зависимости для локального клиента)"
echo "   - requirements_server.txt (зависимости для удаленного сервера)" 
echo "   - collector/requirements.txt (копия для развертывания)"
echo "   - .env.example (пример конфигурации)"
echo "   - test_client.py (скрипт тестирования)"
echo ""
echo "🚀 Команды для развертывания:"
echo "   1. Настроить .env: cp .env.example .env && nano .env"
echo "   2. Развернуть на сервере: ./scripts/deploy_remote_collector.sh SERVER_IP"
echo "   3. Управлять коллектором: python scripts/remote_collector_client.py --help"
echo ""
echo "💡 Примеры использования клиента:"
echo "   python scripts/remote_collector_client.py --server http://SERVER_IP summary"
echo "   python scripts/remote_collector_client.py --server http://SERVER_IP start --symbols BTCUSDT ETHUSDT --database-url 'postgresql://...'"
echo "   python scripts/remote_collector_client.py --server http://SERVER_IP monitor --duration 30"
echo ""