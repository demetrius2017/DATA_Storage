# 🚀 CLOUD DEPLOYMENT: Digital Ocean + Docker + 200 Trading Pairs

## 🎯 Архитектура облачного развертывания

```
┌─────────────────────────────────────────────────────────────────┐
│                        DIGITAL OCEAN CLOUD                      │
├─────────────────────────────────────────────────────────────────┤
│  🖥️  Droplet (4GB RAM, 2 vCPU)                                  │
│  ├── 🐳 Docker Collector Container                              │
│  │   ├── 📊 200 Trading Pairs Collection                       │
│  │   ├── 🔄 Connection Pooling                                 │
│  │   └── 📈 ~9000 records/minute throughput                    │
│  │                                                             │
│  ├── 🐳 API Container                                           │
│  │   ├── 🌐 REST API for data access                           │
│  │   ├── 📊 Grafana dashboard                                  │
│  │   └── 🔍 Query interface                                    │
│  │                                                             │
│  └── 🐳 Monitoring Container                                    │
│      ├── 📊 Prometheus metrics                                 │
│      ├── 📈 Health monitoring                                  │
│      └── 🚨 Alerting system                                    │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  🗄️  Managed PostgreSQL Database                               │
│  ├── 💾 8GB RAM, 4 vCPU                                        │
│  ├── 🔄 Automatic backups                                      │
│  ├── 📊 ~13GB/day storage growth                               │
│  └── 🌍 Global SSL access                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 МАСШТАБИРОВАНИЕ НА 200 ТОРГОВЫХ ПАР

### Расчет нагрузки
```
200 символов × 45 записей/мин = 9,000 записей/минуту
9,000 записей/мин × 100 байт = 900KB/минуту
900KB/мин × 1440 мин/день = ~1.3GB/день
1.3GB/день × 30 дней = ~40GB/месяц
```

### Требования к ресурсам
- **Droplet:** 4GB RAM, 2 vCPU, 80GB SSD
- **PostgreSQL:** 8GB RAM, 4 vCPU, 100GB storage
- **Сетевая пропускная способность:** 50+ Mbps

---

## 🐳 DOCKER КОНТЕЙНЕРИЗАЦИЯ

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY collector/ ./collector/
COPY api/ ./api/
COPY scripts/ ./scripts/

# Создание пользователя для безопасности
RUN useradd -m -u 1000 collector && chown -R collector:collector /app
USER collector

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Точка входа
ENTRYPOINT ["python", "-m"]
CMD ["collector.main"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  collector:
    build: .
    restart: unless-stopped
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_SECRET_KEY=${BINANCE_SECRET_KEY}
      - SYMBOLS_CHUNK_SIZE=50
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
    command: ["collector.main", "--config", "/app/config/production.json", "--production"]
    healthcheck:
      test: ["CMD", "python", "-c", "import psutil; exit(0 if psutil.cpu_percent() < 90 else 1)"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

  api:
    build: .
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
    command: ["api.main", "--port", "8080"]
    depends_on:
      - collector

  monitoring:
    image: prom/prometheus:latest
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana:/etc/grafana/provisioning

volumes:
  prometheus_data:
  grafana_data:
```

---

## 🏗️ КОНФИГУРАЦИЯ ДЛЯ 200 СИМВОЛОВ

### config/production.json
```json
{
  "storage": {
    "type": "postgresql",
    "batch_size": 100,
    "buffer_size": 500,
    "flush_interval": 5
  },
  "postgresql": {
    "pool_size": 20,
    "max_overflow": 30,
    "pool_timeout": 30,
    "pool_recycle": 3600
  },
  "collection": {
    "symbols_chunk_size": 50,
    "concurrent_collectors": 4,
    "rate_limit_per_second": 1000,
    "reconnect_attempts": 5,
    "reconnect_delay": 30
  },
  "monitoring": {
    "metrics_interval": 60,
    "health_check_interval": 30,
    "prometheus_port": 9091
  },
  "logging": {
    "level": "INFO",
    "rotation": "midnight",
    "retention": 7
  }
}
```

### Список 200 символов
```python
# config/symbols.py
TOP_200_SYMBOLS = [
    # Топ-10 по объему
    "BTCUSDT", "ETHUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT",
    "SOLUSDT", "DOTUSDT", "DOGEUSDT", "AVAXUSDT", "MATICUSDT",
    
    # DeFi токены
    "UNIUSDT", "LINKUSDT", "AAVEUSDT", "COMPUSDT", "MKRUSDT",
    "SUSHIUSDT", "CRVUSDT", "YFIUSDT", "1INCHUSDT", "ALPHAUSDT",
    
    # Layer 1 блокчейны
    "FTMUSDT", "NEARUSDT", "ATOMUSDT", "ALGOUSDT", "EOSUSDT",
    "TRXUSDT", "XTZUSDT", "FILUSDT", "VETUSDT", "ICXUSDT",
    
    # Meme и Social
    "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT", "WIFUSDT",
    
    # Продолжение до 200 символов...
    # (полный список в отдельном файле)
]
```

---

## 🚀 РАЗВЕРТЫВАНИЕ НА DIGITAL OCEAN

### 1. Создание инфраструктуры
```bash
# Создание Droplet
doctl compute droplet create orderbook-collector \
  --size s-2vcpu-4gb \
  --image ubuntu-22-04-x64 \
  --region nyc1 \
  --ssh-keys YOUR_SSH_KEY_ID \
  --tag-names production,orderbook

# Создание PostgreSQL кластера
doctl databases create orderbook-db \
  --engine pg \
  --version 14 \
  --size db-s-4vcpu-8gb \
  --region nyc1 \
  --num-nodes 1
```

### 2. Настройка Droplet
```bash
# Подключение к серверу
ssh root@YOUR_DROPLET_IP

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установка Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Клонирование проекта
git clone https://github.com/demetrius2017/DATA_Storage.git
cd DATA_Storage
```

### 3. Настройка окружения
```bash
# Создание .env файла
cat > .env << EOF
# PostgreSQL (из Digital Ocean)
DB_HOST=your-db-do-user-123456-0.b.db.ondigitalocean.com
DB_PORT=25060
DB_NAME=defaultdb
DB_USER=doadmin
DB_PASSWORD=your_password

# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key

# Мониторинг
GRAFANA_PASSWORD=secure_password_123
EOF
```

### 4. Запуск системы
```bash
# Сборка и запуск контейнеров
docker-compose up -d

# Проверка статуса
docker-compose ps
docker-compose logs -f collector
```

---

## 🌍 API ДЛЯ ГЛОБАЛЬНОГО ДОСТУПА

### REST API эндпоинты
```python
# api/main.py
from fastapi import FastAPI, Query
from typing import List, Optional
import asyncpg
import pandas as pd

app = FastAPI(title="OrderBook Data API", version="1.0.0")

@app.get("/symbols")
async def get_available_symbols():
    """Получить список доступных торговых пар."""
    pass

@app.get("/data/{symbol}")
async def get_symbol_data(
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = Query(1000, le=10000)
):
    """Получить данные по символу."""
    pass

@app.get("/stats")
async def get_collection_stats():
    """Статистика сбора данных."""
    pass

@app.get("/health")
async def health_check():
    """Проверка здоровья системы."""
    pass
```

### Примеры использования API
```bash
# Получить последние 1000 записей BTCUSDT
curl "http://YOUR_DROPLET_IP:8080/data/BTCUSDT?limit=1000"

# Получить данные за последний час
curl "http://YOUR_DROPLET_IP:8080/data/ETHUSDT?start_time=1695211200&limit=5000"

# Статистика всех символов
curl "http://YOUR_DROPLET_IP:8080/stats"
```

---

## 📊 МОНИТОРИНГ И АЛЕРТИНГ

### Grafana Dashboard метрики
- 📈 **Throughput:** записей в секунду по символам
- 🔄 **Database connections:** активные соединения
- 💾 **Memory usage:** использование RAM контейнерами
- 🌐 **Network:** входящий/исходящий трафик
- ⚠️ **Errors:** ошибки подключения к Binance/PostgreSQL

### Alerting правила
```yaml
# monitoring/alerts.yml
groups:
  - name: orderbook_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(collector_errors_total[5m]) > 0.1
        for: 2m
        
      - alert: DatabaseConnectionFailed
        expr: up{job="postgresql"} == 0
        for: 1m
        
      - alert: LowDataIngestion
        expr: rate(records_inserted_total[5m]) < 100
        for: 5m
```

---

## 💰 СТОИМОСТЬ INFRASTRUCTURE

### Ежемесячные расходы Digital Ocean
```
🖥️  Droplet (4GB RAM, 2 vCPU):     $24/месяц
🗄️  PostgreSQL (8GB RAM, 4 vCPU):   $60/месяц  
🌐 Load Balancer (если нужен):      $12/месяц
📦 Snapshot backups:                $5/месяц
────────────────────────────────────────────
💳 ИТОГО:                          ~$101/месяц
```

### Прогноз роста данных
```
📊 Текущий объем: ~40GB/месяц
📈 Через 6 месяцев: ~240GB
💾 Рекомендуемый storage: 500GB
💰 Стоимость storage: +$25/месяц
```

---

## 🚀 ПЛАН РАЗВЕРТЫВАНИЯ (4-6 часов)

### Phase 1: Подготовка (1 час)
1. Создать Droplet и PostgreSQL на Digital Ocean
2. Настроить DNS и SSL сертификаты
3. Подготовить 200 символов список

### Phase 2: Контейнеризация (2 часа)  
1. Создать Dockerfile и docker-compose.yml
2. Реализовать PostgreSQL менеджер
3. Добавить API модуль

### Phase 3: Развертывание (1 час)
1. Загрузить код на сервер
2. Запустить контейнеры
3. Проверить работу всех компонентов

### Phase 4: Мониторинг (1 час)
1. Настроить Grafana dashboards
2. Проверить алертинг
3. Протестировать API

### Phase 5: Тестирование (1 час)
1. Stress-тест 200 символов
2. Проверить стабильность 24/7
3. Валидация данных через API

---

**🎯 Результат:** Полностью автоматизированная система сбора 200 торговых пар с глобальным доступом к данным через API!