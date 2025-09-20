# 📊 ЛОГИКА СБОРА ДАННЫХ ORDERBOOK

## 🎯 Цель проекта

Создание системы **24/7 сбора тиковых данных** с книги покупок/продаж (orderbook) биржи Binance для последующего обучения ML моделей на удаленном сервере.

## 🏗️ 3-фазная архитектура

### Phase 1: Получение данных (Real-time Collection)
**Цель:** Получение РЕАЛЬНЫХ данных orderbook от Binance в реальном времени

**Компоненты:**
- `BinanceCollector` — WebSocket подключение к Binance
- `OrderBookProcessor` — обработка снимков orderbook  
- `DataValidator` — валидация входящих данных

**Технологии:**
- WebSocket к Binance API
- JSON orderbook snapshots и updates
- Тиковая частота (вся активность в orderbook)
- Rate Limit защита

### Phase 2: Накопление и сжатие (Data Accumulation)
**Цель:** Накопление и сжатие данных на удаленном сервере

**Компоненты:**
- `DataCompressor` — сжатие и архивация данных
- `StorageManager` — управление хранилищем на сервере
- `FileRotator` — ротация файлов по времени

**Технологии:**
- Gzip сжатие для оптимизации хранения
- Автоматическая ротация файлов (24 часа)
- Резервное копирование

### Phase 3: Экспорт данных (ML Export)
**Цель:** Экспорт данных в формате CSV для обучения ML

**Компоненты:**
- `CSVExporter` — экспорт в CSV формат
- `ParquetExporter` — экспорт в Parquet формат
- `DataFormatter` — форматирование для ML pipeline

## 📊 Формат данных

### Входящие данные (WebSocket)
```json
{
  "e": "depthUpdate",
  "E": 1751328000003,
  "s": "BTCUSDT", 
  "U": 123456789,
  "u": 123456790,
  "b": [["43250.50", "0.75"]],
  "a": [["43251.00", "1.25"]]
}
```

### Выходные данные (CSV)
```csv
exchange,symbol,timestamp,local_timestamp,ask_amount,ask_price,bid_price,bid_amount
binance-futures,BTCUSDT,1751328000003000,1751328000007356,1.25,43251.00,43250.50,0.75
```

## 🔄 Поток данных

```
Binance API → WebSocket → OrderBookProcessor → DataValidator
     ↓
StorageManager → DataCompressor → FileRotator
     ↓  
CSVExporter → ML Pipeline
```

## 🛡️ Политики безопасности

### ✅ Разрешенные операции
- Реальные WebSocket подключения к Binance API
- Read-only операции с orderbook данными
- Сжатие и архивация собранных данных
- Экспорт в стандартные форматы (CSV, Parquet)

### ❌ Запрещенные операции
- Mock, синтетические, random или файловые источники данных
- Торговые операции или любые write операции на бирже
- Модификация торговых конфигураций или API ключей

## 📈 Метрики и мониторинг

### Ключевые метрики
- **Latency:** время от получения до записи
- **Throughput:** количество записей в секунду
- **Storage:** объем данных на диске
- **Uptime:** время работы без сбоев

### Компоненты мониторинга
- `HealthMonitor` — мониторинг состояния системы
- `MetricsCollector` — сбор метрик производительности
- `WebDashboard` — веб-интерфейс для мониторинга

## 🔧 Конфигурация

### Основные параметры
```json
{
  "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "websocket": {
    "url": "wss://fstream.binance.com/ws/",
    "reconnect_interval": 5,
    "ping_interval": 20
  },
  "storage": {
    "base_dir": "/data/binance_orderbook",
    "compression": "gzip",
    "rotation_hours": 24,
    "backup_enabled": true
  },
  "monitoring": {
    "web_port": 8080,
    "metrics_interval": 60,
    "health_check_interval": 30
  }
}
```

## 🚀 Запуск системы

### Основная команда
```bash
python -m collector.main --symbol BTCUSDT --output-dir /path/to/storage
```

### Параметры командной строки
- `--symbol` — торговая пара (BTCUSDT, ETHUSDT, SOLUSDT)
- `--output-dir` — директория для сохранения данных
- `--config` — путь к файлу конфигурации
- `--compress` — включить сжатие (по умолчанию true)
- `--monitor` — запустить веб-мониторинг
- `--verbose` — подробные логи

## 📋 Требования к системе

### Минимальные требования
- **RAM:** 1 ГБ
- **Disk:** 50 ГБ/месяц на символ
- **Network:** стабильное соединение (5+ Мбит/с)
- **Python:** 3.8+

### Рекомендуемые требования
- **RAM:** 2+ ГБ
- **Disk:** 100+ ГБ/месяц на символ
- **Network:** выделенный канал (10+ Мбит/с)
- **Backup:** ежедневное резервное копирование

## 🧪 Тестирование

### Основной тест
```bash
python -m collector.main --symbol BTCUSDT --test-mode
```

### Unit тесты
```bash
python -m pytest tests/test_binance_collector.py
python -m pytest tests/test_orderbook_processor.py
python -m pytest tests/test_data_manager.py
```

### Интеграционные тесты
```bash
python -m pytest tests/test_full_pipeline.py
```

## 📁 Структура проекта

```
collector/
├── main.py                 # Точка входа
├── websocket/              # WebSocket компоненты
│   ├── binance_collector.py
│   ├── connection_manager.py
│   └── rate_limiter.py
├── processing/             # Обработка данных
│   ├── orderbook_processor.py
│   ├── data_validator.py
│   └── data_formatter.py
├── storage/                # Хранение данных
│   ├── data_manager.py
│   ├── compressor.py
│   └── file_rotator.py
├── export/                 # Экспорт данных
│   ├── csv_exporter.py
│   ├── parquet_exporter.py
│   └── ml_formatter.py
├── monitor/                # Мониторинг
│   ├── health_checker.py
│   ├── metrics_collector.py
│   └── web_dashboard.py
├── config/                 # Конфигурация
│   ├── settings.json
│   └── logging.yaml
├── docs/                   # Документация
│   ├── api_spec.md
│   ├── server_integration.md
│   └── deployment_guide.md
└── tests/                  # Тесты
    ├── test_binance_collector.py
    ├── test_orderbook_processor.py
    └── test_full_pipeline.py
```

## ⚠️ Важные ограничения

1. **Только реальные данные** — запрещено использовать mock или синтетические данные
2. **Тестирование только через main.py** — не создавать демо-версии или упрощенные файлы
3. **Все пути с префиксом collector/** — строго следовать структуре проекта
4. **API Binance только официальные** — использовать только документированные эндпоинты

## 📞 Поддержка и обслуживание

### Логи системы
- `collector/logs/collector.log` — основной лог
- `collector/logs/websocket.log` — логи WebSocket соединения
- `collector/logs/error.log` — ошибки и исключения

### Типичные проблемы
1. **Потеря соединения** — автоматический реконнект через 5 сек
2. **Переполнение диска** — автоматическая ротация файлов
3. **Rate Limit** — встроенная защита от превышения лимитов
4. **Высокая нагрузка** — масштабирование по символам

---

**Версия:** 1.0  
**Дата:** 20 сентября 2025  
**Статус:** Техническое задание