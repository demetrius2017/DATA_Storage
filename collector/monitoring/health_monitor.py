"""
Real-time Monitoring System for OrderBook Data Collection
Мониторинг ingestion rate, latency, data quality для 200 торговых пар
"""

import asyncio
import os
import asyncpg
import ssl
from urllib.parse import urlparse
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import logging
from collections import defaultdict, deque
import aiohttp
from aiohttp import web
import weakref

logger = logging.getLogger(__name__)

@dataclass
class IngestionMetrics:
    """Метрики ingestion для одного символа"""
    symbol: str
    symbol_id: int
    
    # Основные метрики за последний час
    book_ticker_count: int = 0
    trades_count: int = 0
    depth_events_count: int = 0
    
    # Последние обновления
    last_book_ticker: Optional[datetime] = None
    last_trade: Optional[datetime] = None
    last_depth_event: Optional[datetime] = None
    
    # Latency метрики (миллисекунды)
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    
    # Quality метрики
    invalid_spreads: int = 0
    invalid_prices: int = 0
    missing_data_gaps: int = 0
    
    # Статус
    is_healthy: bool = True
    status_message: str = "OK"
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для JSON serialization"""
        result = asdict(self)
        # Конвертация datetime в ISO строки
        for field in ['last_book_ticker', 'last_trade', 'last_depth_event']:
            if result[field]:
                result[field] = result[field].isoformat()
        return result

@dataclass 
class SystemMetrics:
    """Общие метрики системы"""
    timestamp: datetime
    total_symbols: int
    active_symbols: int
    healthy_symbols: int
    
    # Aggregate метрики
    total_updates_per_minute: float
    total_volume_per_hour: float
    average_latency_ms: float
    
    # Ресурсы
    db_connections_active: int
    db_connections_total: int
    memory_usage_mb: float
    
    # Errors
    total_errors_last_hour: int
    websocket_disconnects: int
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result

class HealthChecker:
    """Проверка состояния системы"""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        
    async def check_symbol_health(self, symbol_id: int, symbol: str) -> IngestionMetrics:
        """Проверка здоровья одного символа"""
        async with self.db_pool.acquire() as conn:
            # Метрики за последний час
            metrics_query = """
            SELECT 
                COUNT(CASE WHEN bt.symbol_id IS NOT NULL THEN 1 END) as bt_count,
                COUNT(CASE WHEN tr.symbol_id IS NOT NULL THEN 1 END) as tr_count,
                MAX(bt.ts_exchange) as last_bt,
                MAX(tr.ts_exchange) as last_tr,
                AVG(EXTRACT(EPOCH FROM (bt.ts_ingest - bt.ts_exchange)) * 1000) as avg_latency,
                MAX(EXTRACT(EPOCH FROM (bt.ts_ingest - bt.ts_exchange)) * 1000) as max_latency,
                PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (bt.ts_ingest - bt.ts_exchange)) * 1000
                ) as p95_latency
            FROM marketdata.symbols s
            LEFT JOIN marketdata.book_ticker bt ON (
                s.id = bt.symbol_id AND 
                bt.ts_exchange >= NOW() - INTERVAL '1 hour'
            )
            LEFT JOIN marketdata.trades tr ON (
                s.id = tr.symbol_id AND
                tr.ts_exchange >= NOW() - INTERVAL '1 hour'
            )
            WHERE s.id = $1
            GROUP BY s.id
            """
            
            row = await conn.fetchrow(metrics_query, symbol_id)
            
            # Quality check
            quality_query = """
            SELECT 
                COUNT(CASE WHEN bt.spread <= 0 THEN 1 END) as invalid_spreads,
                COUNT(CASE WHEN bt.best_bid <= 0 OR bt.best_ask <= 0 THEN 1 END) as invalid_prices
            FROM marketdata.book_ticker bt
            WHERE 
                bt.symbol_id = $1 
                AND bt.ts_exchange >= NOW() - INTERVAL '1 hour'
            """
            
            quality_row = await conn.fetchrow(quality_query, symbol_id)
            
        # Формирование метрик
        metrics = IngestionMetrics(
            symbol=symbol,
            symbol_id=symbol_id,
            book_ticker_count=row['bt_count'] or 0,
            trades_count=row['tr_count'] or 0,
            last_book_ticker=row['last_bt'],
            last_trade=row['last_tr'],
            avg_latency_ms=float(row['avg_latency'] or 0),
            max_latency_ms=float(row['max_latency'] or 0),
            p95_latency_ms=float(row['p95_latency'] or 0),
            invalid_spreads=quality_row['invalid_spreads'] or 0,
            invalid_prices=quality_row['invalid_prices'] or 0
        )
        
        # Определение здоровья
        now = datetime.now(timezone.utc)
        
        if metrics.last_book_ticker:
            last_update_age = (now - metrics.last_book_ticker).total_seconds()
            if last_update_age > 300:  # 5 минут без обновлений
                metrics.is_healthy = False
                metrics.status_message = f"No updates for {last_update_age:.0f}s"
        else:
            metrics.is_healthy = False
            metrics.status_message = "No data"
            
        if metrics.invalid_spreads > 10:
            metrics.is_healthy = False
            metrics.status_message = f"High invalid spreads: {metrics.invalid_spreads}"
            
        if metrics.avg_latency_ms > 1000:  # > 1 секунды
            metrics.is_healthy = False
            metrics.status_message = f"High latency: {metrics.avg_latency_ms:.0f}ms"
            
        return metrics
    
    async def check_system_health(self) -> SystemMetrics:
        """Проверка общего состояния системы"""
        async with self.db_pool.acquire() as conn:
            # Общие метрики
            system_query = """
            SELECT 
                COUNT(DISTINCT s.id) as total_symbols,
                COUNT(DISTINCT CASE WHEN bt.symbol_id IS NOT NULL THEN s.id END) as active_symbols,
                SUM(bt_count) as total_bt_updates,
                SUM(tr_count) as total_tr_updates,
                AVG(avg_latency) as system_avg_latency
            FROM marketdata.symbols s
            LEFT JOIN (
                SELECT 
                    symbol_id,
                    COUNT(*) as bt_count,
                    AVG(EXTRACT(EPOCH FROM (ts_ingest - ts_exchange)) * 1000) as avg_latency
                FROM marketdata.book_ticker
                WHERE ts_exchange >= NOW() - INTERVAL '1 hour'
                GROUP BY symbol_id
            ) bt_stats ON s.id = bt_stats.symbol_id
            LEFT JOIN (
                SELECT symbol_id, COUNT(*) as tr_count
                FROM marketdata.trades  
                WHERE ts_exchange >= NOW() - INTERVAL '1 hour'
                GROUP BY symbol_id
            ) tr_stats ON s.id = tr_stats.symbol_id
            WHERE s.is_active = true
            """
            
            row = await conn.fetchrow(system_query)
            
            # DB connection stats
            db_stats_row = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_connections,
                    COUNT(CASE WHEN state = 'active' THEN 1 END) as active_connections
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)
            
        # Расчет метрик  
        total_updates = (row['total_bt_updates'] or 0) + (row['total_tr_updates'] or 0)
        updates_per_minute = total_updates / 60.0  # За час -> за минуту
        
        return SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            total_symbols=row['total_symbols'] or 0,
            active_symbols=row['active_symbols'] or 0,
            healthy_symbols=0,  # Будет заполнено отдельно
            total_updates_per_minute=updates_per_minute,
            total_volume_per_hour=0.0,  # TODO: добавить volume расчет
            average_latency_ms=float(row['system_avg_latency'] or 0),
            db_connections_active=db_stats_row['active_connections'],
            db_connections_total=db_stats_row['total_connections'],
            memory_usage_mb=0.0,  # TODO: добавить memory monitoring
            total_errors_last_hour=0,  # TODO: добавить error tracking
            websocket_disconnects=0
        )

class MonitoringDashboard:
    """HTTP dashboard для мониторинга"""
    
    def __init__(self, db_pool: asyncpg.Pool, port: int = 8000):
        self.db_pool = db_pool
        self.port = port
        self.health_checker = HealthChecker(db_pool)
        self.app = web.Application()
        self.setup_routes()
        
        # Кэш метрик
        self.metrics_cache: Dict[str, Any] = {}
        self.cache_ttl = 30  # секунд
        self.last_cache_update = 0
        
    def setup_routes(self):
        """Настройка HTTP маршрутов"""
        self.app.router.add_get('/', self.dashboard_html)
        self.app.router.add_get('/api/metrics', self.api_metrics)
        self.app.router.add_get('/api/symbols', self.api_symbols)
        self.app.router.add_get('/api/system', self.api_system)
        self.app.router.add_get('/health', self.health_check)
        
    async def dashboard_html(self, request) -> web.Response:
        """HTML dashboard"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OrderBook Collection Monitoring</title>
            <meta charset="utf-8">
            <meta http-equiv="refresh" content="30">
            <style>
                body { font-family: monospace; margin: 20px; background: #1e1e1e; color: #fff; }
                .container { max-width: 1200px; margin: 0 auto; }
                .metric-card { background: #2d2d2d; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .healthy { border-left: 5px solid #4CAF50; }
                .warning { border-left: 5px solid #FF9800; }
                .error { border-left: 5px solid #F44336; }
                .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }
                table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                th, td { padding: 8px; text-align: left; border-bottom: 1px solid #444; }
                th { background: #333; }
                .status-ok { color: #4CAF50; }
                .status-error { color: #F44336; }
                .number { font-weight: bold; color: #00BCD4; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 OrderBook Collection Monitoring</h1>
                <div id="lastUpdate"></div>
                
                <div class="grid">
                    <div class="metric-card healthy">
                        <h3>System Status</h3>
                        <div id="systemStatus">Loading...</div>
                    </div>
                    
                    <div class="metric-card">
                        <h3>Performance</h3>
                        <div id="performance">Loading...</div>
                    </div>
                    
                    <div class="metric-card">
                        <h3>Database</h3>
                        <div id="database">Loading...</div>
                    </div>
                </div>
                
                <div class="metric-card">
                    <h3>Symbol Details</h3>
                    <div id="symbolsTable">Loading...</div>
                </div>
            </div>
            
            <script>
                async function updateDashboard() {
                    try {
                        // System metrics
                        const systemResp = await fetch('/api/system');
                        const systemData = await systemResp.json();
                        
                        document.getElementById('systemStatus').innerHTML = `
                            <div>Active Symbols: <span class="number">${systemData.active_symbols}</span>/${systemData.total_symbols}</div>
                            <div>Healthy Symbols: <span class="number">${systemData.healthy_symbols}</span></div>
                            <div>Updates/min: <span class="number">${systemData.total_updates_per_minute.toFixed(1)}</span></div>
                        `;
                        
                        document.getElementById('performance').innerHTML = `
                            <div>Avg Latency: <span class="number">${systemData.average_latency_ms.toFixed(1)}ms</span></div>
                            <div>Errors/hour: <span class="number">${systemData.total_errors_last_hour}</span></div>
                        `;
                        
                        document.getElementById('database').innerHTML = `
                            <div>Active Connections: <span class="number">${systemData.db_connections_active}</span>/${systemData.db_connections_total}</div>
                            <div>Memory: <span class="number">${systemData.memory_usage_mb.toFixed(0)}MB</span></div>
                        `;
                        
                        // Symbols table
                        const symbolsResp = await fetch('/api/symbols');
                        const symbolsData = await symbolsResp.json();
                        
                        let tableHtml = `
                            <table>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Status</th>
                                    <th>Updates/hour</th>
                                    <th>Last Update</th>
                                    <th>Latency (ms)</th>
                                    <th>Issues</th>
                                </tr>
                        `;
                        
                        symbolsData.forEach(symbol => {
                            const statusClass = symbol.is_healthy ? 'status-ok' : 'status-error';
                            const lastUpdate = symbol.last_book_ticker ? 
                                new Date(symbol.last_book_ticker).toLocaleTimeString() : 'Never';
                            
                            tableHtml += `
                                <tr>
                                    <td>${symbol.symbol}</td>
                                    <td class="${statusClass}">${symbol.status_message}</td>
                                    <td class="number">${symbol.book_ticker_count}</td>
                                    <td>${lastUpdate}</td>
                                    <td class="number">${symbol.avg_latency_ms.toFixed(1)}</td>
                                    <td class="number">${symbol.invalid_spreads + symbol.invalid_prices}</td>
                                </tr>
                            `;
                        });
                        
                        tableHtml += '</table>';
                        document.getElementById('symbolsTable').innerHTML = tableHtml;
                        
                        document.getElementById('lastUpdate').innerHTML = 
                            `Last updated: ${new Date().toLocaleTimeString()}`;
                            
                    } catch (error) {
                        console.error('Error updating dashboard:', error);
                    }
                }
                
                // Update every 30 seconds
                updateDashboard();
                setInterval(updateDashboard, 30000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html, content_type='text/html')
    
    async def get_cached_metrics(self) -> Dict[str, Any]:
        """Получение метрик с кэшированием"""
        now = time.time()
        if now - self.last_cache_update > self.cache_ttl:
            # Обновление кэша
            try:
                # Загрузка всех символов
                async with self.db_pool.acquire() as conn:
                    symbols = await conn.fetch("""
                        SELECT id, symbol FROM marketdata.symbols 
                        WHERE is_active = true 
                        ORDER BY symbol
                    """)
                
                # Проверка каждого символа
                symbol_metrics = []
                healthy_count = 0
                
                for symbol_row in symbols:
                    metrics = await self.health_checker.check_symbol_health(
                        symbol_row['id'], symbol_row['symbol']
                    )
                    symbol_metrics.append(metrics)
                    if metrics.is_healthy:
                        healthy_count += 1
                
                # Системные метрики
                system_metrics = await self.health_checker.check_system_health()
                system_metrics.healthy_symbols = healthy_count
                
                self.metrics_cache = {
                    'system': system_metrics,
                    'symbols': symbol_metrics,
                    'timestamp': now
                }
                self.last_cache_update = now
                
            except Exception as e:
                logger.error(f"Error updating metrics cache: {e}")
                
        return self.metrics_cache
    
    async def api_metrics(self, request) -> web.Response:
        """API: все метрики"""
        metrics = await self.get_cached_metrics()
        return web.json_response({
            'system': metrics.get('system', {}).to_dict() if metrics.get('system') else {},
            'symbols': [m.to_dict() for m in metrics.get('symbols', [])],
            'cache_age': time.time() - metrics.get('timestamp', 0)
        })
    
    async def api_symbols(self, request) -> web.Response:
        """API: метрики символов"""
        metrics = await self.get_cached_metrics()
        symbols_data = [m.to_dict() for m in metrics.get('symbols', [])]
        return web.json_response(symbols_data)
    
    async def api_system(self, request) -> web.Response:
        """API: системные метрики"""
        metrics = await self.get_cached_metrics()
        system_data = metrics.get('system', {})
        if hasattr(system_data, 'to_dict'):
            return web.json_response(system_data.to_dict())
        return web.json_response({})
    
    async def health_check(self, request) -> web.Response:
        """Health check endpoint"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval('SELECT 1')
                if result == 1:
                    # Добавляем сводку по эндпоинтам для быстрой проверки окружения
                    recent = await self._recent_ingestion_summary(conn)
                    return web.json_response({
                        'status': 'healthy', 
                        'database': 'ok',
                        'binance': {
                            'base_url': os.getenv('BINANCE_BASE_URL', 'https://fapi.binance.com'),
                            'ws_url': os.getenv('BINANCE_WS_URL', 'wss://fstream.binance.com/ws/')
                        },
                        'recent': recent
                    })
        except Exception as e:
            return web.json_response(
                {'status': 'unhealthy', 'error': str(e)}, 
                status=500
            )
    
    async def start(self):
        """Запуск HTTP сервера"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        logger.info(f"Monitoring dashboard started on http://0.0.0.0:{self.port}")

    async def _recent_ingestion_summary(self, conn: asyncpg.Connection) -> Dict[str, Any]:
        """Сводка по свежим данным: счетчики за 1 минуту и последние timestamps."""
        try:
            bt1 = await conn.fetchval("SELECT COUNT(*) FROM marketdata.book_ticker WHERE ts_exchange >= NOW() - INTERVAL '1 minute'")
            tr1 = await conn.fetchval("SELECT COUNT(*) FROM marketdata.trades WHERE ts_exchange >= NOW() - INTERVAL '1 minute'")
            de1 = await conn.fetchval("SELECT COUNT(*) FROM marketdata.depth_events WHERE ts_exchange >= NOW() - INTERVAL '1 minute'")
            last_bt = await conn.fetchval("SELECT MAX(ts_exchange) FROM marketdata.book_ticker")
            last_tr = await conn.fetchval("SELECT MAX(ts_exchange) FROM marketdata.trades")
            last_de = await conn.fetchval("SELECT MAX(ts_exchange) FROM marketdata.depth_events")
            to_iso = lambda v: v.isoformat() if v else None
            return {
                'last': {
                    'book_ticker': to_iso(last_bt),
                    'trades': to_iso(last_tr),
                    'depth_events': to_iso(last_de)
                },
                'counts_1m': {
                    'book_ticker': int(bt1 or 0),
                    'trades': int(tr1 or 0),
                    'depth_events': int(de1 or 0)
                }
            }
        except Exception as e:
            return {'error': str(e)}

class MonitoringSystem:
    """Главный класс системы мониторинга"""
    
    def __init__(self, db_connection_string: str, dashboard_port: int = 8000):
        self.db_connection_string = db_connection_string
        self.dashboard_port = dashboard_port
        self.db_pool: Optional[asyncpg.Pool] = None
        self.dashboard: Optional[MonitoringDashboard] = None
        self.running = False
        
    async def start(self):
        """Запуск системы мониторинга"""
        logger.info("Запуск системы мониторинга...")
        
        # Подключение к БД
        # Map sslmode from DSN to asyncpg ssl context
        ssl_ctx = None
        try:
            parsed = urlparse(self.db_connection_string)
            query = {}
            if parsed.query:
                for part in parsed.query.split('&'):
                    if not part:
                        continue
                    k, _, v = part.partition('=')
                    query[k] = v
            sslmode = (query.get('sslmode') or os.getenv('DB_SSLMODE') or 'require').lower()
            if sslmode in ('disable', 'allow', 'prefer'):
                ssl_ctx = False
            elif sslmode in ('require', 'verify-none'):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ssl_ctx = ctx
            elif sslmode in ('verify-full', 'verify-ca'):
                cafile = os.getenv('DB_SSLROOTCERT')
                if cafile and os.path.exists(cafile):
                    ctx = ssl.create_default_context(cafile=cafile)
                else:
                    ctx = ssl.create_default_context()
                ctx.check_hostname = True
                ctx.verify_mode = ssl.CERT_REQUIRED
                ssl_ctx = ctx
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ssl_ctx = ctx
        except Exception:
            ssl_ctx = None

        self.db_pool = await asyncpg.create_pool(
            self.db_connection_string,
            min_size=2,
            max_size=5,
            command_timeout=30,
            ssl=ssl_ctx
        )
        
        # Запуск dashboard
        self.dashboard = MonitoringDashboard(self.db_pool, self.dashboard_port)
        await self.dashboard.start()
        
        self.running = True
        logger.info(f"Мониторинг запущен на порту {self.dashboard_port}")
        
    async def stop(self):
        """Остановка системы мониторинга"""
        logger.info("Остановка системы мониторинга...")
        self.running = False
        
        if self.db_pool:
            await self.db_pool.close()
            
        logger.info("Система мониторинга остановлена")

# MAIN для запуска standalone
async def main():
    import os
    
    DB_CONNECTION = os.getenv('DATABASE_URL', 
        'postgresql://ingestor:password@localhost:5432/marketdata')
    DASHBOARD_PORT = int(os.getenv('MONITORING_PORT', '8000'))
    
    monitoring = MonitoringSystem(DB_CONNECTION, DASHBOARD_PORT)
    
    try:
        await monitoring.start()
        
        # Ожидание
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Завершение мониторинга по Ctrl+C")
    finally:
        await monitoring.stop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())