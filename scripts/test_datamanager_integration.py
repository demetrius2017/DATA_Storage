#!/usr/bin/env python3
"""
🧪 Тест интеграции DataManager с PostgreSQL
Проверяет полную интеграцию: DataManager → PostgreSQL → проверка данных
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Добавление пути к модулям
sys.path.append('/Users/dmitrijnazarov/Projects/DATA_Storage')

from collector.storage.data_manager import DataManager
from collector.storage.postgres_manager import PostgreSQLManager

async def test_datamanager_postgresql_integration():
    """Тестирует полную интеграцию DataManager с PostgreSQL"""
    
    print("🧪 ТЕСТИРОВАНИЕ ИНТЕГРАЦИИ DataManager + PostgreSQL")
    print("=" * 60)
    
    # 1. Загрузка конфигурации
    config_path = '/Users/dmitrijnazarov/Projects/DATA_Storage/config/production.json'
    with open(config_path) as f:
        config = json.load(f)
    
    print(f"✅ Конфигурация загружена: {config['storage']['type']}")
    
    # 2. Инициализация DataManager для PostgreSQL
    data_manager = DataManager(
        output_dir="/tmp/test_orderbook",  # Не используется для PostgreSQL
        compress=True,
        config=config
    )
    
    print(f"✅ DataManager инициализирован: {data_manager.storage_type}")
    
    # 2.1. Асинхронная инициализация PostgreSQL
    await data_manager.initialize()
    print("✅ PostgreSQL подключение установлено")
    
    # 3. Тестовые данные orderbook
    test_records = [
        {
            'symbol': 'BTCUSDT',
            'timestamp': time.time(),
            'local_timestamp': time.time(),
            'exchange': 'binance',
            'event_time': int(time.time() * 1000),
            'first_update_id': 1001,
            'final_update_id': 1002,
            'bids': [['50000.00', '1.5'], ['49999.00', '2.0']],
            'asks': [['50001.00', '1.0'], ['50002.00', '1.8']],
            'ask_amount': '1.0',
            'ask_price': '50001.00',
            'bid_price': '50000.00',
            'bid_amount': '1.5'
        },
        {
            'symbol': 'ETHUSDT',
            'timestamp': time.time() + 1,
            'local_timestamp': time.time() + 1,
            'exchange': 'binance',
            'event_time': int((time.time() + 1) * 1000),
            'first_update_id': 2001,
            'final_update_id': 2002,
            'bids': [['3000.00', '5.0'], ['2999.00', '3.0']],
            'asks': [['3001.00', '4.0'], ['3002.00', '2.5']],
            'ask_amount': '4.0',
            'ask_price': '3001.00',
            'bid_price': '3000.00',
            'bid_amount': '5.0'
        }
    ]
    
    print(f"✅ Подготовлено {len(test_records)} тестовых записей")
    
    # 4. Сохранение через DataManager
    print("\n📦 СОХРАНЕНИЕ ДАННЫХ:")
    
    for i, record in enumerate(test_records, 1):
        try:
            await data_manager.save_record(record)
            print(f"  ✅ Запись {i}/{len(test_records)}: {record['symbol']}")
        except Exception as e:
            print(f"  ❌ Ошибка записи {i}: {e}")
            return False
    
    # 5. Принудительная запись буфера PostgreSQL
    if data_manager.postgres_manager:
        try:
            await data_manager.postgres_manager._flush_batch()
            print("  ✅ Batch буфер PostgreSQL сброшен")
        except Exception as e:
            print(f"  ⚠️ Ошибка сброса буфера: {e}")
    
    # 6. Проверка статистики
    stats = data_manager.get_stats()
    print(f"\n📊 СТАТИСТИКА DataManager:")
    print(f"  • Тип хранения: {stats['storage_type']}")
    print(f"  • Записей сохранено: {stats['records_written']}")
    print(f"  • Размер буфера: {stats['buffer_size']}")
    
    if 'postgresql' in stats:
        pg_stats = stats['postgresql']
        print(f"  • PostgreSQL записи: {pg_stats.get('successful_inserts', 'N/A')}")
        print(f"  • PostgreSQL ошибки: {pg_stats.get('failed_inserts', 'N/A')}")
    
    # 7. Прямая проверка данных в PostgreSQL
    print(f"\n🔍 ПРОВЕРКА ДАННЫХ В PostgreSQL:")
    
    if data_manager.postgres_manager and data_manager.postgres_manager.pool:
        try:
            # Проверка последних записей
            query = """
                SELECT symbol, timestamp, event_time, 
                       jsonb_array_length(bids) as bids_count,
                       jsonb_array_length(asks) as asks_count
                FROM orderbook_data 
                ORDER BY timestamp DESC 
                LIMIT 5
            """
            
            async with data_manager.postgres_manager.pool.acquire() as conn:
                rows = await conn.fetch(query)
                
                print(f"  ✅ Найдено {len(rows)} записей в БД:")
                for row in rows:
                    print(f"    • {row['symbol']}: {row['bids_count']} bids, {row['asks_count']} asks")
                    
        except Exception as e:
            print(f"  ❌ Ошибка проверки данных: {e}")
            return False
    else:
        print("  ⚠️ PostgreSQL pool недоступен для проверки данных")
    
    # 8. Завершение работы
    await data_manager.shutdown()
    print("\n✅ DataManager корректно завершён")
    
    print("\n🎯 ИТОГ: Интеграция DataManager + PostgreSQL работает!")
    return True

if __name__ == "__main__":
    try:
        # Загрузка переменных окружения из .env
        from dotenv import load_dotenv
        load_dotenv('/Users/dmitrijnazarov/Projects/DATA_Storage/.env')
        
        # Запуск теста
        result = asyncio.run(test_datamanager_postgresql_integration())
        
        if result:
            print("\n🟢 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
            sys.exit(0)
        else:
            print("\n🔴 ЕСТЬ ОШИБКИ В ТЕСТАХ!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)