# 📊 Binance OrderBook Data Collector

Производственная система сбора данных orderbook с биржи Binance для 200 торговых пар с развертыванием на Digital Ocean.

## 🎯 Описание проекта

Данный проект предназначен для:
- **Сбора реальных данных orderbook** с биржи Binance через WebSocket API (~9,000 сообщений/минуту)
- **Накопления в PostgreSQL** на управляемой базе данных Digital Ocean
- **Масштабирования до 200 торговых пар** с контейнеризацией Docker
- **Предоставления REST API** для доступа к данным из любой точки мира

## 🚀 Быстрый старт (5 минут)

### ⚡ Удаленное развертывание (рекомендуется)

```bash
# Клонируйте репозиторий
git clone https://github.com/demetrius2017/DATA_Storage.git
cd DATA_Storage

# Установите зависимости
./scripts/install_dependencies.sh

# Разверните на удаленном сервере (замените YOUR_SERVER_IP)
./scripts/deploy_remote_collector.sh YOUR_SERVER_IP

# Запустите сбор данных
python scripts/remote_collector_client.py --server http://YOUR_SERVER_IP start \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --database-url "postgresql://user:pass@host:port/db"
```

### 🐳 Автоматическое развертывание (legacy)

```bash
# Клонируйте репозиторий
git clone https://github.com/demetrius2017/DATA_Storage.git
cd DATA_Storage

# Запустите автоматическое развертывание
chmod +x manage.sh
./manage.sh deploy
```

**Подробная инструкция:** [collector/docs/deployment_guide.md](collector/docs/deployment_guide.md)

## 🏗️ Архитектура облачного решения

```
Digital Ocean Infrastructure
├── Droplet (4GB RAM, 2 vCPU)          # Основной сервер
│   ├── Docker Containers
│   │   ├── orderbook-collector        # Сбор данных (200 символов)
│   │   ├── fastapi-server             # REST API 
│   │   ├── prometheus                 # Метрики
│   │   └── grafana                    # Мониторинг
│   └── Nginx Proxy                    # Load balancer
└── Managed PostgreSQL (1GB RAM)       # База данных
    ├── SSL Connections
    ├── Automatic Backups
    └── Global Access
```

## 📊 Поддерживаемые торговые пары

**200 основных торговых пар Binance Futures:**

```python
# Топ-20 по объемам (всегда активны)
TIER_1 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", ...]

# Альткойны (50 пар)
TIER_2 = ["ADAUSDT", "DOGEUSDT", "MATICUSDT", "LINKUSDT", ...]

# Расширенный список (130 дополнительных пар)
TIER_3 = [...] 
```

**Полный список:** [collector/config/symbols.py](collector/config/symbols.py)

## 🌐 Доступ к сервисам

После развертывания доступны по всему миру:

| Сервис | URL | Назначение |
|--------|-----|-----------|
| **REST API** | `http://YOUR_IP:8080` | Доступ к данным orderbook |
| **Remote Management** | `http://YOUR_IP:8000` | Удаленное управление коллектором |
| **Grafana** | `http://YOUR_IP:3000` | Мониторинг и дашборды |
| **Prometheus** | `http://YOUR_IP:9090` | Метрики системы |

## 🎮 Удаленное управление коллектором

### Автоматическое развертывание на сервере

```bash
# Развертывание системы управления на удаленном сервере
./scripts/deploy_remote_collector.sh YOUR_SERVER_IP root

# Установка зависимостей локально
./scripts/install_dependencies.sh
```

### Управление через командную строку

```bash
# Проверить статус коллектора
python scripts/remote_collector_client.py --server http://YOUR_IP summary

# Запустить сбор данных
python scripts/remote_collector_client.py --server http://YOUR_IP start \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --database-url "postgresql://..."

# Остановить коллектор
python scripts/remote_collector_client.py --server http://YOUR_IP stop

# Мониторинг в реальном времени
python scripts/remote_collector_client.py --server http://YOUR_IP monitor --duration 30

# Валидация соответствия ТЗ
python scripts/remote_collector_client.py --server http://YOUR_IP validate
```

### Web Dashboard для управления

После развертывания доступен интерактивный dashboard:

- **Management Dashboard**: `http://YOUR_IP:8000/`
- **Real-time Monitoring**: WebSocket обновления каждые 5 секунд
- **API Documentation**: `http://YOUR_IP:8000/docs`

### Автоматическая валидация ТЗ

Система автоматически проверяет соответствие собираемых данных техническому заданию:

- ✅ **Структура данных**: корректность полей и типов
- ✅ **Свежесть данных**: проверка что данные не старше 5 минут  
- ✅ **Качество данных**: отсутствие NULL значений, валидность цен
- ✅ **Частота обновлений**: минимум 1 обновление в минуту для активных символов

## 📈 API Endpoints

### Получение данных orderbook

```bash
# Текущее состояние BTCUSDT
curl http://YOUR_IP:8080/data/BTCUSDT

# Исторические данные за период
curl "http://YOUR_IP:8080/data/BTCUSDT?from=2024-01-01T00:00:00Z&to=2024-01-01T01:00:00Z"

# Статистика всех символов
curl http://YOUR_IP:8080/stats

# Здоровье системы
curl http://YOUR_IP:8080/health
```

### Пример ответа API

```json
{
  "symbol": "BTCUSDT",
  "timestamp": 1703875200.123,
  "bids": [
    {"price": "43500.00", "quantity": "0.15", "level": 0},
    {"price": "43499.99", "quantity": "0.25", "level": 1}
  ],
  "asks": [
    {"price": "43500.01", "quantity": "0.20", "level": 0},
    {"price": "43500.02", "quantity": "0.30", "level": 1}
  ],
  "spread": "0.01",
  "mid_price": "43500.005"
}
```

## 🎛️ Управление системой

### Удаленное управление (рекомендуется)

```bash
# Развертывание системы управления
./scripts/deploy_remote_collector.sh YOUR_SERVER_IP

# Запуск коллектора для конкретных символов
python scripts/remote_collector_client.py --server http://YOUR_IP start \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --database-url "postgresql://..."

# Мониторинг статуса в реальном времени
python scripts/remote_collector_client.py --server http://YOUR_IP monitor

# Проверка качества данных по ТЗ
python scripts/remote_collector_client.py --server http://YOUR_IP validate

# Статистика базы данных
python scripts/remote_collector_client.py --server http://YOUR_IP db-stats
```

### Локальное управление (legacy)

```bash
# Проверка статуса
./manage.sh status

# Просмотр логов
./manage.sh logs collector

# Масштабирование символов
./manage.sh scale 100

# Перезапуск сервисов
./manage.sh restart

# Мониторинг производительности
./manage.sh monitor

# Создание бэкапа
./manage.sh backup
```

### Масштабирование по этапам

```bash
# Этап 1: Тестирование (3 символа)
./manage.sh scale 3

# Этап 2: Пилот (50 символов) 
./manage.sh scale 50

# Этап 3: Продакшен (200 символов)
./manage.sh scale 200
```

## 📊 Производительность системы

### Ожидаемая нагрузка

| Параметр | 50 символов | 200 символов |
|----------|-------------|---------------|
| **Сообщений/мин** | ~2,250 | ~9,000 |
| **Данных/день** | ~100MB | ~400MB |
| **Данных/месяц** | ~3GB | ~12GB |
| **CPU Usage** | 15-25% | 30-50% |
| **Memory Usage** | 30-40% | 60-80% |

### Оптимизация производительности

- **Connection Pooling**: 20 соединений к PostgreSQL
- **Batch Processing**: Обработка по 100 записей
- **Compression**: Сжатие данных на уровне БД
- **Indexing**: Оптимизированные индексы по timestamp и symbol

## 🛡️ Безопасность и надежность

### Безопасность

- ✅ SSL соединения к PostgreSQL
- ✅ Firewall конфигурация (только необходимые порты)
- ✅ READ-ONLY API ключи Binance
- ✅ Безопасное хранение credentials в переменных окружения
- ✅ Non-root контейнеры Docker

### Надежность

- ✅ Автоматическое восстановление WebSocket соединений
- ✅ Health checks для всех сервисов
- ✅ Graceful shutdown при обновлениях
- ✅ Автоматические бэкапы PostgreSQL
- ✅ Monitoring с алертами в Grafana

## 💰 Стоимость инфраструктуры

| Компонент | Спецификация | Стоимость/месяц |
|-----------|--------------|-----------------|
| **Droplet** | 4GB RAM, 2 vCPU, 80GB SSD | $24 |
| **PostgreSQL** | 1GB RAM, 10GB Storage | $15 |
| **Backup Space** | 20GB | $2 |
| **Total** | | **$41/месяц** |

*Стоимость для 200 торговых пар с круглосуточной работой*

## 🔧 Конфигурация для разных нагрузок

### Минимальная конфигурация (тестирование)

```bash
# 2GB Droplet + Shared PostgreSQL
# 3-10 символов
# ~$15/месяц
```

### Производственная конфигурация

```bash
# 4GB Droplet + Managed PostgreSQL
# 50-200 символов  
# ~$41/месяц
```

### Enterprise конфигурация

```bash
# 8GB Droplet + High-Performance PostgreSQL
# 200+ символов с high-frequency данными
# ~$85/месяц
```

## 📈 Мониторинг в Grafana

### Доступные дашборды

1. **System Overview**
   - CPU, Memory, Disk usage
   - Network I/O
   - Container status

2. **OrderBook Metrics**
   - Messages per minute by symbol
   - WebSocket connection status
   - Data processing latency

3. **Database Performance**
   - PostgreSQL connections
   - Query performance
   - Storage growth

4. **Business Metrics**
   - Market coverage (active symbols)
   - Data quality scores
   - Uptime statistics

## 🔧 Локальная разработка

### Для разработчиков

```bash
# Клонирование для разработки
git clone https://github.com/demetrius2017/DATA_Storage.git
cd DATA_Storage

# Локальная установка
pip install -r requirements.txt

# Локальный запуск с 1 символом
python -m collector.main --symbol BTCUSDT --output-dir ./data

# Запуск тестов
python -m pytest tests/ -v
```

### Docker для локальной разработки

```bash
# Локальная сборка
docker-compose -f docker-compose.local.yml up --build

# Только база данных
docker-compose -f docker-compose.local.yml up postgres

# Разработка с hot-reload
docker-compose -f docker-compose.dev.yml up
```

## 📋 Roadmap

### ✅ Phase 1: Базовая инфраструктура
- [x] WebSocket коллектор Binance
- [x] PostgreSQL интеграция  
- [x] Docker контейнеризация
- [x] Digital Ocean развертывание

### ✅ Phase 2: Масштабирование
- [x] 200 торговых пар
- [x] Batch processing
- [x] Connection pooling
- [x] Monitoring stack

### ✅ Phase 3: Удаленное управление
- [x] REST API для управления коллектором
- [x] WebSocket мониторинг в реальном времени
- [x] Web Dashboard с визуальным интерфейсом
- [x] Автоматическая валидация соответствия ТЗ
- [x] Системы systemd для production
- [x] Клиент командной строки для управления

### 🔄 Phase 4: Оптимизация (в процессе)
- [ ] Real-time аналитика
- [ ] Machine Learning features
- [ ] Advanced alerting
- [ ] Performance tuning

### 📋 Phase 4: Enterprise features
- [ ] Multi-region deployment
- [ ] Load balancing
- [ ] Advanced security
- [ ] Custom analytics

## 🤝 Участие в разработке

### Для контрибьюторов

1. Fork репозитория
2. Создайте feature branch
3. Следуйте стандартам кода (PEP 8)
4. Добавьте тесты для нового функционала
5. Убедитесь что тесты проходят
6. Создайте Pull Request

### Требования

- Python 3.11+
- Docker и Docker Compose
- PostgreSQL для локальной разработки
- Binance API ключи (testnet для разработки)

### Структура проекта

```
DATA_Storage/
├── scripts/                          # Скрипты управления
│   ├── deploy_remote_collector.sh     # Автоматическое развертывание
│   ├── remote_collector_client.py     # Клиент управления
│   └── install_dependencies.sh        # Установка зависимостей
├── collector/                         # Основной модуль коллектора
│   ├── management/                    # Система удаленного управления
│   │   └── collector_api.py           # FastAPI сервер
│   ├── validation/                    # Валидация ТЗ
│   │   └── data_validator.py          # Проверка соответствия
│   ├── ingestion/                     # Сбор данных
│   └── docs/                          # Документация
│       └── deployment_guide.md        # Руководство по развертыванию
├── DEPLOYMENT_READY.md               # Готовность к развертыванию
└── README.md                         # Этот файл
```

## 📞 Поддержка

### Получение помощи

1. **Quick Start Guide**: [QUICK_START.md](QUICK_START.md)
2. **Deployment Guide**: [CLOUD_DEPLOYMENT_GUIDE.md](CLOUD_DEPLOYMENT_GUIDE.md)
3. **GitHub Issues**: [Создать issue](https://github.com/demetrius2017/DATA_Storage/issues)
4. **Email поддержка**: support@orderbook-collector.dev

### Troubleshooting

```bash
# Проверка статуса
./manage.sh status

# Детальные логи
./manage.sh logs collector

# Проверка здоровья системы
curl http://YOUR_IP:8080/health
```

## 📄 Лицензия

MIT License - подробности в файле [LICENSE](LICENSE).

---

## 🎉 Начните прямо сейчас!

**Удаленное развертывание (1-2 команды):**

```bash
git clone https://github.com/demetrius2017/DATA_Storage.git && cd DATA_Storage && \
./scripts/install_dependencies.sh && \
./scripts/deploy_remote_collector.sh YOUR_SERVER_IP
```

**Управление через CLI:**

```bash
# Запуск сбора данных
python scripts/remote_collector_client.py --server http://YOUR_IP start \
    --symbols BTCUSDT ETHUSDT SOLUSDT --database-url "postgresql://..."

# Мониторинг в реальном времени  
python scripts/remote_collector_client.py --server http://YOUR_IP monitor
```

**Ваш удаленно управляемый OrderBook коллектор будет готов через 5 минут!** 🚀

---

*Собирайте данные с 200 торговых пар Binance с удаленным управлением, real-time мониторингом и автоматической валидацией ТЗ. Идеально для машинного обучения, алгоритмической торговли и рыночной аналитики.*