"""
Мониторинг состояния системы сбора данных.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any


class HealthMonitor:
    """
    Монитор состояния системы сбора данных.
    
    Отслеживает работу коллектора, процессора и менеджера данных,
    предоставляет метрики через веб-интерфейс.
    """
    
    def __init__(self, collector, config: Dict[str, Any]):
        """
        Инициализация монитора.
        
        Args:
            collector: Экземпляр BinanceCollector
            config: Конфигурация системы
        """
        self.collector = collector
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Настройки мониторинга
        monitor_config = config.get('monitoring', {})
        self.web_port = monitor_config.get('web_port', 8080)
        self.metrics_interval = monitor_config.get('metrics_interval', 60)
        self.health_check_interval = monitor_config.get('health_check_interval', 30)
        
        # Состояние системы
        self.system_health = {
            'status': 'starting',
            'last_check': None,
            'errors': [],
            'warnings': []
        }
        
        self.is_running = False
        
    async def start(self) -> None:
        """
        Запуск мониторинга.
        """
        self.is_running = True
        self.logger.info(f"Starting health monitor on port {self.web_port}")
        
        # Запуск фоновых задач
        tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._metrics_collection_loop()),
            asyncio.create_task(self._web_server())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            self.logger.error(f"Monitor error: {e}")
        finally:
            self.is_running = False
            
    async def _health_check_loop(self) -> None:
        """
        Периодическая проверка состояния системы.
        """
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)
                
    async def _metrics_collection_loop(self) -> None:
        """
        Периодический сбор метрик.
        """
        while self.is_running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.metrics_interval)
            except Exception as e:
                self.logger.error(f"Metrics collection error: {e}")
                await asyncio.sleep(5)
                
    async def _perform_health_check(self) -> None:
        """
        Выполнение проверки состояния.
        """
        try:
            # Проверка коллектора
            collector_stats = self.collector.get_stats()
            
            # Обновление статуса
            if collector_stats['is_running']:
                if collector_stats['message_count'] > 0:
                    self.system_health['status'] = 'healthy'
                else:
                    self.system_health['status'] = 'waiting'
            else:
                self.system_health['status'] = 'stopped'
                
            self.system_health['last_check'] = datetime.now().isoformat()
            
            # Проверка на предупреждения
            if collector_stats['reconnect_count'] > 5:
                warning = f"High reconnect count: {collector_stats['reconnect_count']}"
                if warning not in self.system_health['warnings']:
                    self.system_health['warnings'].append(warning)
                    
        except Exception as e:
            error_msg = f"Health check failed: {e}"
            self.system_health['status'] = 'error'
            self.system_health['errors'].append(error_msg)
            self.logger.error(error_msg)
            
    async def _collect_metrics(self) -> None:
        """
        Сбор метрик производительности.
        """
        try:
            # Получение статистики от компонентов
            collector_stats = self.collector.get_stats()
            
            # Логирование метрик
            self.logger.info(f"Metrics - Messages: {collector_stats['message_count']}, "
                           f"MPS: {collector_stats['messages_per_second']:.2f}, "
                           f"Reconnects: {collector_stats['reconnect_count']}")
                           
        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
            
    async def _web_server(self) -> None:
        """
        Простой веб-сервер для отображения статуса.
        """
        try:
            # Здесь должен быть код веб-сервера
            # Для простоты пока только логирование
            self.logger.info(f"Web server would run on port {self.web_port}")
            
            # Заглушка - просто ждем
            while self.is_running:
                await asyncio.sleep(10)
                
        except Exception as e:
            self.logger.error(f"Web server error: {e}")
            
    def get_system_status(self) -> Dict[str, Any]:
        """
        Получение текущего статуса системы.
        
        Returns:
            Словарь с информацией о состоянии
        """
        try:
            # Статистика коллектора
            collector_stats = self.collector.get_stats()
            
            return {
                'system_health': self.system_health,
                'collector_stats': collector_stats,
                'monitor_config': {
                    'web_port': self.web_port,
                    'metrics_interval': self.metrics_interval,
                    'health_check_interval': self.health_check_interval
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
    def stop(self) -> None:
        """
        Остановка мониторинга.
        """
        self.is_running = False
        self.logger.info("Stopping health monitor")