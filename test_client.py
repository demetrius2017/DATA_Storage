#!/usr/bin/env python3
"""Тестирование клиента удаленного коллектора"""

import sys
import json
from datetime import datetime

def test_imports():
    """Тестирование импортов"""
    print("🧪 Тестирование импортов...")
    
    try:
        import requests
        print("  ✅ requests")
    except ImportError as e:
        print(f"  ❌ requests: {e}")
        return False
    
    try:
        import websockets
        print("  ✅ websockets")
    except ImportError as e:
        print(f"  ❌ websockets: {e}")
        return False
    
    try:
        import asyncio
        print("  ✅ asyncio")
    except ImportError as e:
        print(f"  ❌ asyncio: {e}")
        return False
    
    try:
        from dataclasses import dataclass
        print("  ✅ dataclasses")
    except ImportError as e:
        print(f"  ❌ dataclasses: {e}")
        return False
    
    return True

def test_client_functionality():
    """Тестирование функциональности клиента"""
    print("\n🔧 Тестирование функциональности клиента...")
    
    try:
        # Импортируем наш клиент
        sys.path.append('scripts')
        from remote_collector_client import RemoteCollectorClient, CollectorStatus
        
        # Создаем тестовый клиент
        client = RemoteCollectorClient("http://localhost:8000")
        print("  ✅ Клиент создан успешно")
        
        # Создаем тестовый статус
        status = CollectorStatus(
            is_running=True,
            symbols=["BTCUSDT", "ETHUSDT"],
            start_time=datetime.now().isoformat(),
            uptime_seconds=3600,
            error=None
        )
        print("  ✅ Структуры данных работают")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False

def main():
    """Главная функция тестирования"""
    print("🚀 ТЕСТИРОВАНИЕ КЛИЕНТА УДАЛЕННОГО КОЛЛЕКТОРА")
    print("=" * 50)
    
    success = True
    
    # Тестируем импорты
    if not test_imports():
        success = False
    
    # Тестируем функциональность
    if not test_client_functionality():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("✅ Все тесты прошли успешно!")
        print("\n💡 Следующие шаги:")
        print("1. Скопируйте .env.example в .env и настройте параметры")
        print("2. Запустите развертывание: ./scripts/deploy_remote_collector.sh SERVER_IP")
        print("3. Используйте клиент: python scripts/remote_collector_client.py --help")
    else:
        print("❌ Некоторые тесты не прошли. Проверьте установку зависимостей.")
        sys.exit(1)

if __name__ == "__main__":
    main()
