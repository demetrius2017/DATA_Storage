# 🚀 POSTGRES ORDERBOOK SYSTEM DEPLOYMENT

> Deployment status (2025-09-21): Redeploy prepared to enforce Binance Futures endpoints (REST=https://fapi.binance.com, WS=wss://fstream.binance.com/ws/). Health endpoint now exposes active endpoints. Entrypoint filters symbols to valid Futures USDT-perp. After rollout, verify http://178.128.24.209:8000/health and confirm non-zero 5/60m ingestion counts.

### 🔒 One‑shot настройка DigitalOcean Firewall (без деплоя)

```
# Предусловия: экспортируйте DO_TOKEN и укажите droplet и источники
export DO_TOKEN=...                # Personal Access Token DO
export DO_DROPLET_ID=123456789     # или DO_DROPLET_NAME=your-droplet
export DO_ALLOW_8000_SOURCES="203.0.113.10/32,198.51.100.0/24"  # кто может видеть 8000/tcp

# Прогон dry-run (покажет payload)
python3 collector/management/do_firewall_apply.py --dry-run

# Применение
python3 collector/management/do_firewall_apply.py

# Проверка: должен открыться http://<droplet_public_ip>:8000/health
```

## 📋 Компоненты системы

- **PostgreSQL + TimescaleDB**: основное хранилище с hypertables для 200+ торговых пар
- **Batch Ingestor**: асинхронный сборщик с шардированием WebSocket потоков  
- **Continuous Aggregates**: автоматические 1s агрегаты для "вчерашнего" обучения
- **Monitoring**: real-time мониторинг ingestion rate, latency, data quality

## 🛠️ Системные требования

### Железо
- **CPU**: 8+ cores (рекомендуется 16)
- **RAM**: 16GB minimum (32GB для 200 пар)
- **Storage**: 500GB SSD (NVMe рекомендуется)
- **Network**: стабильное соединение 10+ Mbps

### ПО
- Ubuntu 22.04+ / macOS 12+ / Docker
- Python 3.9+
- PostgreSQL 14+ с TimescaleDB 2.11+

## 💾 1. Database Setup

### PostgreSQL + TimescaleDB Installation

#### Ubuntu/Debian
```bash
# PostgreSQL 15
sudo apt update && sudo apt install postgresql-15 postgresql-client-15

# TimescaleDB
echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" | sudo tee /etc/apt/sources.list.d/timescaledb.list
wget -qO - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo apt-key add -
sudo apt update && sudo apt install timescaledb-2-postgresql-15

# Tune & restart
sudo timescaledb-tune --quiet --yes
sudo systemctl restart postgresql
```

#### macOS
```bash
brew install postgresql@15 && brew services start postgresql@15
brew tap timescale/tap && brew install timescaledb
```

#### Docker Compose
```yaml
version: '3.8'
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: marketdata
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: secure_pg_password
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    command: ["postgres", "-c", "shared_preload_libraries=timescaledb", "-c", "max_connections=200"]
    
volumes:
  pg_data:
```

### Database Configuration
```sql
-- 1. Создание БД и пользователя
CREATE DATABASE marketdata;
CREATE USER ingestor WITH PASSWORD 'strong_ingestor_password';
GRANT ALL PRIVILEGES ON DATABASE marketdata TO ingestor;

-- 2. Активация TimescaleDB
\c marketdata
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 3. Применение схемы
\i /path/to/collector/database/schema.sql

-- 4. Права доступа
GRANT USAGE ON SCHEMA marketdata TO ingestor;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA marketdata TO ingestor;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA marketdata TO ingestor;
```

### PostgreSQL.conf Optimization
```ini
# Основные настройки
shared_preload_libraries = 'timescaledb'
max_connections = 200
shared_buffers = 4GB                    # 25% RAM
effective_cache_size = 12GB             # 75% RAM
work_mem = 32MB
maintenance_work_mem = 1GB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
random_page_cost = 1.1                  # SSD

# TimescaleDB
timescaledb.max_background_workers = 16
```

## 🐍 2. Python Environment

```bash
cd /Users/dmitrijnazarov/Projects/DATA_Storage
python3 -m venv venv && source venv/bin/activate
pip install -r collector/requirements.txt

# Test DB connection
python -c "
import asyncio, asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://ingestor:password@localhost/marketdata')
    print(await conn.fetchval('SELECT version()'))
    await conn.close()
asyncio.run(test())
"
```

## 🔧 3. Production Configuration

### Environment Variables
```bash
# collector/config/.env
DATABASE_URL=postgresql://ingestor:strong_password@localhost:5432/marketdata
BINANCE_WS_BASE=wss://fstream.binance.com/stream
LOG_LEVEL=INFO
BATCH_SIZE=500
BATCH_TIMEOUT=10
SHARDS_COUNT=5
MONITORING_PORT=8000

# Top 50 symbols for testing
SYMBOLS_TEST=BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,DOTUSDT,AVAXUSDT,MATICUSDT,LINKUSDT,UNIUSDT,SHIBUSDT

# All 200 symbols for production  
SYMBOLS_FULL=BTCUSDT,ETHUSDT,BNBUSDT,ADAUSDT,SOLUSDT,XRPUSDT,DOTUSDT,DOGEUSDT,AVAXUSDT,MATICUSDT,SHIBUSDT,LTCUSDT,TRXUSDT,UNIUSDT,LINKUSDT,BCHUSDT,XLMUSDT,ATOMUSDT,ETCUSDT,FILUSDT,VETUSDT,ICPUSDT,FTMUSDT,HBARUSDT,ALGOUSDT,THETAUSDT,XMRUSDT,EOSUSDT,AAVEUSDT,MKRUSDT,KLAYUSDT,AXSUSDT,SANDUSDT,MANAUSDT,IOTAUSDT
```

### Systemd Service (Ubuntu)
```ini
# /etc/systemd/system/orderbook-ingestor.service
[Unit]
Description=OrderBook Batch Ingestor
After=postgresql.service network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/orderbook-collector
Environment=PATH=/opt/orderbook-collector/venv/bin
EnvironmentFile=/opt/orderbook-collector/collector/config/.env
ExecStart=/opt/orderbook-collector/venv/bin/python collector/ingestion/batch_ingestor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 🚀 4. Launch Strategy

### Phase 1: Testing (10 symbols)
```bash
mkdir -p logs
python collector/ingestion/batch_ingestor.py \
  --symbols "BTCUSDT,ETHUSDT,SOLUSDT" \
  --channels "bookTicker,aggTrade" \
  --shards 2
```

### Phase 2: Medium Scale (50 symbols)
```bash
# Start with bookTicker + aggTrade for 50 symbols
export SYMBOLS_50="BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,DOTUSDT,AVAXUSDT,MATICUSDT,LINKUSDT,UNIUSDT,SHIBUSDT,LTCUSDT,TRXUSDT,BCHUSDT,XLMUSDT,ATOMUSDT,ETCUSDT,FILUSDT,VETUSDT,ICPUSDT,FTMUSDT,HBARUSDT,ALGOUSDT,THETAUSDT,XMRUSDT,EOSUSDT,AAVEUSDT,MKRUSDT,KLAYUSDT,AXSUSDT,SANDUSDT,MANAUSDT,IOTAUSDT,NEARUSDT,GMTUSDT,APUSDT,APEUSDT,GALAUSDT,MASKUSDT,LDOUSDT,ROSEUSDT,DYDXUSDT,1INCHUSDT,CHZUSDT,ENSUSDT,PEOPLEUSDT,ANTUSDT,LRCUSDT,JASMYUSDT,DARUSDT,UNFIUSDT"

python collector/ingestion/batch_ingestor.py \
  --symbols "$SYMBOLS_50" \
  --channels "bookTicker,aggTrade" \
  --shards 4
```

### Phase 3: Full Production (200 symbols)
```bash
# Enable systemd service
sudo systemctl enable orderbook-ingestor
sudo systemctl start orderbook-ingestor
sudo systemctl status orderbook-ingestor
```

## 📊 5. Monitoring & Validation

### Real-time Monitoring
```sql
-- Ingestion statistics (run every minute)
SELECT * FROM marketdata.ingestion_stats ORDER BY book_ticker_count_1h DESC;

-- Data quality check  
SELECT * FROM marketdata.data_quality_check;

-- Top active symbols
SELECT 
    s.symbol,
    COUNT(bt.*) as updates_last_hour,
    MAX(bt.ts_exchange) as last_update_utc
FROM marketdata.symbols s
JOIN marketdata.book_ticker bt ON s.id = bt.symbol_id  
WHERE bt.ts_exchange >= NOW() - INTERVAL '1 hour'
GROUP BY s.symbol
ORDER BY updates_last_hour DESC
LIMIT 15;
```

### Performance Validation
```sql
-- Continuous aggregates check
SELECT 
    ts_second,
    symbol_id, 
    mid_close,
    spread_mean,
    update_count
FROM marketdata.bt_1s
WHERE ts_second >= NOW() - INTERVAL '1 hour'
ORDER BY ts_second DESC
LIMIT 20;

-- Yesterday training data test
SELECT COUNT(*) as records_count 
FROM marketdata.get_yesterday_training_data();
```

### Log Monitoring
```bash
# Live tail
tail -f logs/batch_ingestor.log

# Service logs
sudo journalctl -u orderbook-ingestor -f

# Error analysis
grep -i error logs/batch_ingestor.log | tail -20
```

## 🔧 6. Integration with ML Pipeline

### PostgreSQL Data Reader
```python
# collector/adapters/postgres_reader.py
import asyncpg
import pandas as pd
from datetime import date, timedelta

async def get_yesterday_ml_data(symbols: list = None) -> pd.DataFrame:
    """Загрузка вчерашних данных для обучения ML"""
    conn = await asyncpg.connect(DATABASE_URL)
    
    yesterday = date.today() - timedelta(days=1)
    rows = await conn.fetch(
        "SELECT * FROM marketdata.get_yesterday_training_data($1, $2)",
        None, yesterday
    )
    
    await conn.close()
    return pd.DataFrame(rows)

# Usage in ML pipeline
df_yesterday = await get_yesterday_ml_data(['BTCUSDT', 'ETHUSDT'])
# Now use df_yesterday for training instead of Parquet files
```

## ⚡ 7. Performance Expectations

### Throughput
- **200 symbols**: ~30,000 updates/minute total
- **Per symbol**: 30-150 updates/minute (varies by liquidity)
- **Latency**: <5ms from exchange to database
- **Batch efficiency**: 500 records/batch, 10s max age

### Storage
- **Raw data**: ~43M records/day, ~1.3B/month
- **Compressed**: ~50GB/month with TimescaleDB compression
- **Aggregates**: ~2GB/month (much faster for ML)

### "Yesterday" Training
- **Data load**: <30 seconds for full day
- **Processing**: ready for immediate ML training
- **Freshness**: available at 00:01 UTC next day

## 🚨 8. Troubleshooting

### Common Issues

1. **WebSocket disconnections**
   ```bash
   # Check logs for shard status
   grep "Шард.*подключен" logs/batch_ingestor.log
   ```

2. **Database connection pool exhaustion**
   ```sql
   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
   ```

3. **High disk usage**
   ```sql
   -- Check table sizes
   SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
   FROM pg_tables WHERE schemaname = 'marketdata';
   ```

4. **Lagging continuous aggregates**
   ```sql
   SELECT * FROM timescaledb_information.continuous_aggregates;
   ```

### Recovery Procedures

1. **Service restart**
   ```bash
   sudo systemctl restart orderbook-ingestor
   ```

2. **Database maintenance**
   ```sql
   -- Force compression
   SELECT compress_chunk(chunk_name) FROM timescaledb_information.chunks 
   WHERE hypertable_name = 'book_ticker' AND NOT is_compressed;
   
   -- Refresh aggregates
   CALL refresh_continuous_aggregate('marketdata.bt_1s', NOW() - INTERVAL '2 hours', NOW());
   ```

## 📈 Expected Results

После развертывания система обеспечит:
- ✅ **Real-time collection**: 200 торговых пар без потерь
- ✅ **Быстрое обучение**: доступ к "вчерашним" данным за секунды  
- ✅ **Масштабируемость**: готовность к расширению на >500 пар
- ✅ **Надежность**: автоматическое восстановление соединений
- ✅ **Мониторинг**: полная видимость производительности

**Система готова к production deployment!** 🚀