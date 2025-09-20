"""
Тесты для системы сбора данных Binance OrderBook.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Импорты из нашей системы (после создания __init__.py файлов)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from collector.processing.orderbook_processor import OrderBookProcessor
from collector.storage.data_manager import DataManager
from collector.config.settings import load_config


class TestOrderBookProcessor:
    """Тесты для обработчика orderbook данных."""
    
    def setup_method(self):
        """Настройка для каждого теста."""
        self.mock_data_manager = Mock()
        self.mock_data_manager.save_record = AsyncMock()
        self.processor = OrderBookProcessor(self.mock_data_manager)
        
    def test_validate_data_valid(self):
        """Тест валидации корректных данных."""
        valid_data = {
            'e': 'depthUpdate',
            'E': 1699999999999,
            's': 'BTCUSDT',
            'b': [['43250.50', '0.75']],
            'a': [['43251.00', '1.25']]
        }
        
        assert self.processor._validate_data(valid_data) is True
        
    def test_validate_data_invalid(self):
        """Тест валидации некорректных данных."""
        invalid_data = {
            'e': 'wrongType',
            'E': 1699999999999,
            's': 'BTCUSDT'
        }
        
        assert self.processor._validate_data(invalid_data) is False
        
    def test_extract_best_prices(self):
        """Тест извлечения лучших цен."""
        data = {
            'b': [['43250.50', '0.75'], ['43250.00', '1.00']],
            'a': [['43251.00', '1.25'], ['43251.50', '0.50']]
        }
        
        best_bid, best_ask = self.processor._extract_best_prices(data)
        
        assert best_bid == [43250.50, 0.75]
        assert best_ask == [43251.00, 1.25]
        
    def test_create_record(self):
        """Тест создания записи."""
        data = {
            's': 'BTCUSDT',
            'E': 1699999999,
            'local_timestamp': 1699999999000000
        }
        
        best_bid = [43250.50, 0.75]
        best_ask = [43251.00, 1.25]
        
        record = self.processor._create_record(data, best_bid, best_ask)
        
        expected = {
            'exchange': 'binance-futures',
            'symbol': 'BTCUSDT',
            'timestamp': 1699999999000,
            'local_timestamp': 1699999999000000,
            'ask_amount': 1.25,
            'ask_price': 43251.00,
            'bid_price': 43250.50,
            'bid_amount': 0.75
        }
        
        assert record == expected
        
    @pytest.mark.asyncio
    async def test_process_orderbook_update(self):
        """Тест полной обработки обновления orderbook."""
        data = {
            'e': 'depthUpdate',
            'E': 1699999999,
            's': 'BTCUSDT',
            'b': [['43250.50', '0.75']],
            'a': [['43251.00', '1.25']],
            'local_timestamp': 1699999999000000
        }
        
        await self.processor.process_orderbook_update(data)
        
        # Проверяем, что метод сохранения был вызван
        self.mock_data_manager.save_record.assert_called_once()
        
        # Проверяем статистику
        stats = self.processor.get_stats()
        assert stats['processed_count'] == 1
        assert stats['error_count'] == 0


class TestDataManager:
    """Тесты для менеджера данных."""
    
    def setup_method(self):
        """Настройка для каждого теста."""
        self.test_dir = "/tmp/test_data_collector"
        self.config = {
            'storage': {
                'rotation_hours': 1
            }
        }
        self.data_manager = DataManager(
            output_dir=self.test_dir,
            compress=False,  # Без сжатия для простоты тестов
            config=self.config
        )
        
    def teardown_method(self):
        """Очистка после теста."""
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            
    @pytest.mark.asyncio
    async def test_save_record(self):
        """Тест сохранения записи."""
        record = {
            'exchange': 'binance-futures',
            'symbol': 'BTCUSDT',
            'timestamp': 1699999999000,
            'local_timestamp': 1699999999000000,
            'ask_amount': 1.25,
            'ask_price': 43251.00,
            'bid_price': 43250.50,
            'bid_amount': 0.75
        }
        
        await self.data_manager.save_record(record)
        
        # Проверяем статистику
        stats = self.data_manager.get_stats()
        assert stats['files_created'] >= 1
        
    def test_get_stats(self):
        """Тест получения статистики."""
        stats = self.data_manager.get_stats()
        
        expected_keys = [
            'records_written', 'files_created', 'buffer_size',
            'output_directory', 'compression_enabled', 'rotation_hours'
        ]
        
        for key in expected_keys:
            assert key in stats


class TestConfig:
    """Тесты для конфигурации."""
    
    def test_load_default_config(self):
        """Тест загрузки конфигурации по умолчанию."""
        config = load_config()
        
        assert 'symbols' in config
        assert 'websocket' in config
        assert 'storage' in config
        assert 'monitoring' in config
        
    def test_load_config_from_file(self, tmp_path):
        """Тест загрузки конфигурации из файла."""
        config_file = tmp_path / "test_config.json"
        test_config = {
            "symbols": ["TESTUSDT"],
            "custom_setting": "test_value"
        }
        
        config_file.write_text(json.dumps(test_config))
        
        config = load_config(str(config_file))
        
        assert config['symbols'] == ["TESTUSDT"]
        assert config['custom_setting'] == "test_value"
        # Проверяем, что значения по умолчанию тоже присутствуют
        assert 'websocket' in config


class TestIntegration:
    """Интеграционные тесты."""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_simulation(self):
        """Тест полного pipeline обработки данных."""
        # Создание компонентов
        test_dir = "/tmp/test_integration"
        data_manager = DataManager(output_dir=test_dir, compress=False)
        processor = OrderBookProcessor(data_manager)
        
        try:
            # Симуляция данных от WebSocket
            mock_websocket_data = {
                'e': 'depthUpdate',
                'E': 1699999999,
                's': 'BTCUSDT',
                'b': [['43250.50', '0.75']],
                'a': [['43251.00', '1.25']],
                'local_timestamp': 1699999999000000
            }
            
            # Обработка данных
            await processor.process_orderbook_update(mock_websocket_data)
            
            # Принудительная запись буфера
            await data_manager._flush_buffer()
            
            # Проверка результатов
            processor_stats = processor.get_stats()
            manager_stats = data_manager.get_stats()
            
            assert processor_stats['processed_count'] == 1
            assert processor_stats['error_count'] == 0
            assert manager_stats['files_created'] >= 1
            
        finally:
            # Очистка
            await data_manager.shutdown()
            import shutil
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)


if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])