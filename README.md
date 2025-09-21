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

Отличная идея: собирать реальный поток сразу в PostgreSQL под 200 пар, чтобы ежедневно тренироваться на “вчерашнем” и быстро подтверждать валидность ML. Ниже — практичная схема: что собирать, как хранить, индексы/партиционирование, объём/нагрузка и как это подключить к текущему пайплайну.

Что собирать (минимум → расширение)
Приоритет 1 (лёгкий, полезный всем моделям):

bookTicker (top-of-book): best_bid, best_ask, bid_qty, ask_qty, event_time.
aggTrade (или trade): цена/объём сделки, сторона агрессора, event_time.
Приоритет 2 (для микро‑структуры и сильных сигналов):

depth5@100ms или depth10@100ms: массивы [price, qty] на первых 5–10 уровнях + диффы.
mark price/funding (для фьючерсов): события изменения mark price и funding (каждые 8ч).
Рекомендация на старт:

Для всех 200 пар: bookTicker + aggTrade (нагрузка низкая/средняя).
Для топ‑N ликвидных пар: depth5@100ms. По мере стабилизации — расширять на большее число пар.
Схема БД (PostgreSQL/Timescale)
Сразу делайте нормализацию символов и ключи времени в UTC. Для высоких скоростей — TimescaleDB (hypertable) и компрессия старых партиций. Если TimescaleDB пока нет — используйте natively PARTITION BY RANGE (по дате) + индекс на (symbol_id, ts).

Схема marketdata:

Справочник символов
marketdata.symbols
id bigserial PK
exchange text not null (e.g., 'binance-futures', 'binance-spot')
symbol text not null (e.g., 'SOLUSDT')
instrument_type text (e.g., 'perp', 'spot') null
base_asset text, quote_asset text null
is_active boolean default true
UNIQUE (exchange, symbol)
Поток top-of-book (bookTicker)
marketdata.book_ticker
ts_exchange timestamptz not null — из поля E/1000 (UTC)
ts_ingest timestamptz not null default now()
symbol_id bigint not null references marketdata.symbols(id)
update_id bigint null — поле u (если есть)
best_bid double precision not null
best_ask double precision not null
bid_qty double precision not null
ask_qty double precision not null
spread double precision not null — best_ask − best_bid
mid double precision not null — (best_ask + best_bid)/2
PRIMARY KEY (symbol_id, ts_exchange, update_id) — если u отсутствует, можно PK(symbol_id, ts_exchange, ts_ingest)
INDEX (symbol_id, ts_exchange)
Сделки (aggTrade)
marketdata.trades
ts_exchange timestamptz not null — из E/1000
ts_ingest timestamptz not null default now()
symbol_id bigint not null
agg_trade_id bigint not null — a
price double precision not null — p
qty double precision not null — q
is_buyer_maker boolean not null — m
PRIMARY KEY (symbol_id, agg_trade_id)
INDEX (symbol_id, ts_exchange)
События глубины (depth updates) — два варианта
Вариант А (простой, быстрый для ingestion): хранить raw JSONB на событие:

marketdata.depth_events
ts_exchange timestamptz not null — E/1000
ts_ingest timestamptz not null default now()
symbol_id bigint not null
first_update_id bigint not null — U
final_update_id bigint not null — u
prev_final_update_id bigint null — pu
bids jsonb not null — массив массивов [["price","qty"], ...] как строки или числа
asks jsonb not null
PRIMARY KEY (symbol_id, final_update_id)
INDEX (symbol_id, ts_exchange)
Вариант Б (сразу “удобно для фич”): хранить top‑N в плоском виде по столбцам

marketdata.orderbook_topN
ts_exchange timestamptz not null
symbol_id bigint not null
b1_price double precision, b1_qty double precision, ..., bN_price, bN_qty
a1_price double precision, a1_qty double precision, ..., aN_price, aN_qty
первичные derived фичи: i1, iN, microprice, wall_size, wall_dist_bps, …
PRIMARY KEY (symbol_id, ts_exchange)
INDEX (symbol_id, ts_exchange)
Обычно наполняется фоновым job’ом из depth_events (raw→features). Это разгружает ingestion и упрощает эволюцию фич.
Материализованные агрегаты (для быстрых “вчерашних” обучений)
marketdata.bt_1s (или hypertable) — ресемплинг book_ticker в 1s:
ts_second timestamptz, symbol_id
mid_open, mid_high, mid_low, mid_close, spread_mean, …
marketdata.trade_1s — агр по сделкам:
ts_second, symbol_id
trade_count, vol_sum, vwap, imbalance_buy_sell, …
marketdata.depth_100ms_topN — если требуется сверхскоростной оффлайн (тонко)
Ротация/компрессия:

book_ticker/trades: хранить “сырое” 7–30 дней (Timescale compress + retention policy).
depth_events (сырая глубина): может быть объёмной — 3–7 дней в сыром виде + derived topN/фичи хранить дольше (30–90 дней) с компрессией.
агрегаты 1s/100ms — дольше (90–180 дней), они эффективнее для быстрых тренировок.
Примечания по типам:

double precision — быстрый. Если нужна точность — numeric(20,10) на price/qty, но цена по скорости. Для ML обычно double ок.
Всегда UTC (timestamptz), индексы по (symbol_id, ts_exchange).
Нагрузка, шардирование и ingestion
Соединения WS:
Binance Combined Streams: wss://fstream.binance.com/stream?streams=... Можно “сшивать” по 50–100 пар на одно соединение (зависит от каналов).
Рекомендуется 3–5 соединений на 200 пар (1–2 для bookTicker, 1–2 для aggTrade, 1 для depth топовых пар).
Batching в БД:
Пакетная вставка каждые 50–500 записей (psycopg2 execute_values или asyncpg copy_records_to_table).
Транзакции короткие, autocommit off.
Индексы: заранее, но без лишних; уникальные ключи защищают от дублей.
Партиционирование:
TimescaleDB hypertable time(ts_exchange), partitioning by symbol_id (space partition).
Если без Timescale: PARTITION BY RANGE (date_trunc('day', ts_exchange)) и отдельные таблицы на сутки (±хэш по symbol_id).
Отказоустойчивость:
Идём “at least once”: используем уникальные ключи, UPSERT ON CONFLICT DO NOTHING/UPDATE для дедупликации.
Логи “последний обработанный update_id” per symbol для depth (в памяти + периодически в таблицу offsets).
“Вчерашний” датасет для обучения — быстрый доступ
Окно: [00:00:00Z; 23:59:59Z] вчера. Для SOLUSDT и/или 200 пар.
Брать заранее агрегированное:
Из bt_1s и trade_1s: очень быстрый скан одной партиции.
Для depth — из orderbook_topN или готовых feature‑таблиц (уже рассчитанных I1/I10/microprice/OFI).
Для обучения:
ML процесс получает список symbol_id и ts диапазон, делает SELECT’ы в фич‑таблицах, строит матрицу признаков и запускает тренинг на живых данных за “вчера”.
Порог/калибровка — отдельно (Platt/Isotonic), лог в отчёт.
Быстрый DDL (схематично)
create schema marketdata;
symbols, book_ticker, trades — как выше.
depth_events (jsonb) + orderbook_topN (фичи сверху 5–10 уровней).
Индексы: (symbol_id, ts_exchange) везде; PK под уникальность (например, trades по agg_trade_id, depth по final_update_id).
Инкрементальные фичи (для студентов)
На ingestion не навешиваем тяжёлые расчёты. Считаем “лёгкие” derived поля (spread, mid). Всё сложное — в фоновом job’е:

Каждые N минут/сек: пробегаем depth_events по окну и пересчитываем orderbook_topN + фичи:
I1, I5/I10, microprice, max_wall_size/dist, OFI(T=1–3s), liquidity slope.
Пишем в отдельную фич‑таблицу (например, marketdata.features_100ms или features_1s), на которой тренируем “вчера” и валидируем “сегодня”.
Объёмы и реальность
bookTicker: у топ‑пар 30–150 updates/sec, у остальных — <1/sec. В среднем по 200 парам поток приемлем при батчинге.
depth@100ms: тяжёлый — делайте сначала на 20–50 самых ликвидных пар; остальным — позже или на 250–500ms.
trades: умеренно; полезно для OFI и валидации ликвидности.
Интеграция с текущим проектом
Инжестор: отдельный сервис (Python asyncio) c шардированием потоков и батч‑записью в PG.
В copilot добавить адаптер Postgres ридера (read‑only) для “вчерашних” выборок (перенастроить оффлайн инструменты на SELECT вместо Parquet, когда БД готова).
В MCP можно добавить read‑only инструменты (getOrderBookSnapshotFromDB, getTradesSlice) — сначала описать в mcp_server_spec.md, потом реализовать.
Подсказки по эксплуатации
Включите autovacuum и мониторинг блоатинга; для Timescale — включить компрессию >7 дней.
Любые “heavy” SELECT’ы в off-peak время, материализованные представления на сутки.
Храните “сырой” JSONB depth и плоскую topN таблицу — это баланс между гибкостью и скоростью обучения.
Итог
Идея целиком — Адвокат ЗА:

Централизация live‑данных в Postgres/Timescale для 200 пар даёт непрерывный, реплицируемый источник “вчерашнего” обучения и быстрой валидации ML.
Схема разделяет сырые события (надёжно) и производные фичи (быстро для тренировки), с ретеншеном и компрессией.
Старт с bookTicker+trades для всех и глубины для топ‑пар — разумный компромисс по нагрузке.
Идея целиком — Адвокат ПРОТИВ:

Depth@100ms по 200 парам может быть тяжёлым без Timescale/партиционирования/батчинга.
Переход на БД требует доработки ридеров и фич‑построителей, и повторной калибровки/валидации.
Конкретная часть/правки — Адвокат ЗА:

Дал конкретную схему таблиц, ключи, индексы, ретеншен, и план фоновых roll‑up’ов для “вчерашнего” обучения.
Обозначил безопасную стратегию ingestion (batch + UPSERT) и шардирование WS.
Конкретная часть/правки — Адвокат ПРОТИВ:

Не включены SQL‑скрипты целиком и код инжестора — это следующий шаг; есть нюансы по числовым типам/индексам под конкретные винтажи PG/Timescale.
Не описана полноценная high‑availability/replica архитектура (по необходимости добавим).
Вывод: предлагаю начать с развертывания схеме marketdata (symbols, book_ticker, trades, depth_events) и батч‑инжестора, запустить сбор на 200 пар (depth на топ‑N), и в течение 1–3 дней переключить “вчерашние” тренировки студентов на SELECT из Postgres. Если хотите, подготовлю DDL и каркас инжестора под asyncio + asyncpg с батч‑вставками и простым шардированием потоков.