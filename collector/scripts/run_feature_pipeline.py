#!/usr/bin/env python3
"""
Интеграционный скрипт для ML Feature Pipeline
Извлекает данные из агрегатов и вычисляет фичи для машинного обучения

Использование:
    python collector/scripts/run_feature_pipeline.py --symbol BTCUSDT --hours 1
    python collector/scripts/run_feature_pipeline.py --all-symbols --hours 24 --output features.csv
"""

import asyncio
import argparse
import sys
import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from collector.features import FeaturePipeline, FeatureStorage
    from collector.aggregates import AggregateManager
    print("✅ Модули feature pipeline импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Установите зависимости: pip install numpy pandas asyncpg")
    sys.exit(1)

class MLFeaturePipeline:
    """Полный pipeline для подготовки ML данных"""
    
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.aggregate_manager = AggregateManager(connection_string)
        self.feature_pipeline = FeaturePipeline()
        self.feature_storage = FeatureStorage(connection_string)
        
    async def get_market_data_range(self, symbol: str, start_time: datetime, 
                                  end_time: datetime) -> List[Dict]:
        """Получает market data за указанный период"""
        
        try:
            import asyncpg
            pool = await asyncpg.create_pool(self.connection_string)
            
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
            AND ts_bucket BETWEEN $2 AND $3
            ORDER BY ts_bucket ASC
            """
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, symbol, start_time, end_time)
                
            await pool.close()
            
            # Конвертируем в список словарей
            result = []
            for row in rows:
                record = dict(row)
                # Конвертируем Decimal в float
                for key, value in record.items():
                    if hasattr(value, '__float__'):
                        record[key] = float(value)
                    elif isinstance(value, datetime):
                        record[key] = value
                        
                # Добавляем недостающие поля если они None
                record['bid_qty_close'] = record.get('bid_qty_close', 1.0)
                record['ask_qty_close'] = record.get('ask_qty_close', 1.0) 
                result.append(record)
                
            return result
            
        except Exception as e:
            print(f"❌ Ошибка получения market data: {e}")
            return []
    
    async def get_all_symbols(self) -> List[str]:
        """Получает список всех доступных символов"""
        
        try:
            import asyncpg
            pool = await asyncpg.create_pool(self.connection_string)
            
            query = """
            SELECT DISTINCT symbol 
            FROM market_data_1s 
            ORDER BY symbol
            """
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(query)
                
            await pool.close()
            
            return [row['symbol'] for row in rows]
            
        except Exception as e:
            print(f"❌ Ошибка получения символов: {e}")
            return []
    
    async def process_symbol_features(self, symbol: str, start_time: datetime,
                                    end_time: datetime, store_db: bool = False) -> List[Dict]:
        """Обрабатывает фичи для одного символа"""
        
        print(f"📊 Обработка {symbol}: {start_time} - {end_time}")
        
        # Получаем market data
        market_data = await self.get_market_data_range(symbol, start_time, end_time)
        
        if not market_data:
            print(f"⚠️ Нет данных для {symbol}")
            return []
            
        print(f"   📈 Найдено {len(market_data)} записей")
        
        # Вычисляем фичи
        features_list = self.feature_pipeline.process_market_data_batch(market_data)
        
        print(f"   🔬 Вычислено {len(features_list)} фичей")
        
        # Сохраняем в БД если требуется
        if store_db:
            await self.feature_storage.create_features_table()
            success = await self.feature_storage.store_features(features_list)
            if success:
                print(f"   ✅ Фичи сохранены в БД")
            else:
                print(f"   ⚠️ Ошибка сохранения в БД")
        
        # Конвертируем в словари для экспорта
        return [features.to_dict() for features in features_list]
    
    async def run_pipeline(self, symbols: List[str], hours: int, 
                         output_file: Optional[str] = None,
                         store_db: bool = False) -> List[Dict]:
        """Запускает полный pipeline для списка символов"""
        
        print("🚀 Запуск ML Feature Pipeline")
        print("=" * 60)
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        print(f"📅 Период: {start_time} - {end_time} ({hours} часов)")
        print(f"🎯 Символы: {', '.join(symbols)}")
        
        all_features = []
        
        for symbol in symbols:
            try:
                features = await self.process_symbol_features(
                    symbol, start_time, end_time, store_db
                )
                all_features.extend(features)
                
            except Exception as e:
                print(f"❌ Ошибка обработки {symbol}: {e}")
                continue
        
        print(f"\n📊 Итого обработано: {len(all_features)} фичей")
        
        # Сохраняем в файл если указан
        if output_file and all_features:
            await self.save_features_to_file(all_features, output_file)
        
        return all_features
    
    async def save_features_to_file(self, features: List[Dict], filename: str):
        """Сохраняет фичи в файл (CSV или JSON)"""
        
        if not features:
            print("⚠️ Нет фичей для сохранения")
            return
            
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if filename.endswith('.csv'):
            # Сохраняем в CSV
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                if features:
                    writer = csv.DictWriter(f, fieldnames=features[0].keys())
                    writer.writeheader()
                    writer.writerows(features)
                    
            print(f"📄 Фичи сохранены в CSV: {file_path}")
            
        elif filename.endswith('.json'):
            # Сохраняем в JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(features, f, indent=2, default=str)
                
            print(f"📄 Фичи сохранены в JSON: {file_path}")
            
        else:
            print(f"❌ Неподдерживаемый формат файла: {filename}")
    
    async def generate_feature_summary(self, features: List[Dict]) -> Dict:
        """Генерирует сводку по вычисленным фичам"""
        
        if not features:
            return {}
            
        import numpy as np
        
        summary = {
            'total_records': len(features),
            'symbols': list(set(f['symbol'] for f in features)),
            'time_range': {
                'start': min(f['timestamp'] for f in features),
                'end': max(f['timestamp'] for f in features)
            },
            'feature_stats': {}
        }
        
        # Статистика по численным фичам
        numeric_features = ['microprice', 'spread_rel', 'i1', 'ofi', 'volume_imbalance', 
                          'buy_volume_ratio', 'price_volatility']
        
        for feature in numeric_features:
            values = [f[feature] for f in features if f[feature] is not None]
            if values:
                summary['feature_stats'][feature] = {
                    'count': len(values),
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)),
                    'min': float(np.min(values)),
                    'max': float(np.max(values))
                }
        
        return summary

async def main():
    """Основная функция CLI"""
    
    parser = argparse.ArgumentParser(description='ML Feature Pipeline для market data')
    parser.add_argument('--symbol', type=str, help='Торговая пара (например, BTCUSDT)')
    parser.add_argument('--all-symbols', action='store_true', 
                       help='Обработать все доступные символы')
    parser.add_argument('--hours', type=int, default=1, 
                       help='Количество часов истории (по умолчанию: 1)')
    parser.add_argument('--output', type=str, 
                       help='Файл для сохранения (CSV или JSON)')
    parser.add_argument('--store-db', action='store_true',
                       help='Сохранить фичи в базу данных')
    parser.add_argument('--summary', action='store_true',
                       help='Показать сводку по фичам')
    
    args = parser.parse_args()
    
    # Валидация аргументов
    if not args.symbol and not args.all_symbols:
        print("❌ Укажите --symbol или --all-symbols")
        sys.exit(1)
    
    # Connection string
    # Пример использования
    connection_string = "postgresql://user:password@host:port/database"
    
    # Создаем pipeline
    pipeline = MLFeaturePipeline(connection_string)
    
    try:
        # Определяем символы для обработки
        if args.all_symbols:
            symbols = await pipeline.get_all_symbols()
            if not symbols:
                print("❌ Не найдено символов в базе данных")
                sys.exit(1)
        else:
            symbols = [args.symbol.upper()]
        
        # Запускаем pipeline
        features = await pipeline.run_pipeline(
            symbols=symbols,
            hours=args.hours,
            output_file=args.output,
            store_db=args.store_db
        )
        
        # Показываем сводку
        if args.summary and features:
            print("\n📋 Сводка по фичам:")
            print("=" * 40)
            
            summary = await pipeline.generate_feature_summary(features)
            
            print(f"Записей: {summary['total_records']}")
            print(f"Символы: {', '.join(summary['symbols'])}")
            print(f"Период: {summary['time_range']['start']} - {summary['time_range']['end']}")
            
            print("\nСтатистика фичей:")
            for feature, stats in summary['feature_stats'].items():
                print(f"  {feature}:")
                print(f"    mean: {stats['mean']:.6f}, std: {stats['std']:.6f}")
                print(f"    range: [{stats['min']:.6f}, {stats['max']:.6f}]")
        
        print(f"\n✅ Pipeline завершен успешно!")
        print(f"   Обработано: {len(features)} фичей")
        if args.output:
            print(f"   Сохранено в: {args.output}")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())