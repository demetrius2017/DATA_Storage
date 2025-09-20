#!/usr/bin/env python3
"""
Клиент для управления удаленным коллектором данных
Обеспечивает локальное управление, мониторинг и валидацию ТЗ
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import argparse
import requests
import websockets
from dataclasses import dataclass, asdict


@dataclass
class CollectorStatus:
    """Статус удаленного коллектора"""
    is_running: bool
    symbols: List[str]
    start_time: Optional[str]
    uptime_seconds: Optional[int]
    error: Optional[str]
    

@dataclass
class DatabaseStats:
    """Статистика БД"""
    total_records: int
    records_last_hour: int
    records_last_day: int
    unique_symbols: List[str]
    last_update: str
    avg_updates_per_minute: float


@dataclass
class MonitoringData:
    """Данные мониторинга в реальном времени"""
    timestamp: str
    collector_status: CollectorStatus
    database_stats: DatabaseStats
    system_metrics: Dict[str, Any]


class RemoteCollectorClient:
    """Клиент для управления удаленным коллектором"""
    
    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url.rstrip('/')
        self.ws_url = server_url.replace('http://', 'ws://').replace('https://', 'wss://') + "/ws/monitoring"
        
    def get_status(self) -> Optional[CollectorStatus]:
        """Получить текущий статус коллектора"""
        try:
            response = requests.get(f"{self.server_url}/api/collector/status", timeout=10)
            response.raise_for_status()
            data = response.json()
            return CollectorStatus(**data)
        except Exception as e:
            print(f"❌ Ошибка получения статуса: {e}")
            return None
    
    def start_collector(self, symbols: List[str], database_url: str, log_level: str = "INFO") -> bool:
        """Запустить коллектор с указанными символами"""
        try:
            config = {
                "symbols": symbols,
                "database_url": database_url,
                "log_level": log_level
            }
            response = requests.post(
                f"{self.server_url}/api/collector/start",
                json=config,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                print(f"✅ Коллектор запущен с символами: {symbols}")
                return True
            else:
                print(f"❌ Ошибка запуска: {result.get('error', 'Неизвестная ошибка')}")
                return False
        except Exception as e:
            print(f"❌ Ошибка запуска коллектора: {e}")
            return False
    
    def stop_collector(self) -> bool:
        """Остановить коллектор"""
        try:
            response = requests.post(f"{self.server_url}/api/collector/stop", timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                print("✅ Коллектор остановлен")
                return True
            else:
                print(f"❌ Ошибка остановки: {result.get('error', 'Неизвестная ошибка')}")
                return False
        except Exception as e:
            print(f"❌ Ошибка остановки коллектора: {e}")
            return False
    
    def restart_collector(self) -> bool:
        """Перезапустить коллектор"""
        try:
            response = requests.post(f"{self.server_url}/api/collector/restart", timeout=60)
            response.raise_for_status()
            result = response.json()
            if result.get("success"):
                print("✅ Коллектор перезапущен")
                return True
            else:
                print(f"❌ Ошибка перезапуска: {result.get('error', 'Неизвестная ошибка')}")
                return False
        except Exception as e:
            print(f"❌ Ошибка перезапуска коллектора: {e}")
            return False
    
    def get_database_stats(self) -> Optional[DatabaseStats]:
        """Получить статистику БД"""
        try:
            response = requests.get(f"{self.server_url}/api/database/stats", timeout=10)
            response.raise_for_status()
            data = response.json()
            return DatabaseStats(**data)
        except Exception as e:
            print(f"❌ Ошибка получения статистики БД: {e}")
            return None
    
    def validate_data_compliance(self) -> Optional[Dict[str, Any]]:
        """Проверить соответствие данных ТЗ"""
        try:
            response = requests.get(f"{self.server_url}/api/validation/compliance", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Ошибка валидации ТЗ: {e}")
            return None
    
    async def monitor_realtime(self, duration_minutes: int = 60):
        """Мониторинг в реальном времени через WebSocket"""
        print(f"🔄 Начинаем мониторинг в реальном времени ({duration_minutes} мин)")
        print("=" * 60)
        
        end_time = time.time() + (duration_minutes * 60)
        
        try:
            async with websockets.connect(self.ws_url) as websocket:
                while time.time() < end_time:
                    try:
                        # Получаем данные от WebSocket
                        data = await asyncio.wait_for(websocket.recv(), timeout=10)
                        monitoring_data = json.loads(data)
                        
                        # Выводим обновленную информацию
                        self._display_monitoring_data(monitoring_data)
                        
                    except asyncio.TimeoutError:
                        print("⚠️ Таймаут получения данных мониторинга")
                    except websockets.exceptions.ConnectionClosed:
                        print("❌ WebSocket соединение закрыто")
                        break
                    except Exception as e:
                        print(f"❌ Ошибка мониторинга: {e}")
                        await asyncio.sleep(5)
                        
        except Exception as e:
            print(f"❌ Ошибка подключения к WebSocket: {e}")
    
    def _display_monitoring_data(self, data: Dict[str, Any]):
        """Отображение данных мониторинга"""
        timestamp = data.get('timestamp', datetime.now().isoformat())
        collector = data.get('collector_status', {})
        database = data.get('database_stats', {})
        system = data.get('system_metrics', {})
        
        # Очищаем экран и выводим заголовок
        print("\033[2J\033[H")  # Clear screen
        print(f"🔄 МОНИТОРИНГ КОЛЛЕКТОРА [{timestamp}]")
        print("=" * 60)
        
        # Статус коллектора
        status_icon = "🟢" if collector.get('is_running') else "🔴"
        print(f"\n📊 КОЛЛЕКТОР: {status_icon}")
        print(f"   Статус: {'Запущен' if collector.get('is_running') else 'Остановлен'}")
        if collector.get('symbols'):
            print(f"   Символы: {', '.join(collector['symbols'])}")
        if collector.get('uptime_seconds'):
            uptime = timedelta(seconds=collector['uptime_seconds'])
            print(f"   Время работы: {uptime}")
        if collector.get('error'):
            print(f"   ⚠️ Ошибка: {collector['error']}")
        
        # Статистика БД
        print(f"\n🗄️ БАЗА ДАННЫХ:")
        print(f"   Всего записей: {database.get('total_records', 0):,}")
        print(f"   За последний час: {database.get('records_last_hour', 0):,}")
        print(f"   За последний день: {database.get('records_last_day', 0):,}")
        print(f"   Уникальных символов: {len(database.get('unique_symbols', []))}")
        print(f"   Обновлений/мин: {database.get('avg_updates_per_minute', 0):.1f}")
        if database.get('last_update'):
            print(f"   Последнее обновление: {database['last_update']}")
        
        # Системные метрики
        print(f"\n⚡ СИСТЕМА:")
        print(f"   CPU: {system.get('cpu_percent', 0):.1f}%")
        print(f"   Память: {system.get('memory_percent', 0):.1f}%")
        print(f"   Диск: {system.get('disk_percent', 0):.1f}%")
        print(f"   Сетевые соединения: {system.get('network_connections', 0)}")
        
        print("\n" + "=" * 60)
        print("Нажмите Ctrl+C для выхода")
    
    def show_summary(self):
        """Показать сводную информацию"""
        print("📋 СВОДКА ПО КОЛЛЕКТОРУ")
        print("=" * 50)
        
        # Статус коллектора
        status = self.get_status()
        if status:
            status_icon = "🟢" if status.is_running else "🔴"
            print(f"\n{status_icon} Коллектор: {'Запущен' if status.is_running else 'Остановлен'}")
            if status.symbols:
                print(f"   Символы: {', '.join(status.symbols)}")
            if status.uptime_seconds:
                uptime = timedelta(seconds=status.uptime_seconds)
                print(f"   Время работы: {uptime}")
        else:
            print("\n❌ Не удалось получить статус коллектора")
        
        # Статистика БД
        db_stats = self.get_database_stats()
        if db_stats:
            print(f"\n🗄️ База данных:")
            print(f"   Всего записей: {db_stats.total_records:,}")
            print(f"   За последний час: {db_stats.records_last_hour:,}")
            print(f"   За последний день: {db_stats.records_last_day:,}")
            print(f"   Уникальных символов: {len(db_stats.unique_symbols)}")
            print(f"   Символы: {', '.join(db_stats.unique_symbols[:10])}" + 
                  ("..." if len(db_stats.unique_symbols) > 10 else ""))
            print(f"   Обновлений/мин: {db_stats.avg_updates_per_minute:.1f}")
        else:
            print("\n❌ Не удалось получить статистику БД")
        
        # Валидация ТЗ
        compliance = self.validate_data_compliance()
        if compliance:
            print(f"\n✅ Валидация ТЗ:")
            validation_result = compliance.get('validation_result', {})
            if validation_result.get('is_valid'):
                print("   ✅ Данные соответствуют ТЗ")
            else:
                print("   ❌ Найдены нарушения ТЗ:")
                for error in validation_result.get('errors', []):
                    print(f"      - {error}")
        else:
            print("\n❌ Не удалось выполнить валидацию ТЗ")


def main():
    """Главная функция CLI"""
    parser = argparse.ArgumentParser(description="Клиент управления удаленным коллектором")
    parser.add_argument("--server", default="http://localhost:8000", 
                       help="URL сервера коллектора")
    
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")
    
    # Команда статуса
    subparsers.add_parser("status", help="Показать статус коллектора")
    
    # Команда запуска
    start_parser = subparsers.add_parser("start", help="Запустить коллектор")
    start_parser.add_argument("--symbols", nargs="+", required=True,
                             help="Список символов для сбора")
    start_parser.add_argument("--database-url", required=True,
                             help="URL базы данных")
    start_parser.add_argument("--log-level", default="INFO",
                             choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                             help="Уровень логирования")
    
    # Команда остановки
    subparsers.add_parser("stop", help="Остановить коллектор")
    
    # Команда перезапуска
    subparsers.add_parser("restart", help="Перезапустить коллектор")
    
    # Команда статистики БД
    subparsers.add_parser("db-stats", help="Показать статистику БД")
    
    # Команда валидации ТЗ
    subparsers.add_parser("validate", help="Проверить соответствие ТЗ")
    
    # Команда мониторинга
    monitor_parser = subparsers.add_parser("monitor", help="Мониторинг в реальном времени")
    monitor_parser.add_argument("--duration", type=int, default=60,
                               help="Длительность мониторинга в минутах")
    
    # Команда сводки
    subparsers.add_parser("summary", help="Показать сводную информацию")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    client = RemoteCollectorClient(args.server)
    
    try:
        if args.command == "status":
            status = client.get_status()
            if status:
                print(json.dumps(asdict(status), indent=2))
        
        elif args.command == "start":
            client.start_collector(args.symbols, args.database_url, args.log_level)
        
        elif args.command == "stop":
            client.stop_collector()
        
        elif args.command == "restart":
            client.restart_collector()
        
        elif args.command == "db-stats":
            stats = client.get_database_stats()
            if stats:
                print(json.dumps(asdict(stats), indent=2))
        
        elif args.command == "validate":
            result = client.validate_data_compliance()
            if result:
                print(json.dumps(result, indent=2))
        
        elif args.command == "monitor":
            asyncio.run(client.monitor_realtime(args.duration))
        
        elif args.command == "summary":
            client.show_summary()
            
    except KeyboardInterrupt:
        print("\n👋 Завершение работы...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()