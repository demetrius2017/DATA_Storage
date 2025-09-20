"""
WebSocket клиент для подключения к Binance API и получения данных orderbook.
"""

import asyncio
import json
import logging
import websockets
from typing import Optional, Callable, Dict, Any
from datetime import datetime


class BinanceCollector:
    """
    WebSocket клиент для сбора данных orderbook с Binance.
    
    Осуществляет подключение к Binance WebSocket API и получает
    обновления книги заказов в реальном времени.
    """
    
    def __init__(self, symbol: str, processor, config: Dict[str, Any]):
        """
        Инициализация коллектора.
        
        Args:
            symbol: Торговая пара (например, BTCUSDT)
            processor: Обработчик данных OrderBookProcessor
            config: Конфигурация системы
        """
        self.symbol = symbol.upper()
        self.processor = processor
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # API ключи и настройки
        api_creds = config.get('api_credentials', {})
        self.api_key = api_creds.get('api_key', '')
        self.ws_url = api_creds.get('ws_url', 'wss://fstream.binance.com/ws/')
        
        # WebSocket настройки
        ws_config = config.get('websocket', {})
        self.reconnect_interval = ws_config.get('reconnect_interval', 5)
        self.ping_interval = ws_config.get('ping_interval', 20)
        self.max_reconnects = ws_config.get('max_reconnects', 100)
        
        # Статистика
        self.reconnect_count = 0
        self.message_count = 0
        self.start_time = None
        self.is_running = False
        
        # Проверка API ключа
        if not self.api_key:
            self.logger.warning("No API key provided - using public streams only")
        else:
            self.logger.info(f"API key loaded: {self.api_key[:8]}...{self.api_key[-4:]}")
        
    async def start(self) -> None:
        """
        Запуск сбора данных с автоматическим переподключением.
        """
        self.start_time = datetime.now()
        self.is_running = True
        
        self.logger.info(f"Starting data collection for {self.symbol}")
        
        while self.is_running and self.reconnect_count < self.max_reconnects:
            try:
                await self._connect()
            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                
                if self.is_running:
                    self.reconnect_count += 1
                    self.logger.info(
                        f"Reconnecting in {self.reconnect_interval}s "
                        f"(attempt {self.reconnect_count}/{self.max_reconnects})"
                    )
                    await asyncio.sleep(self.reconnect_interval)
                    
        if self.reconnect_count >= self.max_reconnects:
            self.logger.error("Max reconnects reached, shutting down")
            
    async def _connect(self) -> None:
        """
        Установка WebSocket соединения и обработка сообщений.
        """
        # URL для подписки на обновления orderbook
        stream_name = f"{self.symbol.lower()}@depth"
        url = f"{self.ws_url}{stream_name}"
        
        self.logger.info(f"Connecting to {url}")
        
        async with websockets.connect(
            url,
            ping_interval=self.ping_interval,
            ping_timeout=10,
            close_timeout=10
        ) as websocket:
            self.logger.info(f"Connected to Binance WebSocket for {self.symbol}")
            self.reconnect_count = 0
            
            async for message in websocket:
                if not self.is_running:
                    break
                    
                try:
                    await self._process_message(message)
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")
                    
    async def _process_message(self, message: str) -> None:
        """
        Обработка входящего сообщения с данными orderbook.
        
        Args:
            message: JSON строка с данными от Binance
        """
        try:
            data = json.loads(message)
            
            # Проверка типа сообщения
            if 'e' not in data or data['e'] != 'depthUpdate':
                return
                
            self.message_count += 1
            
            # Добавление метки времени получения
            data['local_timestamp'] = datetime.now().timestamp() * 1000000  # микросекунды
            
            # Передача данных процессору
            await self.processor.process_orderbook_update(data)
            
            if self.message_count % 1000 == 0:
                self.logger.info(f"Processed {self.message_count} messages")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error in message processing: {e}")
            
    def stop(self) -> None:
        """
        Остановка сбора данных.
        """
        self.is_running = False
        self.logger.info("Stopping data collection")
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики работы коллектора.
        
        Returns:
            Словарь со статистикой
        """
        runtime = None
        if self.start_time:
            runtime = (datetime.now() - self.start_time).total_seconds()
            
        return {
            'symbol': self.symbol,
            'is_running': self.is_running,
            'message_count': self.message_count,
            'reconnect_count': self.reconnect_count,
            'runtime_seconds': runtime,
            'messages_per_second': self.message_count / runtime if runtime else 0
        }