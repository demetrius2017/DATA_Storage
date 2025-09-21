#!/bin/bash
# GitHub Secrets Setup Automation Script
# Требует установленный GitHub CLI: brew install gh

set -e

echo "🔐 Автоматическая настройка GitHub Secrets для PostgreSQL OrderBook Collector"
echo "=================================================================="

# Проверка GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI не установлен."
    echo "📦 Установите: brew install gh (macOS) или apt install gh (Ubuntu)"
    exit 1
fi

# Проверка авторизации
if ! gh auth status &> /dev/null; then
    echo "🔑 Требуется авторизация в GitHub..."
    gh auth login
fi

echo "✅ GitHub CLI готов!"
echo ""

# Ввод данных сервера
echo "📋 Настройка данных сервера:"
read -p "🖥️  IP адрес сервера: " SERVER_HOST
read -p "👤 Пользователь сервера (обычно root): " SERVER_USER
read -p "🔌 SSH порт (enter для 22): " SERVER_PORT
SERVER_PORT=${SERVER_PORT:-22}

echo ""
echo "🗄️ Настройка базы данных:"
read -s -p "🔐 Пароль для PostgreSQL: " POSTGRES_PASSWORD
echo ""

echo ""
echo "🔗 Binance API (опционально, можно пропустить):"
read -p "🔑 Binance API Key (enter чтобы пропустить): " BINANCE_API_KEY
if [ ! -z "$BINANCE_API_KEY" ]; then
    read -s -p "🔐 Binance Secret Key: " BINANCE_SECRET_KEY
    echo ""
fi

echo ""
echo "🔧 Настройка SSH ключа:"
echo "1. Использовать существующий ключ"
echo "2. Сгенерировать новый ключ"
read -p "Выберите опцию (1 или 2): " SSH_OPTION

if [ "$SSH_OPTION" = "2" ]; then
    echo "🔨 Генерация нового SSH ключа..."
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy_$(date +%s) -N ""
    
    SSH_KEY_PATH="~/.ssh/github_deploy_$(date +%s)"
    echo "📋 Новый ключ создан: $SSH_KEY_PATH"
    echo "📤 Скопируйте публичный ключ на сервер:"
    echo "ssh-copy-id -i ${SSH_KEY_PATH}.pub $SERVER_USER@$SERVER_HOST"
    read -p "Нажмите Enter после копирования ключа на сервер..."
    
    SSH_PRIVATE_KEY=$(cat "${SSH_KEY_PATH}")
else
    echo "📁 Доступные SSH ключи:"
    ls -la ~/.ssh/*.pub 2>/dev/null || echo "Ключи не найдены"
    read -p "Путь к приватному ключу: " SSH_KEY_PATH
    
    if [ ! -f "$SSH_KEY_PATH" ]; then
        echo "❌ Файл ключа не найден: $SSH_KEY_PATH"
        exit 1
    fi
    
    SSH_PRIVATE_KEY=$(cat "$SSH_KEY_PATH")
fi

echo ""
echo "🚀 Установка секретов в GitHub..."

# Установка основных секретов
gh secret set SERVER_HOST --body "$SERVER_HOST"
echo "✅ SERVER_HOST установлен"

gh secret set SERVER_USER --body "$SERVER_USER" 
echo "✅ SERVER_USER установлен"

gh secret set SERVER_PORT --body "$SERVER_PORT"
echo "✅ SERVER_PORT установлен"

gh secret set POSTGRES_PASSWORD --body "$POSTGRES_PASSWORD"
echo "✅ POSTGRES_PASSWORD установлен"

gh secret set SSH_PRIVATE_KEY --body "$SSH_PRIVATE_KEY"
echo "✅ SSH_PRIVATE_KEY установлен"

# Установка Binance секретов если указаны
if [ ! -z "$BINANCE_API_KEY" ]; then
    gh secret set BINANCE_API_KEY --body "$BINANCE_API_KEY"
    gh secret set BINANCE_SECRET_KEY --body "$BINANCE_SECRET_KEY"
    echo "✅ Binance API секреты установлены"
fi

echo ""
echo "🎉 Все секреты успешно настроены!"
echo ""
echo "📋 Установленные секреты:"
gh secret list

echo ""
echo "🚀 Следующие шаги:"
echo "1. Сделайте commit и push для запуска автодеплоя"
echo "2. Проверьте Actions: https://github.com/$(gh repo view --json owner,name -q '.owner.login + \"/\" + .name')/actions"
echo "3. После деплоя проверьте: http://$SERVER_HOST:8000/health"
echo ""
echo "✨ PostgreSQL OrderBook Collector готов к развертыванию с 200 символами MM анализа!"