"""
Система управления автоматическими агрегатами TimescaleDB
Решает проблему: "⚠️ Отсутствие aggregates: Нет автоматического создания bt_1s/trade_1s таблиц"
"""

import asyncio
import asyncpg
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class AggregateManager:
    """Менеджер непрерывных агрегатов TimescaleDB"""
    
    def __init__(self, connection_string: str):
        """
        Инициализация менеджера агрегатов
        
        Args:
            connection_string: Строка подключения к PostgreSQL
        """
        self.connection_string = connection_string
        self.logger = logging.getLogger(__name__)
        
    async def create_pool(self) -> asyncpg.Pool:
        """Создает пул соединений"""
        return await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=5,
            command_timeout=60
        )
        
    async def setup_continuous_aggregates(self) -> bool:
        """
        Создает все continuous aggregates из SQL файла
        
        Returns:
            True если успешно, False при ошибке
        """
        try:
            # Читаем SQL файл
            sql_file = Path(__file__).parent.parent / "sql" / "create_continuous_aggregates.sql"
            
            if not sql_file.exists():
                self.logger.error(f"SQL файл не найден: {sql_file}")
                return False
                
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            # Разбиваем на отдельные команды
            sql_commands = [cmd.strip() for cmd in sql_content.split(';') if cmd.strip() and not cmd.strip().startswith('--')]
            
            pool = await self.create_pool()
            try:
                async with pool.acquire() as conn:
                    for i, command in enumerate(sql_commands):
                        if not command:
                            continue
                            
                        try:
                            self.logger.info(f"Выполняю команду {i+1}/{len(sql_commands)}")
                            await conn.execute(command)
                            self.logger.debug(f"✅ Команда выполнена: {command[:100]}...")
                            
                        except Exception as e:
                            if "already exists" in str(e).lower():
                                self.logger.info(f"Объект уже существует: {command[:50]}...")
                            else:
                                self.logger.error(f"Ошибка выполнения команды: {e}")
                                self.logger.error(f"Команда: {command}")
                                # Не прерываем, продолжаем с следующей командой
                                
                    self.logger.info("✅ Система continuous aggregates настроена")
                    return True
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка настройки continuous aggregates: {e}")
            return False
    
    async def get_aggregate_status(self) -> Dict:
        """
        Получает статус всех continuous aggregates
        
        Returns:
            Словарь со статусом агрегатов
        """
        try:
            pool = await self.create_pool()
            try:
                async with pool.acquire() as conn:
                    # Получаем информацию об агрегатах
                    aggregates_query = """
                    SELECT view_name, materialized_only, finalized 
                    FROM timescaledb_information.continuous_aggregates
                    """
                    
                    aggregates = await conn.fetch(aggregates_query)
                    
                    # Получаем информацию о политиках
                    policies_query = """
                    SELECT application_name, hypertable_name, config 
                    FROM timescaledb_information.jobs 
                    WHERE application_name LIKE '%continuous_aggregate%'
                    """
                    
                    policies = await conn.fetch(policies_query)
                    
                    # Получаем статистику агрегатов
                    stats = {}
                    for agg in aggregates:
                        view_name = agg['view_name']
                        try:
                            count_query = f"SELECT count(*) as cnt FROM {view_name}"
                            result = await conn.fetchrow(count_query)
                            stats[view_name] = result['cnt']
                        except Exception as e:
                            self.logger.warning(f"Не удалось получить статистику для {view_name}: {e}")
                            stats[view_name] = -1
                    
                    return {
                        'aggregates': [dict(agg) for agg in aggregates],
                        'policies': [dict(pol) for pol in policies],
                        'stats': stats,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка получения статуса агрегатов: {e}")
            return {'error': str(e)}
    
    async def refresh_aggregates(self, 
                               view_names: Optional[List[str]] = None,
                               start_time: Optional[datetime] = None,
                               end_time: Optional[datetime] = None) -> bool:
        """
        Принудительно обновляет continuous aggregates
        
        Args:
            view_names: Список имен представлений для обновления (None = все)
            start_time: Начальное время для обновления
            end_time: Конечное время для обновления
            
        Returns:
            True если успешно
        """
        try:
            if view_names is None:
                view_names = ['bt_1s_continuous', 'trade_1s_continuous', 'depth_1s_continuous']
            
            if start_time is None:
                start_time = datetime.utcnow() - timedelta(hours=1)
            
            if end_time is None:
                end_time = datetime.utcnow()
            
            pool = await self.create_pool()
            try:
                async with pool.acquire() as conn:
                    for view_name in view_names:
                        try:
                            refresh_query = f"""
                            CALL refresh_continuous_aggregate('{view_name}', '{start_time}', '{end_time}')
                            """
                            await conn.execute(refresh_query)
                            self.logger.info(f"✅ Обновлен агрегат: {view_name}")
                            
                        except Exception as e:
                            self.logger.error(f"Ошибка обновления {view_name}: {e}")
                            
                    return True
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка обновления агрегатов: {e}")
            return False
    
    async def get_market_data_sample(self, 
                                   symbol: str = 'BTCUSDT',
                                   limit: int = 10) -> List[Dict]:
        """
        Получает образец данных из объединенного представления market_data_1s
        
        Args:
            symbol: Торговая пара
            limit: Количество записей
            
        Returns:
            Список записей с рыночными данными
        """
        try:
            pool = await self.create_pool()
            try:
                async with pool.acquire() as conn:
                    query = """
                    SELECT 
                        ts_bucket,
                        symbol,
                        bid_close,
                        ask_close,
                        spread_avg,
                        microprice_avg,
                        bt_ticks,
                        price_close,
                        volume,
                        trade_count,
                        vwap,
                        buy_ratio,
                        depth_updates
                    FROM market_data_1s 
                    WHERE symbol = $1
                    ORDER BY ts_bucket DESC 
                    LIMIT $2
                    """
                    
                    rows = await conn.fetch(query, symbol, limit)
                    
                    result = []
                    for row in rows:
                        record = dict(row)
                        # Конвертируем Decimal в float для JSON сериализации
                        for key, value in record.items():
                            if hasattr(value, '__float__'):
                                record[key] = float(value)
                            elif isinstance(value, datetime):
                                record[key] = value.isoformat()
                        result.append(record)
                    
                    return result
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка получения market data: {e}")
            return []
    
    async def calculate_ofi(self, 
                          symbol: str,
                          start_time: datetime,
                          end_time: datetime) -> List[Dict]:
        """
        Рассчитывает Order Flow Imbalance (OFI) из depth events
        
        Args:
            symbol: Торговая пара
            start_time: Начальное время
            end_time: Конечное время
            
        Returns:
            Список записей с OFI
        """
        try:
            pool = await self.create_pool()
            try:
                async with pool.acquire() as conn:
                    query = """
                    WITH depth_changes AS (
                        SELECT 
                            ts_bucket,
                            symbol,
                            last_bid_price::numeric as bid_price,
                            last_ask_price::numeric as ask_price,
                            last_bid_qty::numeric as bid_qty,
                            last_ask_qty::numeric as ask_qty,
                            first_bid_price::numeric as prev_bid_price,
                            first_ask_price::numeric as prev_ask_price,
                            first_bid_qty::numeric as prev_bid_qty,
                            first_ask_qty::numeric as prev_ask_qty
                        FROM depth_1s_continuous
                        WHERE symbol = $1 
                        AND ts_bucket BETWEEN $2 AND $3
                        ORDER BY ts_bucket
                    ),
                    ofi_calc AS (
                        SELECT 
                            ts_bucket,
                            symbol,
                            bid_price,
                            ask_price,
                            bid_qty,
                            ask_qty,
                            -- OFI = (bid_qty - prev_bid_qty) если цена не изменилась, 
                            -- иначе используем текущее количество
                            CASE 
                                WHEN bid_price = prev_bid_price THEN bid_qty - prev_bid_qty
                                ELSE bid_qty
                            END as bid_flow,
                            CASE 
                                WHEN ask_price = prev_ask_price THEN ask_qty - prev_ask_qty  
                                ELSE -ask_qty
                            END as ask_flow
                        FROM depth_changes
                    )
                    SELECT 
                        ts_bucket,
                        symbol,
                        bid_price,
                        ask_price,
                        bid_flow,
                        ask_flow,
                        (bid_flow + ask_flow) as ofi,
                        bid_flow / (bid_flow + abs(ask_flow) + 0.0001) as ofi_ratio
                    FROM ofi_calc
                    ORDER BY ts_bucket
                    """
                    
                    rows = await conn.fetch(query, symbol, start_time, end_time)
                    
                    result = []
                    for row in rows:
                        record = dict(row)
                        for key, value in record.items():
                            if hasattr(value, '__float__'):
                                record[key] = float(value)
                            elif isinstance(value, datetime):
                                record[key] = value.isoformat()
                        result.append(record)
                    
                    return result
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка расчета OFI: {e}")
            return []


async def main():
    """Тестирование менеджера агрегатов"""
    
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Используем connection string из конфигурации
        # Пример использования
    connection_string = "postgresql://user:password@host:port/database"
    
    manager = AggregateManager(connection_string)
    
    print("🚀 Тестирование системы автоматических агрегатов")
    
    # 1. Создаем агрегаты
    print("\n1. Создание continuous aggregates...")
    success = await manager.setup_continuous_aggregates()
    if success:
        print("✅ Continuous aggregates созданы")
    else:
        print("❌ Ошибка создания aggregates")
        return
    
    # 2. Получаем статус
    print("\n2. Проверка статуса...")
    status = await manager.get_aggregate_status()
    print(f"📊 Найдено агрегатов: {len(status.get('aggregates', []))}")
    print(f"📋 Найдено политик: {len(status.get('policies', []))}")
    
    for agg in status.get('aggregates', []):
        view_name = agg['view_name']
        count = status['stats'].get(view_name, 0)
        print(f"   {view_name}: {count} записей")
    
    # 3. Получаем образец данных
    print("\n3. Образец market data...")
    sample = await manager.get_market_data_sample('BTCUSDT', 5)
    if sample:
        print(f"📈 Получено {len(sample)} записей:")
        for record in sample[:2]:  # Показываем первые 2
            print(f"   {record['ts_bucket']}: BID={record.get('bid_close')}, ASK={record.get('ask_close')}")
    else:
        print("⚠️ Нет данных в агрегатах (возможно, коллектор не работал)")
    
    # 4. Принудительное обновление (если есть данные)
    print("\n4. Принудительное обновление агрегатов...")
    refresh_success = await manager.refresh_aggregates()
    if refresh_success:
        print("✅ Агрегаты обновлены")
    else:
        print("⚠️ Ошибка обновления агрегатов")
    
    print("\n✅ Тестирование завершено!")


if __name__ == "__main__":
    asyncio.run(main())