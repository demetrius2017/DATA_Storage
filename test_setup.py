#!/usr/bin/env python3
"""
Тестовый скрипт для проверки подключения к Binance API.
Проверяет загрузку API ключей и доступность WebSocket.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавление пути к модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.config.settings import load_config, get_api_credentials


async def test_api_keys():
    """Тест загрузки API ключей."""
    print("🔐 Тестирование загрузки API ключей...")
    
    # Загрузка конфигурации
    config = load_config()
    
    # Проверка API ключей
    api_creds = config.get('api_credentials', {})
    
    print(f"📋 Использование testnet: {config.get('api', {}).get('use_testnet', True)}")
    print(f"🔗 WebSocket URL: {api_creds.get('ws_url', 'Не найден')}")
    print(f"🏭 Режим: {'PRODUCTION' if not config.get('api', {}).get('use_testnet', True) else 'TESTNET'}")
    
    if api_creds.get('api_key'):
        api_key = api_creds['api_key']
        print(f"✅ API ключ загружен: {api_key[:8]}...{api_key[-4:]}")
    else:
        print("❌ API ключ не найден")
        
    if api_creds.get('secret_key'):
        secret = api_creds['secret_key']
        print(f"✅ Secret ключ загружен: {secret[:8]}...{secret[-4:]}")
    else:
        print("❌ Secret ключ не найден")
        
    # Проверка Tardis API
    tardis_key = config.get('tardis_api_key', '')
    if tardis_key:
        print(f"✅ Tardis API ключ: {tardis_key[:8]}...{tardis_key[-4:]}")
    else:
        print("❌ Tardis API ключ не найден")


async def test_websocket_connection():
    """Тест WebSocket подключения."""
    print("\n🌐 Тестирование WebSocket подключения...")
    
    try:
        # Попытка импорта websockets
        import websockets
        print("✅ Модуль websockets доступен")
        
        # Загрузка конфигурации
        config = load_config()
        api_creds = config.get('api_credentials', {})
        ws_url = api_creds.get('ws_url', 'wss://stream.binancefuture.com/ws/')
        
        # Тестовое подключение
        test_url = f"{ws_url}btcusdt@depth"
        print(f"🔗 Попытка подключения к: {test_url}")
        
        async with websockets.connect(test_url, ping_timeout=5) as websocket:
            print("✅ WebSocket подключение успешно")
            
            # Получение одного сообщения для проверки
            message = await asyncio.wait_for(websocket.recv(), timeout=10)
            print(f"📨 Получено тестовое сообщение ({len(message)} символов)")
            
    except ImportError:
        print("❌ Модуль websockets не установлен")
        print("💡 Установите: pip install websockets")
    except Exception as e:
        print(f"❌ Ошибка WebSocket подключения: {e}")


async def test_data_directories():
    """Тест создания директорий для данных."""
    print("\n📁 Проверка директорий...")
    
    config = load_config()
    base_dir = Path(config.get('storage', {}).get('base_dir', './data/binance_orderbook'))
    logs_dir = Path('collector/logs')
    
    # Создание директорий
    base_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Директория данных: {base_dir}")
    print(f"✅ Директория логов: {logs_dir}")


async def main():
    """Основная функция тестирования."""
    print("🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ СБОРА ДАННЫХ BINANCE ORDERBOOK")
    print("=" * 60)
    
    try:
        await test_api_keys()
        await test_data_directories()
        await test_websocket_connection()
        
        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("\n💡 Если все тесты прошли успешно, можно запускать:")
        print("   python -m collector.main --symbol BTCUSDT --output-dir ./data --test-mode")
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())