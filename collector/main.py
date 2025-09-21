#!/usr/bin/env python3
"""
Главный модуль системы сбора данных Binance OrderBook.

Основная точка входа для запуска коллектора данных с биржи Binance.
Осуществляет подключение к WebSocket API, обработку данных и сохранение.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from collector.websocket.binance_collector import BinanceCollector
from collector.processing.orderbook_processor import OrderBookProcessor
from collector.storage.data_manager import DataManager
from collector.monitor.health_checker import HealthMonitor
from collector.config.settings import load_config


def setup_logging(verbose: bool = False):
    """Настройка системы логирования."""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Создание директории для логов
    logs_dir = Path("collector/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(logs_dir / 'collector.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


async def main():
    """Основная функция запуска коллектора."""
    parser = argparse.ArgumentParser(description='Binance OrderBook Data Collector')
    parser.add_argument('--symbol', help='Trading symbol (e.g., BTCUSDT)')
    parser.add_argument('--symbols', nargs='+', help='Multiple trading symbols (e.g., BTCUSDT ETHUSDT SOLUSDT)')
    parser.add_argument('--output-dir', required=True, help='Output directory for data')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--compress', action='store_true', help='Enable compression')
    parser.add_argument('--monitor', action='store_true', help='Enable web monitoring')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    parser.add_argument('--test-mode', action='store_true', help='Test mode (limited time)')
    parser.add_argument('--production', action='store_true', help='Use production API (default: testnet)')
    
    args = parser.parse_args()
    
    # Валидация аргументов: должен быть указан либо --symbol, либо --symbols
    if not args.symbol and not args.symbols:
        parser.error("Either --symbol or --symbols must be specified")
    if args.symbol and args.symbols:
        parser.error("Cannot use both --symbol and --symbols")
        
    # Определение списка символов
    symbols = [args.symbol] if args.symbol else args.symbols
    
    # Настройка логирования
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info(f"Starting Binance OrderBook Collector for symbols: {', '.join(symbols)}")
    
    try:
        # Загрузка конфигурации
        config = load_config(args.config)
        
        # Переопределение режима API если указан флаг
        if args.production:
            config['api']['use_testnet'] = False
            # Обновляем api_credentials после смены режима, иначе останется testnet ws_url
            from collector.config.settings import get_api_credentials
            config['api_credentials'] = get_api_credentials(use_testnet=False)
            logger.info("⚠️  PRODUCTION MODE ENABLED - Using real Binance API")
        
        # Создание компонентов для каждого символа
        collectors = []
        data_managers = []
        
        for symbol in symbols:
            # Отдельный data_manager для каждого символа
            data_manager = DataManager(
                output_dir=args.output_dir,
                compress=args.compress,
                config=config
            )
            data_managers.append(data_manager)
            
            # Отдельный processor для каждого символа
            processor = OrderBookProcessor(data_manager=data_manager)
            
            # Отдельный collector для каждого символа
            collector = BinanceCollector(
                symbol=symbol,
                processor=processor,
                config=config
            )
            collectors.append(collector)
        
        # Инициализируем хранилища (PostgreSQL/CSV) до старта сбора
        try:
            await asyncio.gather(*(dm.initialize() for dm in data_managers))
        except Exception as e:
            logger.error(f"Storage initialization failed: {e}")

        # Мониторинг
        if args.monitor:
            health_monitor = HealthMonitor(collectors[0], config)  # Используем первый коллектор для мониторинга
            asyncio.create_task(health_monitor.start())
        
        # Запуск сбора данных для всех символов параллельно
        tasks = [collector.start() for collector in collectors]
        
        if args.test_mode:
            logger.info("Running in test mode (60 seconds)")
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
            except asyncio.TimeoutError:
                logger.info("Test mode completed")
        else:
            await asyncio.gather(*tasks)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        # Корректное завершение всех компонентов
        if 'data_managers' in locals():
            for data_manager in data_managers:
                await data_manager.shutdown()
        if 'collectors' in locals():
            for collector in collectors:
                collector.stop()


if __name__ == "__main__":
    asyncio.run(main())