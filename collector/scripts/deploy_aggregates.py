#!/usr/bin/env python3
"""
Скрипт развертывания системы автоматических агрегатов
Использовать когда восстановится соединение с базой данных

Решает проблему: "⚠️ Отсутствие aggregates: Нет автоматического создания bt_1s/trade_1s таблиц"
"""

import asyncio
import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from collector.aggregates.aggregate_manager import AggregateManager
    print("✅ Модуль AggregateManager импортирован")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Установите зависимости: pip install asyncpg")
    sys.exit(1)

async def deploy_aggregates():
    """Основная функция развертывания"""
    
    print("🚀 Развертывание системы автоматических агрегатов")
    print("=" * 60)
    
    # Connection string (должен быть обновлен для актуальной БД)
    connection_string = os.getenv(
        'DATABASE_URL',
        "postgresql://user:password@host:port/database"
    )
    
    manager = AggregateManager(connection_string)
    
    try:
        # 1. Проверяем соединение
        print("1. Проверка соединения с базой данных...")
        pool = await manager.create_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT version()")
            print(f"✅ PostgreSQL: {result[:50]}...")
        await pool.close()
        
        # 2. Создаем continuous aggregates
        print("\n2. Создание continuous aggregates...")
        success = await manager.setup_continuous_aggregates()
        
        if not success:
            print("❌ Ошибка создания агрегатов")
            return False
            
        print("✅ Continuous aggregates созданы")
        
        # 3. Проверяем статус
        print("\n3. Проверка статуса агрегатов...")
        status = await manager.get_aggregate_status()
        
        if 'error' in status:
            print(f"❌ Ошибка получения статуса: {status['error']}")
            return False
            
        print(f"📊 Создано агрегатов: {len(status.get('aggregates', []))}")
        print(f"📋 Настроено политик: {len(status.get('policies', []))}")
        
        # Детальная информация
        for agg in status.get('aggregates', []):
            view_name = agg['view_name']
            materialized = agg['materialized_only']
            finalized = agg['finalized']
            count = status['stats'].get(view_name, 0)
            
            print(f"   📈 {view_name}:")
            print(f"      • Записей: {count}")
            print(f"      • Материализован: {materialized}")
            print(f"      • Финализован: {finalized}")
        
        # 4. Принудительное обновление
        print("\n4. Принудительное обновление агрегатов...")
        refresh_success = await manager.refresh_aggregates()
        
        if refresh_success:
            print("✅ Агрегаты принудительно обновлены")
        else:
            print("⚠️ Проблема с обновлением (возможно, нет исходных данных)")
        
        # 5. Тестируем получение данных
        print("\n5. Тестирование получения данных...")
        symbols_to_test = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
        
        for symbol in symbols_to_test:
            sample = await manager.get_market_data_sample(symbol, 3)
            if sample:
                print(f"✅ {symbol}: {len(sample)} записей найдено")
                latest = sample[0]
                print(f"   Последняя запись: {latest['ts_bucket']}")
                print(f"   BID: {latest.get('bid_close')}, ASK: {latest.get('ask_close')}")
                print(f"   Volume: {latest.get('volume')}, Trades: {latest.get('trade_count')}")
            else:
                print(f"⚠️ {symbol}: данных не найдено")
        
        print("\n" + "=" * 60)
        print("🎉 СИСТЕМА АВТОМАТИЧЕСКИХ АГРЕГАТОВ РАЗВЕРНУТА!")
        print("=" * 60)
        
        # Показываем полезные SQL запросы
        print("\n📋 Полезные SQL запросы для мониторинга:")
        print("   • Статус агрегатов:")
        print("     SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates;")
        print("   • Последние данные:")
        print("     SELECT * FROM market_data_1s WHERE symbol = 'BTCUSDT' ORDER BY ts_bucket DESC LIMIT 5;")
        print("   • Статистика объемов:")
        print("     SELECT symbol, sum(volume), count(*) FROM trade_1s_continuous WHERE ts_bucket > now() - interval '1 hour' GROUP BY symbol;")
        
        return True
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        return False

async def validate_aggregates():
    """Валидация существующих агрегатов"""
    
    print("🔍 Валидация существующих агрегатов")
    print("=" * 50)
    
    connection_string = os.getenv(
        'DATABASE_URL',
        "postgresql://user:password@host:port/database"
    )
    
    manager = AggregateManager(connection_string)
    
    try:
        status = await manager.get_aggregate_status()
        
        if 'error' in status:
            print(f"❌ Ошибка: {status['error']}")
            return False
            
        aggregates = status.get('aggregates', [])
        if not aggregates:
            print("⚠️ Агрегаты не найдены. Требуется развертывание.")
            return False
            
        print(f"✅ Найдено {len(aggregates)} агрегатов:")
        
        expected_aggregates = ['bt_1s_continuous', 'trade_1s_continuous', 'depth_1s_continuous']
        found_aggregates = [agg['view_name'] for agg in aggregates]
        
        for expected in expected_aggregates:
            if expected in found_aggregates:
                count = status['stats'].get(expected, 0)
                print(f"   ✅ {expected}: {count} записей")
            else:
                print(f"   ❌ {expected}: НЕ НАЙДЕН")
                
        # Проверяем представление market_data_1s
        try:
            sample = await manager.get_market_data_sample('BTCUSDT', 1)
            if sample:
                print("   ✅ Представление market_data_1s: работает")
            else:
                print("   ⚠️ Представление market_data_1s: нет данных")
        except Exception as e:
            print(f"   ❌ Представление market_data_1s: ошибка ({e})")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка валидации: {e}")
        return False

def main():
    """Основная функция"""
    
    if len(sys.argv) > 1 and sys.argv[1] == 'validate':
        # Режим валидации
        result = asyncio.run(validate_aggregates())
    else:
        # Режим развертывания
        result = asyncio.run(deploy_aggregates())
    
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()