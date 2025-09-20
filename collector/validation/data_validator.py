"""
Система валидации соответствия данных техническому заданию
Проверяет качество и структуру собираемых данных orderbook
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import sys

# Добавляем путь к collector модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

@dataclass
class ValidationResult:
    """Результат валидации"""
    test_name: str
    passed: bool
    details: str
    expected_value: Any = None
    actual_value: Any = None
    severity: str = "error"  # error, warning, info

@dataclass
class DataQualityReport:
    """Отчет о качестве данных"""
    timestamp: datetime
    total_tests: int
    passed_tests: int
    failed_tests: int
    warnings: int
    overall_score: float  # 0-100%
    results: List[ValidationResult]
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'failed_tests': self.failed_tests,
            'warnings': self.warnings,
            'overall_score': self.overall_score,
            'results': [
                {
                    'test_name': r.test_name,
                    'passed': r.passed,
                    'details': r.details,
                    'expected_value': r.expected_value,
                    'actual_value': r.actual_value,
                    'severity': r.severity
                }
                for r in self.results
            ]
        }

class DataValidator:
    """Валидатор данных по техническому заданию"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.logger = logging.getLogger(__name__)
        
        # Требования ТЗ для валидации
        self.requirements = {
            'data_types': {
                'book_ticker': ['symbol', 'bid_price', 'bid_qty', 'ask_price', 'ask_qty', 'ts_exchange'],
                'trades': ['symbol', 'price', 'quantity', 'quote_quantity', 'is_buyer_maker', 'ts_exchange'],
                'depth_events': ['symbol', 'data', 'ts_exchange']
            },
            'update_frequency': {
                'book_ticker': 100,  # миллисекунды максимум между обновлениями
                'trades': 1000,      # миллисекунды
                'depth_events': 100  # миллисекунды
            },
            'data_quality': {
                'price_precision': 8,    # знаков после запятой
                'quantity_precision': 8,
                'max_spread_percent': 1.0,  # максимальный спред в процентах
                'min_records_per_hour': 1000  # минимум записей в час для активной пары
            }
        }
    
    async def create_connection(self):
        """Создает подключение к базе данных"""
        try:
            import asyncpg
            return await asyncpg.connect(self.connection_string)
        except ImportError:
            self.logger.error("Требуется установка: pip install asyncpg")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка подключения к БД: {e}")
            return None
    
    async def validate_table_structure(self, conn) -> List[ValidationResult]:
        """Валидирует структуру таблиц"""
        results = []
        
        for table_name, required_columns in self.requirements['data_types'].items():
            try:
                # Получаем структуру таблицы
                columns_query = """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = $1
                ORDER BY ordinal_position
                """
                
                columns = await conn.fetch(columns_query, table_name)
                actual_columns = [col['column_name'] for col in columns]
                
                # Проверяем наличие обязательных колонок
                missing_columns = set(required_columns) - set(actual_columns)
                
                if missing_columns:
                    results.append(ValidationResult(
                        test_name=f"Table structure: {table_name}",
                        passed=False,
                        details=f"Отсутствуют обязательные колонки: {missing_columns}",
                        expected_value=required_columns,
                        actual_value=actual_columns,
                        severity="error"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Table structure: {table_name}",
                        passed=True,
                        details=f"Все обязательные колонки присутствуют",
                        expected_value=required_columns,
                        actual_value=actual_columns,
                        severity="info"
                    ))
                    
                # Проверяем типы данных
                for col in columns:
                    col_name = col['column_name']
                    data_type = col['data_type']
                    
                    if col_name in ['bid_price', 'ask_price', 'price', 'quantity']:
                        if 'numeric' not in data_type.lower() and 'decimal' not in data_type.lower():
                            results.append(ValidationResult(
                                test_name=f"Data type: {table_name}.{col_name}",
                                passed=False,
                                details=f"Неправильный тип данных для цены/количества: {data_type}",
                                expected_value="NUMERIC/DECIMAL",
                                actual_value=data_type,
                                severity="warning"
                            ))
                            
            except Exception as e:
                results.append(ValidationResult(
                    test_name=f"Table structure: {table_name}",
                    passed=False,
                    details=f"Ошибка проверки структуры: {e}",
                    severity="error"
                ))
        
        return results
    
    async def validate_data_freshness(self, conn) -> List[ValidationResult]:
        """Валидирует свежесть данных"""
        results = []
        
        for table_name in self.requirements['data_types'].keys():
            try:
                # Проверяем последние обновления
                freshness_query = f"""
                SELECT 
                    max(ts_exchange) as last_update,
                    count(*) as total_records,
                    count(DISTINCT symbol) as unique_symbols
                FROM {table_name}
                WHERE ts_exchange > now() - interval '1 hour'
                """
                
                result = await conn.fetchrow(freshness_query)
                
                if not result['last_update']:
                    results.append(ValidationResult(
                        test_name=f"Data freshness: {table_name}",
                        passed=False,
                        details="Нет свежих данных за последний час",
                        expected_value="Данные не старше 1 часа",
                        actual_value="Нет данных",
                        severity="error"
                    ))
                    continue
                
                # Проверяем возраст последних данных
                last_update = result['last_update']
                age_minutes = (datetime.utcnow().replace(tzinfo=last_update.tzinfo) - last_update).total_seconds() / 60
                
                if age_minutes > 10:  # Данные старше 10 минут
                    results.append(ValidationResult(
                        test_name=f"Data freshness: {table_name}",
                        passed=False,
                        details=f"Последние данные старше {age_minutes:.1f} минут",
                        expected_value="< 10 минут",
                        actual_value=f"{age_minutes:.1f} минут",
                        severity="warning"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Data freshness: {table_name}",
                        passed=True,
                        details=f"Данные свежие: {age_minutes:.1f} минут назад",
                        expected_value="< 10 минут",
                        actual_value=f"{age_minutes:.1f} минут",
                        severity="info"
                    ))
                
                # Проверяем объем данных
                min_records = self.requirements['data_quality']['min_records_per_hour']
                if result['total_records'] < min_records:
                    results.append(ValidationResult(
                        test_name=f"Data volume: {table_name}",
                        passed=False,
                        details=f"Недостаточно данных за час: {result['total_records']}",
                        expected_value=f">= {min_records}",
                        actual_value=result['total_records'],
                        severity="warning"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Data volume: {table_name}",
                        passed=True,
                        details=f"Достаточно данных: {result['total_records']} записей",
                        expected_value=f">= {min_records}",
                        actual_value=result['total_records'],
                        severity="info"
                    ))
                    
            except Exception as e:
                results.append(ValidationResult(
                    test_name=f"Data freshness: {table_name}",
                    passed=False,
                    details=f"Ошибка проверки свежести: {e}",
                    severity="error"
                ))
        
        return results
    
    async def validate_data_quality(self, conn) -> List[ValidationResult]:
        """Валидирует качество данных"""
        results = []
        
        try:
            # Проверяем качество book_ticker данных
            bt_quality_query = """
            SELECT 
                symbol,
                count(*) as records,
                avg((ask_price - bid_price) / ((ask_price + bid_price) / 2) * 100) as avg_spread_percent,
                max((ask_price - bid_price) / ((ask_price + bid_price) / 2) * 100) as max_spread_percent,
                count(CASE WHEN bid_price <= 0 OR ask_price <= 0 THEN 1 END) as invalid_prices,
                count(CASE WHEN bid_qty <= 0 OR ask_qty <= 0 THEN 1 END) as invalid_quantities,
                count(CASE WHEN ask_price <= bid_price THEN 1 END) as inverted_spread
            FROM book_ticker 
            WHERE ts_exchange > now() - interval '1 hour'
            GROUP BY symbol
            ORDER BY records DESC
            LIMIT 10
            """
            
            bt_stats = await conn.fetch(bt_quality_query)
            
            for stat in bt_stats:
                symbol = stat['symbol']
                
                # Проверяем спред
                max_spread = stat['max_spread_percent'] or 0
                if max_spread > self.requirements['data_quality']['max_spread_percent']:
                    results.append(ValidationResult(
                        test_name=f"Spread quality: {symbol}",
                        passed=False,
                        details=f"Максимальный спред слишком большой: {max_spread:.3f}%",
                        expected_value=f"<= {self.requirements['data_quality']['max_spread_percent']}%",
                        actual_value=f"{max_spread:.3f}%",
                        severity="warning"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Spread quality: {symbol}",
                        passed=True,
                        details=f"Спред в норме: max {max_spread:.3f}%",
                        expected_value=f"<= {self.requirements['data_quality']['max_spread_percent']}%",
                        actual_value=f"{max_spread:.3f}%",
                        severity="info"
                    ))
                
                # Проверяем некорректные цены
                if stat['invalid_prices'] > 0:
                    results.append(ValidationResult(
                        test_name=f"Price validity: {symbol}",
                        passed=False,
                        details=f"Найдены некорректные цены: {stat['invalid_prices']} записей",
                        expected_value="0",
                        actual_value=stat['invalid_prices'],
                        severity="error"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Price validity: {symbol}",
                        passed=True,
                        details="Все цены корректны",
                        expected_value="0",
                        actual_value="0",
                        severity="info"
                    ))
                
                # Проверяем инвертированный спред
                if stat['inverted_spread'] > 0:
                    results.append(ValidationResult(
                        test_name=f"Spread direction: {symbol}",
                        passed=False,
                        details=f"Найден инвертированный спред: {stat['inverted_spread']} записей",
                        expected_value="0",
                        actual_value=stat['inverted_spread'],
                        severity="error"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Spread direction: {symbol}",
                        passed=True,
                        details="Направление спреда корректно",
                        expected_value="0",
                        actual_value="0",
                        severity="info"
                    ))
            
            # Проверяем качество trades данных
            trades_quality_query = """
            SELECT 
                count(*) as total_trades,
                count(CASE WHEN price <= 0 THEN 1 END) as invalid_prices,
                count(CASE WHEN quantity <= 0 THEN 1 END) as invalid_quantities,
                avg(quantity) as avg_trade_size,
                count(CASE WHEN is_buyer_maker = true THEN 1 END) as maker_trades,
                count(CASE WHEN is_buyer_maker = false THEN 1 END) as taker_trades
            FROM trades 
            WHERE ts_exchange > now() - interval '1 hour'
            """
            
            trades_stat = await conn.fetchrow(trades_quality_query)
            
            if trades_stat:
                # Проверяем соотношение maker/taker
                total_trades = trades_stat['total_trades']
                if total_trades > 0:
                    maker_ratio = trades_stat['maker_trades'] / total_trades
                    if maker_ratio < 0.3 or maker_ratio > 0.7:
                        results.append(ValidationResult(
                            test_name="Maker/Taker balance",
                            passed=False,
                            details=f"Несбалансированное соотношение maker/taker: {maker_ratio:.2%}",
                            expected_value="30-70%",
                            actual_value=f"{maker_ratio:.2%}",
                            severity="warning"
                        ))
                    else:
                        results.append(ValidationResult(
                            test_name="Maker/Taker balance",
                            passed=True,
                            details=f"Сбалансированное соотношение: {maker_ratio:.2%}",
                            expected_value="30-70%",
                            actual_value=f"{maker_ratio:.2%}",
                            severity="info"
                        ))
                
                # Проверяем некорректные сделки
                if trades_stat['invalid_prices'] > 0 or trades_stat['invalid_quantities'] > 0:
                    results.append(ValidationResult(
                        test_name="Trades data validity",
                        passed=False,
                        details=f"Некорректные данные сделок: {trades_stat['invalid_prices']} цен, {trades_stat['invalid_quantities']} количеств",
                        expected_value="0",
                        actual_value=f"{trades_stat['invalid_prices']} + {trades_stat['invalid_quantities']}",
                        severity="error"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name="Trades data validity",
                        passed=True,
                        details="Все данные сделок корректны",
                        expected_value="0",
                        actual_value="0",
                        severity="info"
                    ))
                    
        except Exception as e:
            results.append(ValidationResult(
                test_name="Data quality check",
                passed=False,
                details=f"Ошибка проверки качества данных: {e}",
                severity="error"
            ))
        
        return results
    
    async def validate_update_frequency(self, conn) -> List[ValidationResult]:
        """Валидирует частоту обновлений данных"""
        results = []
        
        try:
            # Анализируем интервалы между обновлениями
            frequency_query = """
            WITH intervals AS (
                SELECT 
                    symbol,
                    ts_exchange,
                    LAG(ts_exchange) OVER (PARTITION BY symbol ORDER BY ts_exchange) as prev_ts
                FROM book_ticker 
                WHERE ts_exchange > now() - interval '10 minutes'
            ),
            interval_stats AS (
                SELECT 
                    symbol,
                    count(*) as updates,
                    avg(EXTRACT(milliseconds FROM (ts_exchange - prev_ts))) as avg_interval_ms,
                    max(EXTRACT(milliseconds FROM (ts_exchange - prev_ts))) as max_interval_ms,
                    percentile_disc(0.95) WITHIN GROUP (ORDER BY EXTRACT(milliseconds FROM (ts_exchange - prev_ts))) as p95_interval_ms
                FROM intervals 
                WHERE prev_ts IS NOT NULL
                GROUP BY symbol
            )
            SELECT * FROM interval_stats 
            WHERE updates > 10
            ORDER BY updates DESC
            LIMIT 5
            """
            
            freq_stats = await conn.fetch(frequency_query)
            
            for stat in freq_stats:
                symbol = stat['symbol']
                avg_interval = stat['avg_interval_ms'] or 0
                max_interval = stat['max_interval_ms'] or 0
                p95_interval = stat['p95_interval_ms'] or 0
                
                expected_max = self.requirements['update_frequency']['book_ticker']
                
                if avg_interval > expected_max:
                    results.append(ValidationResult(
                        test_name=f"Update frequency: {symbol}",
                        passed=False,
                        details=f"Средний интервал слишком большой: {avg_interval:.1f}ms",
                        expected_value=f"<= {expected_max}ms",
                        actual_value=f"{avg_interval:.1f}ms",
                        severity="warning"
                    ))
                else:
                    results.append(ValidationResult(
                        test_name=f"Update frequency: {symbol}",
                        passed=True,
                        details=f"Частота обновлений в норме: {avg_interval:.1f}ms",
                        expected_value=f"<= {expected_max}ms",
                        actual_value=f"{avg_interval:.1f}ms",
                        severity="info"
                    ))
                
                # Дополнительная проверка p95
                if p95_interval > expected_max * 3:  # Допускаем 3x для 95 перцентиля
                    results.append(ValidationResult(
                        test_name=f"Update consistency: {symbol}",
                        passed=False,
                        details=f"95% интервалов превышают норму: {p95_interval:.1f}ms",
                        expected_value=f"<= {expected_max * 3}ms",
                        actual_value=f"{p95_interval:.1f}ms",
                        severity="warning"
                    ))
                    
        except Exception as e:
            results.append(ValidationResult(
                test_name="Update frequency check",
                passed=False,
                details=f"Ошибка проверки частоты обновлений: {e}",
                severity="error"
            ))
        
        return results
    
    async def validate_continuous_aggregates(self, conn) -> List[ValidationResult]:
        """Валидирует работу continuous aggregates"""
        results = []
        
        try:
            # Проверяем наличие агрегатов
            agg_query = """
            SELECT view_name, materialized_only, finalized 
            FROM timescaledb_information.continuous_aggregates
            """
            
            aggregates = await conn.fetch(agg_query)
            expected_aggregates = ['bt_1s_continuous', 'trade_1s_continuous', 'depth_1s_continuous']
            
            found_aggs = [agg['view_name'] for agg in aggregates]
            missing_aggs = set(expected_aggregates) - set(found_aggs)
            
            if missing_aggs:
                results.append(ValidationResult(
                    test_name="Continuous aggregates presence",
                    passed=False,
                    details=f"Отсутствуют агрегаты: {missing_aggs}",
                    expected_value=expected_aggregates,
                    actual_value=found_aggs,
                    severity="error"
                ))
            else:
                results.append(ValidationResult(
                    test_name="Continuous aggregates presence",
                    passed=True,
                    details="Все агрегаты созданы",
                    expected_value=expected_aggregates,
                    actual_value=found_aggs,
                    severity="info"
                ))
            
            # Проверяем актуальность агрегатов
            for agg_name in expected_aggregates:
                if agg_name in found_aggs:
                    agg_data_query = f"""
                    SELECT 
                        count(*) as records,
                        max(ts_bucket) as last_bucket
                    FROM {agg_name}
                    WHERE ts_bucket > now() - interval '1 hour'
                    """
                    
                    agg_stat = await conn.fetchrow(agg_data_query)
                    
                    if agg_stat['records'] == 0:
                        results.append(ValidationResult(
                            test_name=f"Aggregate data: {agg_name}",
                            passed=False,
                            details="Нет данных в агрегате за последний час",
                            expected_value="> 0",
                            actual_value="0",
                            severity="warning"
                        ))
                    else:
                        results.append(ValidationResult(
                            test_name=f"Aggregate data: {agg_name}",
                            passed=True,
                            details=f"Агрегат содержит {agg_stat['records']} записей",
                            expected_value="> 0",
                            actual_value=agg_stat['records'],
                            severity="info"
                        ))
                        
        except Exception as e:
            results.append(ValidationResult(
                test_name="Continuous aggregates check",
                passed=False,
                details=f"Ошибка проверки агрегатов: {e}",
                severity="error"
            ))
        
        return results
    
    async def run_full_validation(self) -> DataQualityReport:
        """Запускает полную валидацию всех компонентов"""
        self.logger.info("🔍 Начинаем полную валидацию данных...")
        
        conn = await self.create_connection()
        if not conn:
            # Возвращаем отчет об ошибке подключения
            return DataQualityReport(
                timestamp=datetime.utcnow(),
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                warnings=0,
                overall_score=0.0,
                results=[ValidationResult(
                    test_name="Database connection",
                    passed=False,
                    details="Не удалось подключиться к базе данных",
                    severity="error"
                )]
            )
        
        try:
            all_results = []
            
            # Выполняем все валидации
            all_results.extend(await self.validate_table_structure(conn))
            all_results.extend(await self.validate_data_freshness(conn))
            all_results.extend(await self.validate_data_quality(conn))
            all_results.extend(await self.validate_update_frequency(conn))
            all_results.extend(await self.validate_continuous_aggregates(conn))
            
            # Подсчитываем статистику
            total_tests = len(all_results)
            passed_tests = len([r for r in all_results if r.passed])
            failed_tests = len([r for r in all_results if not r.passed and r.severity == "error"])
            warnings = len([r for r in all_results if not r.passed and r.severity == "warning"])
            
            # Рассчитываем общий score
            if total_tests > 0:
                # Ошибки снижают score больше чем warnings
                error_penalty = failed_tests * 10
                warning_penalty = warnings * 3
                overall_score = max(0, 100 - error_penalty - warning_penalty)
            else:
                overall_score = 0
            
            return DataQualityReport(
                timestamp=datetime.utcnow(),
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                warnings=warnings,
                overall_score=overall_score,
                results=all_results
            )
            
        finally:
            await conn.close()


async def main():
    """Демонстрация системы валидации"""
    
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Connection string
        # Пример использования
    connection_string = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/database")
    
    validator = DataValidator(connection_string)
    
    print("🔍 Запуск валидации соответствия данных ТЗ")
    print("=" * 60)
    
    # Запускаем полную валидацию
    report = await validator.run_full_validation()
    
    # Выводим результаты
    print(f"📊 Результаты валидации ({report.timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"   Всего тестов: {report.total_tests}")
    print(f"   Пройдено: {report.passed_tests} ✅")
    print(f"   Ошибки: {report.failed_tests} ❌")
    print(f"   Предупреждения: {report.warnings} ⚠️")
    print(f"   Общий балл: {report.overall_score:.1f}/100")
    
    print(f"\n📋 Детальные результаты:")
    print("-" * 60)
    
    for result in report.results:
        status_icon = "✅" if result.passed else ("❌" if result.severity == "error" else "⚠️")
        print(f"{status_icon} {result.test_name}")
        print(f"   {result.details}")
        if result.expected_value is not None:
            print(f"   Ожидалось: {result.expected_value}, Получено: {result.actual_value}")
        print()
    
    # Сохраняем отчет
    report_file = Path("logs/data_quality_report.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
    
    print(f"💾 Отчет сохранен: {report_file}")
    
    # Возвращаем код выхода основанный на результатах
    if report.failed_tests > 0:
        print("\n❌ Валидация завершена с ошибками")
        return 1
    elif report.warnings > 0:
        print("\n⚠️ Валидация завершена с предупреждениями")
        return 0
    else:
        print("\n✅ Валидация пройдена успешно!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)