# 🔐 GitHub Secrets Configuration Guide

## Настройка секретов для автодеплоя PostgreSQL OrderBook Collector

### 📋 Обязательные секреты

Перейдите в **Settings → Secrets and variables → Actions** вашего GitHub репозитория и добавьте следующие секреты:

#### 🖥️ Сервер подключения
```bash
SERVER_HOST=your.server.ip.address
SERVER_USER=root  # или ваш пользователь с Docker правами
SERVER_PORT=22    # опционально, по умолчанию 22
```

#### 🔑 SSH ключ
```bash
SSH_PRIVATE_KEY=-----BEGIN OPENSSH PRIVATE KEY-----
[ваш приватный SSH ключ]
-----END OPENSSH PRIVATE KEY-----
```

#### 🗄️ База данных
```bash
POSTGRES_PASSWORD=your_strong_database_password_here
```

#### 🔗 Binance API (опционально)
```bash
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key
```

### 🛠️ Подготовка сервера

#### 1. Установка Docker на удаленном сервере
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### 2. Создание рабочей директории
```bash
sudo mkdir -p /opt/orderbook-collector
sudo chown $USER:$USER /opt/orderbook-collector
```

#### 3. Настройка SSH ключей
```bash
# На локальной машине сгенерируйте SSH ключ
ssh-keygen -t ed25519 -C "github-actions-deploy"

# Скопируйте публичный ключ на сервер
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your.server.ip

# Приватный ключ добавьте в GitHub Secrets как SSH_PRIVATE_KEY
cat ~/.ssh/id_ed25519
```

### 🚀 Процесс деплоя

После настройки секретов деплой происходит автоматически при:
- ✅ Push в ветку `master`/`main`
- ✅ Изменения в файлах `collector/**`, `Dockerfile`, `docker-compose.production.yml`
- ✅ Ручной запуск через GitHub Actions

### 📊 Мониторинг после деплоя

После успешного деплоя доступны:
- 🌐 **Health Dashboard:** `http://your.server.ip:8000/health`
- 📈 **Metrics:** `http://your.server.ip:8000/metrics`
- 🗄️ **PostgreSQL:** `your.server.ip:5432` (только для внутренних подключений)

### 🔧 Проверка состояния на сервере

```bash
# Подключение к серверу
ssh user@your.server.ip

# Переход в рабочую директорию
cd /opt/orderbook-collector

# Проверка состояния контейнеров
docker-compose ps

# Просмотр логов
docker-compose logs -f collector

# Проверка здоровья системы
curl http://localhost:8000/health
```

### 🛡️ Безопасность

1. **Firewall:** Настройте фаервол для разрешения только необходимых портов
   ```bash
   sudo ufw allow 22     # SSH
   sudo ufw allow 8000   # Monitoring dashboard
   sudo ufw enable
   ```

2. **SSL Certificates:** Для production рекомендуется настроить SSL через Nginx
3. **Database Security:** PostgreSQL доступен только внутри Docker сети
4. **Regular Updates:** Регулярно обновляйте Docker образы и систему

### 📝 Пример секретов в GitHub

```
Secrets:
├── SERVER_HOST: 165.232.123.45
├── SERVER_USER: collector
├── SERVER_PORT: 22
├── SSH_PRIVATE_KEY: -----BEGIN OPENSSH PRIVATE KEY-----...
├── POSTGRES_PASSWORD: secure_db_password_2025
├── BINANCE_API_KEY: your_api_key_if_needed
└── BINANCE_SECRET_KEY: your_secret_if_needed
```

### ✅ Проверка готовности

- [ ] Сервер подготовлен (Docker установлен)
- [ ] SSH ключи настроены
- [ ] GitHub Secrets добавлены
- [ ] Workflow файл создан
- [ ] 200 символов MM фокуса валидированы
- [ ] PostgreSQL схема готова

## 🎯 После настройки

Просто сделайте commit и push - GitHub Actions автоматически:
1. 🔨 Соберет Docker образ
2. 📤 Загрузит в GitHub Container Registry  
3. 🚀 Развернет на удаленном сервере
4. ✅ Проверит health check
5. 📊 Запустит сбор данных с 200 символами MM анализа