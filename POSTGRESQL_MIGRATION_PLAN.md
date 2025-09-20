# 🗄️ МИГРАЦИЯ НА POSTGRESQL: План Действий

## 🎯 Цель
Переход от файлового хранения к PostgreSQL базе данных на Digital Ocean для:
- Надежности и backup-ов
- Масштабируемости 
- Быстрых SQL запросов для ML
- Централизованного доступа к данным

---

## 📋 ПЛАН РЕАЛИЗАЦИИ

### Phase 1: Подготовка инфраструктуры
1. **Создание PostgreSQL на Digital Ocean:**
   - Managed Database PostgreSQL 14+
   - Минимум 1GB RAM, 25GB storage
   - SSL соединения обязательны
   - Backup retention: 7 дней

2. **Настройка схемы базы данных:**
   ```sql
   -- Основная таблица для orderbook данных
   CREATE TABLE orderbook_data (
       id BIGSERIAL PRIMARY KEY,
       exchange VARCHAR(50) NOT NULL DEFAULT 'binance-futures',
       symbol VARCHAR(20) NOT NULL,
       timestamp BIGINT NOT NULL,
       local_timestamp BIGINT NOT NULL,
       ask_amount DECIMAL(20,8),
       ask_price DECIMAL(20,8),
       bid_price DECIMAL(20,8),
       bid_amount DECIMAL(20,8),
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );

   -- Индексы для производительности
   CREATE INDEX idx_orderbook_symbol_timestamp ON orderbook_data(symbol, timestamp);
   CREATE INDEX idx_orderbook_created_at ON orderbook_data(created_at);
   CREATE INDEX idx_orderbook_symbol ON orderbook_data(symbol);
   ```

3. **Переменные окружения (.env):**
   ```env
   # PostgreSQL Digital Ocean
   DB_HOST=your-cluster-do-user-123456-0.b.db.ondigitalocean.com
   DB_PORT=25060
   DB_NAME=defaultdb
   DB_USER=doadmin
   DB_PASSWORD=your_password...
   DB_SSLMODE=require
   DB_POOL_SIZE=10
   DB_BATCH_SIZE=50
   ```

### Phase 2: Код PostgreSQL интеграции

#### 1. Создать `collector/storage/postgres_manager.py`
```python
import asyncio
import asyncpg
import logging
from typing import Dict, Any, List
from datetime import datetime

class PostgreSQLManager:
    """Менеджер для работы с PostgreSQL на Digital Ocean."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool = None
        self.logger = logging.getLogger(__name__)
        self.batch_buffer = []
        self.batch_size = config.get('batch_size', 50)
        
    async def connect(self):
        """Создание пула соединений."""
        try:
            self.pool = await asyncpg.create_pool(
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                ssl='require',
                min_size=2,
                max_size=self.config.get('pool_size', 10)
            )
            self.logger.info("Connected to PostgreSQL")
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
            
    async def save_record(self, record: Dict[str, Any]):
        """Сохранение записи с батчингом."""
        self.batch_buffer.append(record)
        
        if len(self.batch_buffer) >= self.batch_size:
            await self._flush_batch()
            
    async def _flush_batch(self):
        """Массовая вставка записей."""
        if not self.batch_buffer:
            return
            
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO orderbook_data 
                    (exchange, symbol, timestamp, local_timestamp, 
                     ask_amount, ask_price, bid_price, bid_amount)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    [(r['exchange'], r['symbol'], r['timestamp'], r['local_timestamp'],
                      r['ask_amount'], r['ask_price'], r['bid_price'], r['bid_amount'])
                     for r in self.batch_buffer]
                )
            
            self.logger.info(f"Inserted {len(self.batch_buffer)} records")
            self.batch_buffer.clear()
            
        except Exception as e:
            self.logger.error(f"Failed to insert batch: {e}")
            # В случае ошибки можем сохранить в файл как fallback
            
    async def shutdown(self):
        """Завершение работы."""
        await self._flush_batch()  # Сохранить оставшиеся записи
        if self.pool:
            await self.pool.close()
```

#### 2. Обновить `collector/storage/data_manager.py`
```python
# Добавить поддержку PostgreSQL как опции
class DataManager:
    def __init__(self, config: Dict[str, Any]):
        storage_type = config.get('storage', {}).get('type', 'file')
        
        if storage_type == 'postgresql':
            from .postgres_manager import PostgreSQLManager
            self.storage = PostgreSQLManager(config['postgresql'])
        else:
            # Оставить файловое хранение как fallback
            self.storage = FileStorage(config)
```

#### 3. Обновить конфигурацию
```json
{
  "storage": {
    "type": "postgresql"
  },
  "postgresql": {
    "host": "your-cluster.db.ondigitalocean.com",
    "port": 25060,
    "database": "defaultdb",
    "user": "doadmin", 
    "password": "from_env",
    "pool_size": 10,
    "batch_size": 50
  }
}
```

### Phase 3: Тестирование и развертывание

1. **Локальное тестирование:**
   - Создать test PostgreSQL в Docker
   - Протестировать все операции
   - Убедиться в корректности batch INSERT

2. **Digital Ocean тестирование:**
   - Подключение к managed database
   - Тест производительности
   - Тест обработки ошибок

3. **Production развертывание:**
   - Плавная миграция с file → PostgreSQL
   - Мониторинг производительности
   - Backup стратегия

---

## 📊 ОЖИДАЕМЫЕ ПРЕИМУЩЕСТВА

### Производительность
- **Batch INSERT:** ~50 записей за раз вместо одиночных
- **Connection pooling:** переиспользование соединений
- **Индексы:** быстрые запросы по symbol + timestamp

### Надежность  
- **Автоматические backup:** Digital Ocean managed service
- **Репликация:** встроенная в managed database
- **Мониторинг:** интеграция с DO metrics

### Масштабируемость
- **Вертикальное масштабирование:** увеличение ресурсов DO
- **Партиционирование:** разделение по датам при росте
- **Множественные коллекторы:** параллельная запись

---

## 🚀 NEXT STEPS

1. **Создать PostgreSQL на Digital Ocean** (15 мин)
2. **Реализовать PostgreSQLManager** (2-3 часа)
3. **Интегрировать в существующий код** (1 час)
4. **Протестировать на production API** (30 мин)
5. **Документировать процесс развертывания** (30 мин)

**Общее время:** ~4-5 часов работы для полной миграции.