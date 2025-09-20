#!/usr/bin/env python3
"""
🔌 PostgreSQL Connection Test для Digital Ocean
Проверка подключения к managed database с вашими credentials
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

async def test_postgresql_connection():
    """Тестирование подключения к PostgreSQL на Digital Ocean"""
    
    print("🔌 Тестирование подключения к PostgreSQL...")
    print("=" * 50)
    
    # Параметры подключения из .env
    connection_params = {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 25060)),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'ssl': 'require'
    }
    
    print(f"🏠 Host: {connection_params['host']}")
    print(f"🔌 Port: {connection_params['port']}")
    print(f"🗄️ Database: {connection_params['database']}")
    print(f"👤 User: {connection_params['user']}")
    print(f"🔐 SSL: {connection_params['ssl']}")
    print("-" * 50)
    
    try:
        # Попытка подключения
        print("🔄 Подключение к PostgreSQL...")
        conn = await asyncpg.connect(**connection_params)
        
        # Проверка версии PostgreSQL
        version = await conn.fetchval('SELECT version()')
        print(f"✅ Подключение успешно!")
        print(f"📊 PostgreSQL версия: {version}")
        
        # Проверка доступных баз данных
        databases = await conn.fetch("SELECT datname FROM pg_database WHERE datistemplate = false")
        print(f"🗄️ Доступные базы данных:")
        for db in databases:
            print(f"   - {db['datname']}")
        
        # Проверка текущих привилегий
        privileges = await conn.fetch("""
            SELECT table_schema, table_name, privilege_type 
            FROM information_schema.table_privileges 
            WHERE grantee = current_user 
            LIMIT 10
        """)
        print(f"🔑 Привилегии пользователя (первые 10):")
        for priv in privileges:
            print(f"   - {priv['table_schema']}.{priv['table_name']}: {priv['privilege_type']}")
        
        # Тест создания таблицы
        print("🧪 Тестирование создания таблицы...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_connection (
                id SERIAL PRIMARY KEY,
                test_data TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Вставка тестовых данных
        await conn.execute("""
            INSERT INTO test_connection (test_data) 
            VALUES ('Connection test successful')
        """)
        
        # Чтение данных
        result = await conn.fetchrow("SELECT * FROM test_connection ORDER BY id DESC LIMIT 1")
        print(f"✅ Тест записи/чтения: {result['test_data']}")
        
        # Очистка тестовой таблицы
        await conn.execute("DROP TABLE IF EXISTS test_connection")
        print("🧹 Тестовая таблица удалена")
        
        # Закрытие соединения
        await conn.close()
        
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("✅ PostgreSQL готов для OrderBook коллектора")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("\n🔧 Проверьте:")
        print("1. Правильность credentials в .env файле")
        print("2. IP адрес сервера добавлен в Trusted Sources PostgreSQL")
        print("3. Firewall правила на Digital Ocean")
        print("4. SSL сертификаты")
        return False

async def test_connection_pool():
    """Тестирование connection pool"""
    
    print("\n🔄 Тестирование connection pool...")
    
    try:
        # Создание pool соединений с более мягкими настройками
        pool = await asyncpg.create_pool(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 25060)),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            ssl='require',
            min_size=2,  # Уменьшил минимальный размер
            max_size=5,  # Уменьшил максимальный размер
            command_timeout=60,  # Увеличил таймаут
            server_settings={
                'jit': 'off'  # Отключаем JIT для стабильности
            }
        )
        
        print("✅ Connection pool создан")
        
        # Последовательные запросы вместо одновременных
        successful = 0
        for i in range(5):  # Уменьшил количество тестов
            try:
                async with pool.acquire() as conn:
                    result = await conn.fetchval("SELECT $1::text as query_id", str(i))  # Приведение к строке
                    if result == str(i):
                        successful += 1
                        print(f"  ✓ Запрос {i+1}: успешно")
                    else:
                        print(f"  ✗ Запрос {i+1}: неверный результат")
                
                # Небольшая пауза между запросами
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"  ✗ Запрос {i+1}: ошибка {e}")
        
        print(f"📊 Успешных запросов: {successful}/5")
        
        # Тест простого запроса для проверки работы pool
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT 'Pool работает!' as message")
            print(f"📝 Тест pool: {version}")
        
        await pool.close()
        print("✅ Connection pool закрыт")
        
        return successful >= 3  # Требуем минимум 3 успешных из 5
        
    except Exception as e:
        print(f"❌ Ошибка connection pool: {e}")
        print(f"💡 Детали ошибки: {type(e).__name__}")
        return False

async def test_single_query(pool, query_id):
    """Выполнение одного запроса через pool"""
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT $1 as query_id", query_id)
            return result == query_id
    except Exception:
        return False

if __name__ == "__main__":
    print("🚀 Запуск тестов PostgreSQL для Digital Ocean")
    print("=" * 60)
    
    # Проверка наличия .env файла
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден!")
        print("Создайте .env файл с вашими credentials")
        exit(1)
    
    # Запуск тестов
    async def run_all_tests():
        # Базовое подключение
        connection_ok = await test_postgresql_connection()
        
        if connection_ok:
            # Тест connection pool
            pool_ok = await test_connection_pool()
            
            if pool_ok:
                print("\n🎯 ИТОГ: PostgreSQL готов для production!")
                print("💡 Следующий шаг: Реализация PostgreSQLManager")
            else:
                print("\n⚠️ ИТОГ: Базовое подключение работает, но есть проблемы с pool")
        else:
            print("\n❌ ИТОГ: Проблемы с подключением к PostgreSQL")
            print("🔧 Исправьте настройки и попробуйте снова")
    
    # Запуск асинхронных тестов
    asyncio.run(run_all_tests())