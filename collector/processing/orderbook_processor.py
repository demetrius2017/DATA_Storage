"""
Обработчик данных orderbook от Binance.

Преобразует сырые данные WebSocket в структурированный формат
и передает их системе хранения.
"""

import asyncio
import logging
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime


class OrderBookProcessor:
    """
    Обработчик данных книги заказов.
    
    Принимает сырые данные от WebSocket, валидирует их,
    преобразует в стандартный формат и передает на сохранение.
    """
    
    def __init__(self, data_manager):
        """
        Инициализация процессора.
        
        Args:
            data_manager: Менеджер данных для сохранения
        """
        self.data_manager = data_manager
        self.logger = logging.getLogger(__name__)
        
        # Статистика
        self.processed_count = 0
        self.error_count = 0
        self.last_update_time = None
        
    async def process_orderbook_update(self, data: Dict[str, Any]) -> None:
        """
        Обработка обновления orderbook.
        
        Args:
            data: Сырые данные от Binance WebSocket
        """
        try:
            # Валидация данных
            if not self._validate_data(data):
                self.error_count += 1
                return
                
            # Извлечение лучших bid/ask
            best_bid, best_ask = self._extract_best_prices(data)
            
            # Для depth updates может быть только одна сторона книги заказов
            if not best_bid and not best_ask:
                # Детальное логирование для анализа проблемных сообщений
                bids_count = len(data.get('b', []))
                asks_count = len(data.get('a', []))
                self.logger.debug(f"No valid bid/ask data - bids: {bids_count}, asks: {asks_count}, "
                                f"first_bid: {data.get('b', [[]])[0] if data.get('b') else 'None'}, "
                                f"first_ask: {data.get('a', [[]])[0] if data.get('a') else 'None'}")
                return
                
            # Если доступна прямая запись сырых данных в PostgreSQL — используем её
            if getattr(self.data_manager, 'storage_type', 'csv') == 'postgresql' and hasattr(self.data_manager, 'save_orderbook_raw'):
                await self.data_manager.save_orderbook_raw(data)
            else:
                # Формирование упрощенной записи для CSV
                record = self._create_record(data, best_bid, best_ask)
                await self.data_manager.save_record(record)
            
            self.processed_count += 1
            self.last_update_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Error processing orderbook update: {e}")
            self.error_count += 1
            
    def _validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Валидация входящих данных.
        
        Args:
            data: Данные для валидации
            
        Returns:
            True если данные валидны
        """
        required_fields = ['e', 'E', 's', 'b', 'a']
        
        for field in required_fields:
            if field not in data:
                self.logger.warning(f"Missing required field: {field}")
                return False
                
        # Проверка типа события
        if data['e'] != 'depthUpdate':
            return False
            
        # Проверка наличия bid/ask данных
        if not data['b'] and not data['a']:
            return False
            
        return True
        
    def _extract_best_prices(self, data: Dict[str, Any]) -> Tuple[Optional[List[float]], Optional[List[float]]]:
        """
        Извлечение лучших цен bid/ask.
        
        Args:
            data: Данные orderbook
            
        Returns:
            Кортеж (best_bid, best_ask)
        """
        bids = data.get('b', [])
        asks = data.get('a', [])
        
        best_bid = None
        best_ask = None
        
        # Лучший bid (наивысшая цена покупки)
        if bids:
            try:
                # Bids отсортированы по убыванию цены
                best_bid = [float(bids[0][0]), float(bids[0][1])]  # [price, quantity]
            except (IndexError, ValueError) as e:
                self.logger.warning(f"Invalid bid data: {e}")
                
        # Лучший ask (наименьшая цена продажи)  
        if asks:
            try:
                # Asks отсортированы по возрастанию цены
                best_ask = [float(asks[0][0]), float(asks[0][1])]  # [price, quantity]
            except (IndexError, ValueError) as e:
                self.logger.warning(f"Invalid ask data: {e}")
                
        return best_bid, best_ask
        
    def _create_record(self, data: Dict[str, Any], best_bid: Optional[List[float]], best_ask: Optional[List[float]]) -> Dict[str, Any]:
        """
        Создание стандартизированной записи.
        
        Args:
            data: Исходные данные
            best_bid: Лучшая цена покупки [price, quantity]
            best_ask: Лучшая цена продажи [price, quantity]
            
        Returns:
            Стандартизированная запись
        """
        return {
            'exchange': 'binance-futures',
            'symbol': data['s'],
            'timestamp': data['E'] * 1000,  # конвертация в микросекунды
            'local_timestamp': int(data.get('local_timestamp', datetime.now().timestamp() * 1000000)),
            'ask_amount': best_ask[1] if best_ask else None,
            'ask_price': best_ask[0] if best_ask else None,
            'bid_price': best_bid[0] if best_bid else None,
            'bid_amount': best_bid[1] if best_bid else None
        }
        
    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики обработки.
        
        Returns:
            Словарь со статистикой
        """
        return {
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
            'error_rate': self.error_count / max(1, self.processed_count + self.error_count)
        }