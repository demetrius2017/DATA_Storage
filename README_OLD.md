# 📊 DATA_Storage: Система сбора данных Binance OrderBook

**Цель:** Надежный сбор реальных данных orderbook с биржи Binance в тиковой частоте для последующего обучения ML моделей. Данные сохраняются в PostgreSQL базу данных на Digital Ocean.

## 🎯 Что делает система

Система осуществляет **24/7 сбор тиковых данных** с книги покупок/продаж (orderbook) биржи Binance:

- **WebSocket подключение** к Binance API в реальном времени
- **Тиковая частота** — фиксация каждого изменения в orderbook
- **Хранение в PostgreSQL** на Digital Ocean для надежности и масштабируемости
- **Автоматическое индексирование** по времени и символам для быстрых запросов

## 🗄️ Архитектура хранения данных

### PostgreSQL на Digital Ocean
- **Managed Database** — автоматические backup и мониторинг
- **Высокая производительность** — оптимизированные индексы для тиковых данных
- **Масштабируемость** — легкое увеличение ресурсов по мере роста данных
- **SSL подключение** — безопасная передача данных

### Схема таблицы orderbook
```sql
CREATE TABLE orderbook_data (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timestamp BIGINT NOT NULL,
    local_timestamp BIGINT NOT NULL,
    ask_amount DECIMAL(20,8),
    ask_price DECIMAL(20,8),
    bid_price DECIMAL(20,8),
    bid_amount DECIMAL(20,8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрых запросов
CREATE INDEX idx_orderbook_symbol_timestamp ON orderbook_data(symbol, timestamp);
CREATE INDEX idx_orderbook_created_at ON orderbook_data(created_at);
```

## 📈 Формат данных

Каждая запись содержит снимок лучших bid/ask цен:

**Пример записи в PostgreSQL:**
```sql
INSERT INTO orderbook_data VALUES (
    DEFAULT, 'binance-futures', 'SOLUSDT', 
    1751328000003000, 1751328000007356,
    548.95, 154.74, 154.73, 745.47,
    DEFAULT
);
```

**Поля:**
- `exchange` — биржа (binance-futures)
- `symbol` — торговая пара (BTCUSDT, SOLUSDT и др.)
- `timestamp` — время сервера биржи (микросекунды)
- `local_timestamp` — локальное время получения (микросекунды)
- `ask_price/ask_amount` — лучшая цена/объем продажи
- `bid_price/bid_amount` — лучшая цена/объем покупки

## 🏗️ Архитектура системы

### Phase 1: Сбор данных (WebSocket)
```
collector/websocket/binance_collector.py    # WebSocket клиент
collector/processing/orderbook_processor.py # Обработка снимков
```

### Phase 2: База данных PostgreSQL
```
collector/storage/postgres_manager.py       # Интеграция с PostgreSQL
collector/storage/connection_pool.py        # Пул соединений
collector/storage/batch_inserter.py         # Массовые вставки
```

### Phase 3: Экспорт для ML
```
collector/export/sql_exporter.py            # SQL запросы для выборки данных
collector/export/csv_exporter.py            # Экспорт в CSV из PostgreSQL
collector/export/parquet_exporter.py        # Экспорт в Parquet из PostgreSQL
```

### Мониторинг
```
collector/monitor/health_checker.py # Мониторинг состояния
collector/monitor/metrics.py        # Сбор метрик
```

## 🚀 Быстрый старт

### Установка зависимостей
```bash
pip install websockets pandas pyarrow psycopg2-binary asyncpg
```

### Настройка PostgreSQL на Digital Ocean

1. **Создание Managed Database:**
   - Зайти в Digital Ocean панель управления
   - Database → Create → PostgreSQL
   - Выбрать регион и конфигурацию
   - Получить connection string

2. **Конфигурация подключения:**
   Создать файл `.env`:
   ```env
   # Binance API
   BINANCE_API_KEY=your_api_key
   BINANCE_SECRET_KEY=your_secret_key
   
   # PostgreSQL Digital Ocean
   DB_HOST=your-db-host.db.ondigitalocean.com
   DB_PORT=25060
   DB_NAME=defaultdb
   DB_USER=doadmin
   DB_PASSWORD=your_password
   DB_SSLMODE=require
   ```

### Запуск коллектора
```bash
# Один символ в PostgreSQL
python -m collector.main --symbol BTCUSDT --production

# Несколько символов
python -m collector.main --symbols BTCUSDT ETHUSDT SOLUSDT --production
```

### Параметры запуска
- `--symbol` — торговая пара (BTCUSDT, ETHUSDT, SOLUSDT и др.)
- `--symbols` — несколько торговых пар одновременно
- `--production` — использовать реальный Binance API (не testnet)
- `--monitor` — запустить мониторинг состояния

## 📊 Объемы данных в PostgreSQL

**Производительность тиковых данных:**
- BTCUSDT: ~45 записей/минута = ~2700 записей/час
- ETHUSDT: ~32 записи/минута = ~1920 записей/час  
- Altcoins: ~20 записей/минута = ~1200 записей/час

**Размер базы данных:**
- ~100 байт на запись в PostgreSQL
- BTCUSDT: ~270KB/час, ~6.5MB/сутки
- Все основные пары: ~50-100MB/сутки

**Оптимизация PostgreSQL:**
- Партиционирование по дате для больших объемов
- Автоматические vacuum и analyze для производительности
- Индексы по symbol + timestamp для быстрых запросов

## 🔧 Конфигурация

### Файл конфигурации: `collector/config/settings.json`
```json
{
  "database": {
    "type": "postgresql",
    "connection_pool_size": 10,
    "batch_size": 100,
    "reconnect_attempts": 5
  },
  "collection": {
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "buffer_size": 50,
    "flush_interval": 10
  },
  "monitoring": {
    "web_port": 8080,
    "metrics_interval": 60
  }
}
```

## 📋 Требования к серверу

**Минимальные:**
- RAM: 1 ГБ
- Disk: 50 ГБ/месяц на символ
- Network: стабильное соединение
- Python: 3.8+

**Рекомендуемые:**
- RAM: 2 ГБ
- Disk: 100 ГБ/месяц на символ (с резервом)
- Network: выделенный канал
- Backup: ежедневный бэкап данных

## 🛡️ Политика безопасности

### ✅ Разрешено
- Реальные WebSocket подключения к Binance API
- Сжатие и архивация собранных данных
- Экспорт в стандартные форматы (CSV, Parquet)

### ❌ Запрещено
- Mock, синтетические или случайные данные
- Торговые операции или изменение позиций
- Модификация торговых настроек или API ключей

## 📁 Структура проекта

```
collector/
├── main.py                 # Точка входа
├── websocket/              # WebSocket компоненты
│   ├── binance_collector.py
│   └── connection_manager.py
├── processing/             # Обработка данных
│   ├── orderbook_processor.py
│   └── data_validator.py
├── storage/                # Хранение данных
│   ├── data_manager.py
│   ├── compressor.py
│   └── file_rotator.py
├── export/                 # Экспорт данных
│   ├── csv_exporter.py
│   └── parquet_exporter.py
├── monitor/                # Мониторинг
│   ├── health_checker.py
│   ├── metrics.py
│   └── web_dashboard.py
├── config/                 # Конфигурация
│   └── settings.json
└── docs/                   # Документация
    ├── api_spec.md
    ├── server_integration.md
    └── data_collection_action_plan.md
```

## 🔍 Мониторинг

### Веб-интерфейс
Откройте `http://localhost:8080` для просмотра:
- Статус подключения к Binance
- Количество собранных записей
- Объем данных по времени
- Графики активности orderbook

### Логи
Логи сохраняются в `collector/logs/`:
- `collector.log` — основной лог
- `websocket.log` — логи WebSocket соединения
- `error.log` — ошибки и исключения

## 🚨 Важные примечания

1. **Только реальные данные** — запрещено использовать mock или синтетические данные
2. **Тестирование только через main.py** — не создавать демо-версии
3. **Все пути с префиксом collector/** — следовать структуре проекта
4. **API Binance** — использовать только официальные эндпоинты

## 📞 Техническая поддержка

При проблемах проверьте:
1. Статус подключения к интернету
2. Лимиты API Binance
3. Свободное место на диске
4. Логи ошибок в `collector/logs/`

---

**Версия:** 1.0  
**Дата обновления:** 20 сентября 2025  
**Статус:** Активная разработка
