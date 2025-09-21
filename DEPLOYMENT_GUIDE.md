# 🚀 PostgreSQL OrderBook Collector - Production Deployment Guide

## 📋 Итоговая архитектура системы

### 🏗️ Компоненты системы
- **PostgreSQL + TimescaleDB** - высокопроизводительная БД для временных рядов
- **OrderBook Collector** - асинхронный WebSocket коллектор (5 шардов)
- **Batch Ingestor** - пакетная запись в БД (500 записей/batch)
- **Health Monitor** - real-time мониторинг на порту 8000
- **Redis** - кэширование и rate limiting
- **Nginx** - reverse proxy для production

### 🎯 Market Maker Analysis Focus
- **200 уникальных символов** начиная с SOLUSDT
- **10 уровней ликвидности** для точного анализа MM активности
- **Исключены высоколиквидные пары** (BTCUSDT/ETHUSDT) для чистоты сигналов

## 🔧 Созданные файлы

### Docker инфраструктура
```
├── Dockerfile                      # Production образ с Ubuntu 22.04 + Python 3.11
├── docker-compose.production.yml   # Multi-service setup с PostgreSQL/TimescaleDB
├── requirements.txt                # Python зависимости для PostgreSQL + WebSocket
└── .env.production                 # Production конфигурация
```

### Application код  
```
├── collector/
│   ├── config/symbols_mm_focused.py    # 200 символов MM анализа
│   ├── scripts/docker_entrypoint.py    # Production entrypoint
│   ├── database/
│   │   ├── schema.sql                  # PostgreSQL схема с TimescaleDB
│   │   ├── connection.py              # Database connection manager
│   │   └── init_timescale.sql         # TimescaleDB инициализация
│   ├── ingestion/batch_ingestor.py     # Async WebSocket batch collector
│   ├── monitoring/health_monitor.py    # Health dashboard на порту 8000
│   └── adapters/postgres_ml_adapter.py # ML интеграция с PostgreSQL
```

### CI/CD автодеплой
```
├── .github/workflows/deploy.yml       # GitHub Actions автодеплой
├── GITHUB_SECRETS_SETUP.md           # Инструкция по настройке secrets
└── DEPLOYMENT_GUIDE.md               # Этот файл
```

## 🔐 Настройка GitHub Secrets

### Обязательные секреты в Settings → Secrets and variables → Actions:

```bash
SERVER_HOST=your.server.ip.address     # IP адрес вашего сервера
SERVER_USER=root                       # Пользователь с Docker правами
SSH_PRIVATE_KEY=-----BEGIN...-----     # SSH приватный ключ
POSTGRES_PASSWORD=secure_password      # Пароль для PostgreSQL
BINANCE_API_KEY=optional_api_key       # Опционально для Binance API
BINANCE_SECRET_KEY=optional_secret     # Опционально для Binance API
```

## 📊 Market Maker символы (200 pairs)

### Структура ликвидности:
1. **Tier 1 (Medium):** SOLUSDT, ADAUSDT, DOTUSDT... (10 символов)
2. **Tier 2 (Moderate):** ATOMUSDT, VETUSDT, FILUSDT... (20 символов)  
3. **Tier 3-10:** Убывающая ликвидность до ultra low-cap (170 символов)

### Фокус на MM анализе:
- ✅ Начинается с SOLUSDT как запрошено
- ✅ Исключены BTCUSDT/ETHUSDT для чистоты MM сигналов
- ✅ Приоритет на менее ликвидных парах для лучшего MM трекинга

## 🚀 Процесс развертывания

### 1. Подготовка сервера
```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Создание рабочей директории
sudo mkdir -p /opt/orderbook-collector
sudo chown $USER:$USER /opt/orderbook-collector
```

### 2. Настройка SSH ключей
```bash
# Генерация SSH ключа
ssh-keygen -t ed25519 -C "github-actions-deploy"

# Копирование на сервер  
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@your.server.ip

# Приватный ключ → GitHub Secrets (SSH_PRIVATE_KEY)
cat ~/.ssh/id_ed25519
```

### 3. Настройка GitHub Secrets
См. подробную инструкцию в `GITHUB_SECRETS_SETUP.md`

### 4. Деплой
```bash
# Автоматический деплой при push в master/main
git add .
git commit -m "Deploy PostgreSQL OrderBook Collector with 200 MM symbols"
git push origin master
```

## 📈 Мониторинг после деплоя

### Доступные эндпоинты:
- **Health Dashboard:** `http://your.server.ip:8000/health`
- **Metrics:** `http://your.server.ip:8000/metrics`  
- **WebSocket Status:** `http://your.server.ip:8000/websockets`
- **Symbol Stats:** `http://your.server.ip:8000/symbols`

### Проверка состояния на сервере:
```bash
ssh user@your.server.ip
cd /opt/orderbook-collector

# Состояние контейнеров
docker-compose ps

# Логи коллектора
docker-compose logs -f collector

# Логи PostgreSQL  
docker-compose logs -f postgres

# Health check
curl http://localhost:8000/health
```

## 🎯 Особенности системы

### WebSocket сбор данных:
- **5 шардов** для распределения нагрузки
- **500 записей/batch** для оптимальной производительности
- **Автореконнект** при обрывах соединения
- **Rate limiting** защита от превышения лимитов API

### PostgreSQL + TimescaleDB:
- **Hypertables** для оптимизации временных рядов
- **Continuous aggregates** для быстрых аналитических запросов
- **Retention policies** для автоматической ротации данных
- **Compression** для экономии дискового пространства

### Market Maker анализ:
- **200 символов** специально отобранных для MM трекинга
- **10 уровней ликвидности** от medium до ultra low-cap
- **Старт с SOLUSDT** как запрашивал пользователь
- **Фокус на менее популярных парах** для чистоты MM сигналов

## ✅ Проверка готовности

- [x] **Dockerfile** создан с Python 3.11 + PostgreSQL клиентом
- [x] **docker-compose.yml** настроен с TimescaleDB
- [x] **requirements.txt** содержит все зависимости
- [x] **Entrypoint script** для инициализации БД и запуска коллектора
- [x] **GitHub Actions workflow** для автодеплоя
- [x] **GitHub Secrets guide** создан
- [x] **Production config** настроен
- [x] **200 символов MM фокуса** валидированы

## 🔮 Next Steps

1. **Добавьте GitHub Secrets** согласно `GITHUB_SECRETS_SETUP.md`
2. **Сделайте push** - автоматически запустится деплой
3. **Проверьте мониторинг** на `http://your.server.ip:8000`
4. **Настройте алерты** для production мониторинга
5. **Оптимизируйте параметры** на основе реальных метрик

---

🎉 **Система готова к production развертыванию!** 

Просто настройте GitHub Secrets и сделайте commit - автодеплой сделает всё остальное.