#!/usr/bin/env python3
"""
Docker Entrypoint для PostgreSQL OrderBook Collector
Инициализация базы данных и запуск сбора данных с 200 символами MM фокуса
"""

import asyncio
import os
import sys
import logging
import signal
import time
from pathlib import Path

# Добавляем корневую папку в PYTHONPATH
sys.path.insert(0, '/app')

from collector.config.symbols_mm_focused import SYMBOLS_200, validate_symbols
from collector.ingestion.batch_ingestor import BatchIngestor
from collector.monitoring.health_monitor import MonitoringSystem
from collector.database.connection import DatabaseConnection

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/collector.log')
    ]
)
logger = logging.getLogger(__name__)

class ProductionCollector:
    """Главный класс для production развертывания"""
    
    def __init__(self):
        self.ingestor = None
        self.monitoring_system = None
        self.db_connection = None
        self.shutdown_event = asyncio.Event()
        
        # Environment variables
        self.database_url = os.getenv('DATABASE_URL')
        self.batch_size = int(os.getenv('BATCH_SIZE', '500'))
        self.flush_interval = int(os.getenv('FLUSH_INTERVAL', '30'))
        self.shards = int(os.getenv('SHARDS', '5'))
        self.monitoring_port = int(os.getenv('MONITORING_PORT', '8000'))
        
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required")
    
    async def init_database(self):
        """Инициализация базы данных и создание схемы"""
        logger.info("🔧 Initializing database connection...")
        
        self.db_connection = DatabaseConnection(self.database_url)
        await self.db_connection.connect()
        
        # Создание схемы если не существует
        schema_file = Path('/app/collector/database/schema.sql')
        if schema_file.exists():
            logger.info("📋 Creating database schema...")
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            await self.db_connection.execute_script(schema_sql)
            logger.info("✅ Database schema created successfully")
        else:
            logger.warning("⚠️ Schema file not found, skipping schema creation")
    
    async def validate_symbols_config(self):
        """Валидация конфигурации символов"""
        logger.info("🎯 Validating Market Maker symbols configuration...")
        
        try:
            validate_symbols()
            logger.info(f"✅ Validated {len(SYMBOLS_200)} symbols for MM analysis")
            logger.info(f"📊 Starting with: {SYMBOLS_200[0]}")
            logger.info(f"📊 Ultra low-cap symbols: {len(SYMBOLS_200[-30:])}")
        except Exception as e:
            logger.error(f"❌ Symbol validation failed: {e}")
            raise
    
    async def start_batch_ingestor(self):
        """Запуск batch ingestor с 200 символами"""
        logger.info("🚀 Starting PostgreSQL batch ingestor...")
        
        config = {
            'database_url': self.database_url,
            'symbols': SYMBOLS_200,
            'batch_size': self.batch_size,
            'flush_interval': self.flush_interval,
            'shards': self.shards,
            'max_retries': int(os.getenv('MAX_RETRIES', '5')),
            'enable_monitoring': True
        }
        
        self.ingestor = BatchIngestor(config)
        
        # Запуск в background task
        asyncio.create_task(self.ingestor.start())
        logger.info(f"✅ Batch ingestor started with {len(SYMBOLS_200)} symbols")
    
    async def start_health_monitor(self):
        """Запуск health monitoring dashboard"""
        logger.info("📊 Starting health monitoring dashboard...")
        
        # Используем MonitoringSystem, который поднимает aiohttp dashboard с /health
        self.monitoring_system = MonitoringSystem(
            db_connection_string=self.database_url,
            dashboard_port=self.monitoring_port
        )
        
        # Запуск в background task
        asyncio.create_task(self.monitoring_system.start())
        logger.info(f"✅ Monitoring system started on port {self.monitoring_port}")
    
    async def wait_for_shutdown(self):
        """Ожидание сигнала на завершение"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, initiating shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        await self.shutdown_event.wait()
    
    async def cleanup(self):
        """Graceful shutdown всех компонентов"""
        logger.info("🔄 Starting graceful shutdown...")
        
        tasks = []
        
        if self.ingestor:
            tasks.append(self.ingestor.stop())
        
        if self.monitoring_system:
            tasks.append(self.monitoring_system.stop())
        
        if self.db_connection:
            tasks.append(self.db_connection.close())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ Cleanup completed")
    
    async def run(self):
        """Главный цикл приложения"""
        try:
            logger.info("🚀 Starting PostgreSQL OrderBook Collector (Production)")
            logger.info(f"🎯 Market Maker Analysis Focus: {len(SYMBOLS_200)} symbols")
            
            # Инициализация
            await self.validate_symbols_config()
            await self.init_database()
            
            # Запуск компонентов
            await self.start_batch_ingestor()
            await self.start_health_monitor()
            
            logger.info("🎉 All components started successfully!")
            logger.info(f"📊 Monitoring: http://localhost:{self.monitoring_port}/health")
            logger.info("🔄 Press Ctrl+C to stop")
            
            # Ожидание завершения
            await self.wait_for_shutdown()
            
        except Exception as e:
            logger.error(f"💥 Fatal error: {e}")
            sys.exit(1)
        finally:
            await self.cleanup()

async def main():
    """Entrypoint для Docker контейнера"""
    # Создание необходимых директорий
    os.makedirs('/app/logs', exist_ok=True)
    os.makedirs('/app/data', exist_ok=True)
    
    # Ожидание доступности PostgreSQL
    logger.info("⏳ Waiting for PostgreSQL to be ready...")
    for attempt in range(30):
        try:
            # Простая проверка доступности БД
            import asyncpg
            database_url = os.getenv('DATABASE_URL')
            conn = await asyncpg.connect(database_url)
            await conn.close()
            logger.info("✅ PostgreSQL is ready!")
            break
        except Exception as e:
            if attempt == 29:
                logger.error(f"❌ PostgreSQL not available after 30 attempts: {e}")
                sys.exit(1)
            logger.info(f"⏳ Attempt {attempt + 1}/30: PostgreSQL not ready, waiting...")
            time.sleep(2)
    
    # Запуск collector
    collector = ProductionCollector()
    await collector.run()

if __name__ == "__main__":
    asyncio.run(main())