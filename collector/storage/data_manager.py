"""
Менеджер данных для сохранения и управления собранными данными orderbook.
Поддерживает CSV файлы и PostgreSQL хранение.
"""

import asyncio
import csv
import gzip
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, TextIO
from io import TextIOWrapper

# PostgreSQL поддержка
try:
    from .postgres_manager import PostgreSQLManager, OrderBookData, create_orderbook_data
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False


class DataManager:
    """
    Менеджер для сохранения и управления данными orderbook.
    
    Поддерживает:
    - CSV файлы с сжатием и ротацией
    - PostgreSQL базу данных с batch операциями
    """
    
    def __init__(self, output_dir: str, compress: bool = True, config: Optional[Dict[str, Any]] = None):
        """
        Инициализация менеджера данных.
        
        Args:
            output_dir: Директория для сохранения данных (CSV режим)
            compress: Включить сжатие файлов (CSV режим)
            config: Конфигурация системы
        """
        self.output_dir = Path(output_dir)
        self.compress = compress
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Определяем тип хранения
        storage_config = self.config.get('storage', {})
        self.storage_type = storage_config.get('type', 'csv')
        
        # Инициализация PostgreSQL Manager
        self.postgres_manager = None
        if self.storage_type == 'postgresql' and POSTGRES_AVAILABLE:
            self._init_postgresql()
        else:
            self._init_csv_storage()
        
        # Настройки ротации для CSV
        self.rotation_hours = storage_config.get('rotation_hours', 24)
        
        # Состояние для CSV
        self.current_file: Optional[Union[TextIO, TextIOWrapper]] = None
        self.current_writer = None
        self.file_rotation_time = None
        self.buffer = []
        self.buffer_size = storage_config.get('buffer_size', 1000)
        self.records_written = 0
        self.files_created = 0  # Добавляем для всех режимов
    
    def _init_postgresql(self):
        """Инициализация PostgreSQL менеджера"""
        try:
            # Получаем конфигурацию PostgreSQL из .env или config
            db_config = self.config.get('database', {})
            
            # Если нет конфигурации в файле, пытаемся из переменных окружения
            if not db_config.get('host'):
                import os
                db_config = {
                    'host': os.getenv('DB_HOST'),
                    'port': int(os.getenv('DB_PORT', 25060)),
                    'name': os.getenv('DB_NAME'),
                    'user': os.getenv('DB_USER'),
                    'password': os.getenv('DB_PASSWORD'),
                    'batch_size': self.config.get('storage', {}).get('batch_size', 100),
                    'flush_interval': self.config.get('storage', {}).get('flush_interval', 5),
                    'pool_size': self.config.get('postgresql', {}).get('pool_size', 20)
                }
            
            self.postgres_manager = PostgreSQLManager(db_config)
            self.logger.info("🗄️ PostgreSQL менеджер инициализирован")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации PostgreSQL: {e}")
            self.logger.info("🔄 Переключение на CSV режим")
            self.storage_type = 'csv'
            self._init_csv_storage()
    
    async def initialize(self):
        """Асинхронная инициализация менеджера"""
        if self.postgres_manager:
            try:
                await self.postgres_manager.initialize()
                self.logger.info("✅ PostgreSQL подключение установлено")
            except Exception as e:
                self.logger.error(f"❌ Ошибка подключения PostgreSQL: {e}")
                self.storage_type = 'csv'
                self._init_csv_storage()
    
    def _init_csv_storage(self):
        """Инициализация CSV хранения"""
        # Создание директории
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"📁 CSV хранение инициализировано: {self.output_dir}")
        
        # Статистика
        self.records_written = 0
        self.files_created = 0
        
        # CSV заголовки
        self.csv_headers = [
            'exchange', 'symbol', 'timestamp', 'local_timestamp',
            'ask_amount', 'ask_price', 'bid_price', 'bid_amount'
        ]
        
    async def save_record(self, record: Dict[str, Any]) -> None:
        """
        Сохранение записи orderbook.
        
        Args:
            record: Запись для сохранения
        """
        try:
            if self.storage_type == 'postgresql' and self.postgres_manager:
                await self._save_to_postgresql(record)
            else:
                await self._save_to_csv(record)
                
        except Exception as e:
            self.logger.error(f"Error saving record: {e}")
    
    async def _save_to_postgresql(self, record: Dict[str, Any]) -> None:
        """
        Сохранение записи в PostgreSQL.
        
        Args:
            record: Запись для сохранения
        """
        if not self.postgres_manager:
            self.logger.error("PostgreSQL manager не инициализирован")
            await self._save_to_csv(record)
            return
            
        try:
            # Получение символа из записи
            symbol = record.get('symbol', 'UNKNOWN')
            
            # Преобразование в OrderBookData
            orderbook_data = create_orderbook_data(symbol, record)
            
            # Сохранение через PostgreSQL менеджер
            success = await self.postgres_manager.store_orderbook(orderbook_data)
            
            if success:
                self.records_written += 1
            
        except Exception as e:
            self.logger.error(f"Error saving to PostgreSQL: {e}")
            # Fallback на CSV если PostgreSQL недоступен
            self.logger.warning("📝 Переключение на CSV режим из-за ошибки PostgreSQL")
            self.storage_type = 'csv'
            await self._save_to_csv(record)
    
    async def _save_to_csv(self, record: Dict[str, Any]) -> None:
        """
        Сохранение записи в CSV файл.
        
        Args:
            record: Запись для сохранения
        """
        # Проверка необходимости ротации файла
        await self._check_file_rotation(record)
        
        # Добавление в буфер
        self.buffer.append(record)
        
        # Запись буфера при достижении лимита
        if len(self.buffer) >= self.buffer_size:
            await self._flush_buffer()
            
    async def _check_file_rotation(self, record: Dict[str, Any]) -> None:
        """
        Проверка необходимости создания нового файла.
        
        Args:
            record: Текущая запись
        """
        current_time = datetime.now()
        
        # Создание нового файла если:
        # 1. Файл еще не создан
        # 2. Прошло время ротации
        if (self.current_file is None or 
            (self.file_rotation_time and current_time >= self.file_rotation_time)):
            
            await self._close_current_file()
            await self._create_new_file(record)
            
    async def _create_new_file(self, record: Dict[str, Any]) -> None:
        """
        Создание нового файла для записи.
        
        Args:
            record: Текущая запись (для получения символа)
        """
        try:
            current_time = datetime.now()
            symbol = record.get('symbol', 'UNKNOWN')
            
            # Генерация имени файла
            timestamp_str = current_time.strftime('%Y%m%d_%H%M%S')
            filename = f"{symbol}_orderbook_{timestamp_str}.csv"
            
            if self.compress:
                filename += ".gz"
            
            filepath = self.output_dir / filename
            
            # Открытие файла
            if self.compress:
                self.current_file = gzip.open(filepath, 'wt', encoding='utf-8')
            else:
                self.current_file = open(filepath, 'w', encoding='utf-8')
            
            # Создание CSV writer
            self.current_writer = csv.DictWriter(
                self.current_file, 
                fieldnames=self.csv_headers
            )
            
            # Запись заголовков
            self.current_writer.writeheader()
            
            # Установка времени следующей ротации
            self.file_rotation_time = current_time + timedelta(hours=self.rotation_hours)
            
            self.files_created += 1
            self.logger.info(f"📝 Создан новый файл: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error creating new file: {e}")
            
    async def _flush_buffer(self) -> None:
        """
        Запись буфера на диск.
        """
        if not self.buffer or not self.current_writer or not self.current_file:
            return
            
        try:
            # Запись всех записей из буфера
            for record in self.buffer:
                self.current_writer.writerow(record)
                
            # Принудительная запись на диск
            self.current_file.flush()
            
            self.records_written += len(self.buffer)
            self.buffer.clear()
            
        except Exception as e:
            self.logger.error(f"Error flushing buffer: {e}")
            
    async def _close_current_file(self) -> None:
        """
        Закрытие текущего файла.
        """
        try:
            # Запись оставшихся данных из буфера
            await self._flush_buffer()
            
            if self.current_file:
                self.current_file.close()
                self.current_file = None
                self.current_writer = None
                
        except Exception as e:
            self.logger.error(f"Error closing file: {e}")
            
    async def shutdown(self) -> None:
        """
        Корректное завершение работы менеджера.
        """
        self.logger.info("Shutting down data manager")
        
        # Завершение работы PostgreSQL
        if self.postgres_manager:
            await self.postgres_manager.close()
        
        # Завершение работы CSV
        await self._close_current_file()
        
        self.logger.info(f"📊 Статистика: {self.records_written} записей, {getattr(self, 'files_created', 0)} файлов")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики работы менеджера.
        
        Returns:
            Словарь со статистикой
        """
        stats = {
            'storage_type': self.storage_type,
            'records_written': self.records_written,
            'files_created': getattr(self, 'files_created', 0),
            'buffer_size': len(self.buffer)
        }
        
        # Добавление статистики PostgreSQL
        if self.postgres_manager:
            try:
                # Получаем статистику синхронно из внутреннего состояния
                pg_stats = {
                    'successful_inserts': getattr(self.postgres_manager, '_stats', {}).get('successful_inserts', 0),
                    'failed_inserts': getattr(self.postgres_manager, '_stats', {}).get('failed_inserts', 0),
                    'batch_size': getattr(self.postgres_manager, '_batch_size', 0),
                    'buffer_length': len(getattr(self.postgres_manager, '_batch_buffer', []))
                }
                stats['postgresql'] = pg_stats
            except Exception:
                pass
        
        return stats