# 🔧 GitHub CLI команды для настройки секретов (пошагово)

## Предварительная подготовка

### 1. Установка GitHub CLI (если не установлен)
```bash
# macOS
brew install gh

# или скачать с https://cli.github.com/
```

### 2. Авторизация в GitHub
```bash
gh auth login
# Выберите GitHub.com → HTTPS → Авторизуйтесь через браузер
```

### 3. Проверка репозитория
```bash
cd /Users/dmitrijnazarov/Projects/DATA_Storage
gh repo view
```

## 🔐 Установка секретов по порядку

### Шаг 1: Основные секреты сервера
```bash
# Замените на реальные значения
gh secret set SERVER_HOST --body "your.server.ip.address"
gh secret set SERVER_USER --body "root" 
gh secret set SERVER_PORT --body "22"
```

### Шаг 2: База данных
```bash
# Замените на безопасный пароль
gh secret set POSTGRES_PASSWORD --body "secure_db_password_2025"
```

### Шаг 3: SSH ключ (самый важный)
```bash
# Вариант A: Если у вас уже есть SSH ключ
gh secret set SSH_PRIVATE_KEY --body "$(cat ~/.ssh/id_rsa)"

# Вариант B: Создать новый SSH ключ специально для деплоя
ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_deploy -N ""
ssh-copy-id -i ~/.ssh/github_deploy.pub user@your.server.ip
gh secret set SSH_PRIVATE_KEY --body "$(cat ~/.ssh/github_deploy)"
```

### Шаг 4: Binance API (опционально)
```bash
# Только если нужен доступ к Binance API
gh secret set BINANCE_API_KEY --body "your_api_key_here"
gh secret set BINANCE_SECRET_KEY --body "your_secret_key_here"
```

## ✅ Проверка результата

### Посмотреть список установленных секретов:
```bash
gh secret list
```

### Проверить статус последнего workflow:
```bash
gh run list --limit 1
```

## 🚀 Запуск деплоя

### После установки всех секретов:
```bash
# Сделать любое изменение для триггера деплоя
echo "# Deploy trigger $(date)" >> README.md
git add .
git commit -m "🚀 Trigger deployment with configured secrets"
git push origin master
```

### Отслеживание деплоя:
```bash
# Смотреть статус в реальном времени
gh run watch

# Или открыть в браузере
gh run view --web
```

## 🎯 Что нужно подготовить заранее:

1. **IP адрес сервера** - где будет развернута система
2. **SSH доступ** - ключ или пароль для подключения к серверу
3. **Пароль PostgreSQL** - для базы данных (придумать безопасный)
4. **Binance API** (опционально) - если планируете использовать приватные эндпоинты

## ⚡ Быстрый скрипт для копирования:

```bash
#!/bin/bash
# Замените значения на реальные и выполните:

gh secret set SERVER_HOST --body "123.456.789.10"
gh secret set SERVER_USER --body "root"
gh secret set SERVER_PORT --body "22"
gh secret set POSTGRES_PASSWORD --body "MySecurePassword123!"

# SSH ключ (выберите один из вариантов):
# gh secret set SSH_PRIVATE_KEY --body "$(cat ~/.ssh/id_rsa)"
# или
# gh secret set SSH_PRIVATE_KEY --body "$(cat ~/.ssh/id_ed25519)"

# Опционально:
# gh secret set BINANCE_API_KEY --body "your_api_key"
# gh secret set BINANCE_SECRET_KEY --body "your_secret"

echo "✅ Все секреты установлены!"
gh secret list
```

---

💡 **Совет:** Скопируйте команды выше, замените значения на реальные и выполните в терминале по порядку.