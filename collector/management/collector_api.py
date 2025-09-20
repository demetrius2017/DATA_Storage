"""
REST API для удаленного управления коллектором данных
Обеспечивает управление enhanced коллектором через HTTP API
"""

import asyncio
import json
import logging
import signal
import sys
import subprocess
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("❌ Требуется установка: pip install fastapi uvicorn websockets")
    sys.exit(1)

# Добавляем путь к collector модулям
sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.config.symbols_config import get_symbols_config, SHARDING_CONFIG
from collector.aggregates.aggregate_manager import AggregateManager

# Модели данных для API
class CollectorConfig(BaseModel):
    symbols: List[str]
    database_url: str
    max_connections: int = 10
    log_level: str = "INFO"
    enable_depth: bool = True
    enable_trades: bool = True

class CollectorStatus(BaseModel):
    is_running: bool
    pid: Optional[int] = None
    start_time: Optional[datetime] = None
    uptime_seconds: Optional[int] = None
    active_symbols: List[str] = []
    active_streams: int = 0
    total_records: int = 0
    last_update: Optional[datetime] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None

class StreamMetrics(BaseModel):
    stream_name: str
    symbols: List[str]
    status: str  # connected, disconnected, reconnecting
    messages_received: int = 0
    last_message_time: Optional[datetime] = None
    reconnect_count: int = 0

@dataclass
class CollectorManager:
    """Менеджер для управления enhanced коллектором"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.config_file = Path("collector/config/current_config.json")
        self.log_file = Path("logs/collector.log")
        self.status_file = Path("logs/collector_status.json")
        
        # Подключение к БД для мониторинга
        # База данных по умолчанию
        self.db_url = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/database")
        self.aggregate_manager = AggregateManager(self.db_url)
        
        self.logger = logging.getLogger(__name__)
        
    def save_config(self, config: CollectorConfig):
        """Сохраняет конфигурацию коллектора"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config.dict(), f, indent=2)
    
    def load_config(self) -> Optional[CollectorConfig]:
        """Загружает сохраненную конфигурацию"""
        if not self.config_file.exists():
            return None
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
            return CollectorConfig(**data)
        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")
            return None
    
    def start_collector(self, config: CollectorConfig) -> bool:
        """Запускает enhanced коллектор"""
        if self.is_running():
            self.logger.warning("Коллектор уже запущен")
            return False
            
        try:
            # Сохраняем конфигурацию
            self.save_config(config)
            
            # Создаем команду запуска
            env_vars = {
                "DATABASE_URL": config.database_url,
                "LOG_LEVEL": config.log_level,
                "SYMBOLS": ",".join(config.symbols),
                "PYTHONPATH": str(Path.cwd())
            }
            
            # Запускаем коллектор
            cmd = [
                sys.executable, 
                "collector/ingestion/enhanced_multi_stream_collector.py"
            ]
            
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.log_file, 'a') as log_f:
                self.process = subprocess.Popen(
                    cmd,
                    env={**dict(os.environ), **env_vars},
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    cwd=Path.cwd()
                )
            
            # Сохраняем статус
            self.save_status({
                'is_running': True,
                'pid': self.process.pid,
                'start_time': datetime.utcnow().isoformat(),
                'config': config.dict()
            })
            
            self.logger.info(f"Коллектор запущен с PID: {self.process.pid}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска коллектора: {e}")
            return False
    
    def stop_collector(self) -> bool:
        """Останавливает коллектор"""
        if not self.is_running():
            self.logger.warning("Коллектор не запущен")
            return False
            
        try:
            if self.process:
                # Посылаем SIGTERM для graceful shutdown
                self.process.terminate()
                
                # Ждем завершения
                try:
                    self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # Принудительное завершение
                    self.process.kill()
                    self.process.wait()
                
                self.process = None
            
            # Обновляем статус
            self.save_status({'is_running': False})
            
            self.logger.info("Коллектор остановлен")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка остановки коллектора: {e}")
            return False
    
    def restart_collector(self) -> bool:
        """Перезапускает коллектор"""
        config = self.load_config()
        if not config:
            self.logger.error("Нет сохраненной конфигурации для перезапуска")
            return False
            
        self.stop_collector()
        asyncio.sleep(2)  # Небольшая пауза
        return self.start_collector(config)
    
    def is_running(self) -> bool:
        """Проверяет, запущен ли коллектор"""
        if not self.process:
            return False
            
        return self.process.poll() is None
    
    def get_status(self) -> CollectorStatus:
        """Получает текущий статус коллектора"""
        is_running = self.is_running()
        
        status = CollectorStatus(
            is_running=is_running,
            pid=self.process.pid if self.process else None
        )
        
        if is_running and self.process:
            try:
                # Получаем информацию о процессе
                proc = psutil.Process(self.process.pid)
                status.cpu_percent = proc.cpu_percent()
                status.memory_mb = proc.memory_info().rss / 1024 / 1024
                status.start_time = datetime.fromtimestamp(proc.create_time())
                status.uptime_seconds = int((datetime.now() - status.start_time).total_seconds())
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return status
    
    def save_status(self, status_data: Dict):
        """Сохраняет статус в файл"""
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.status_file, 'w') as f:
            json.dump(status_data, f, indent=2, default=str)
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Получает статистику из базы данных"""
        try:
            # Получаем статус агрегатов
            agg_status = await self.aggregate_manager.get_aggregate_status()
            
            # Получаем основную статистику
            import asyncpg
            pool = await asyncpg.create_pool(self.db_url)
            
            try:
                async with pool.acquire() as conn:
                    # Общее количество записей
                    total_records = await conn.fetchval("SELECT count(*) FROM book_ticker")
                    
                    # Активные символы  
                    active_symbols = await conn.fetch("""
                        SELECT symbol, count(*) as records, max(ts_exchange) as last_update
                        FROM book_ticker 
                        WHERE ts_exchange > now() - interval '5 minutes'
                        GROUP BY symbol
                        ORDER BY last_update DESC
                    """)
                    
                    # Статистика по потокам
                    stream_stats = await conn.fetch("""
                        SELECT 
                            symbol,
                            count(*) as bt_records,
                            (SELECT count(*) FROM trades t WHERE t.symbol = bt.symbol 
                             AND t.ts_exchange > now() - interval '5 minutes') as trade_records,
                            max(ts_exchange) as last_bt_update
                        FROM book_ticker bt
                        WHERE ts_exchange > now() - interval '5 minutes'
                        GROUP BY symbol
                    """)
                    
                    return {
                        'total_records': total_records,
                        'active_symbols': [dict(row) for row in active_symbols],
                        'stream_statistics': [dict(row) for row in stream_stats],
                        'aggregates_status': agg_status
                    }
                    
            finally:
                await pool.close()
                
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики БД: {e}")
            return {'error': str(e)}

# Создаем FastAPI приложение
app = FastAPI(title="Collector Management API", version="1.0.0")

# CORS для веб-интерфейса
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный менеджер коллектора
collector_manager = CollectorManager()

# Подключенные WebSocket клиенты
websocket_clients = []

import os

@app.post("/api/collector/start")
async def start_collector(config: CollectorConfig):
    """Запускает коллектор с заданной конфигурацией"""
    success = collector_manager.start_collector(config)
    
    if success:
        return {"status": "success", "message": "Коллектор запущен"}
    else:
        raise HTTPException(status_code=400, detail="Ошибка запуска коллектора")

@app.post("/api/collector/stop")
async def stop_collector():
    """Останавливает коллектор"""
    success = collector_manager.stop_collector()
    
    if success:
        return {"status": "success", "message": "Коллектор остановлен"}
    else:
        raise HTTPException(status_code=400, detail="Ошибка остановки коллектора")

@app.post("/api/collector/restart")
async def restart_collector():
    """Перезапускает коллектор"""
    success = collector_manager.restart_collector()
    
    if success:
        return {"status": "success", "message": "Коллектор перезапущен"}
    else:
        raise HTTPException(status_code=400, detail="Ошибка перезапуска коллектора")

@app.get("/api/collector/status", response_model=CollectorStatus)
async def get_collector_status():
    """Получает текущий статус коллектора"""
    return collector_manager.get_status()

@app.get("/api/collector/config")
async def get_collector_config():
    """Получает текущую конфигурацию коллектора"""
    config = collector_manager.load_config()
    if config:
        return config.dict()
    else:
        raise HTTPException(status_code=404, detail="Конфигурация не найдена")

@app.get("/api/collector/logs")
async def get_collector_logs(lines: int = 100):
    """Получает последние строки лога коллектора"""
    if not collector_manager.log_file.exists():
        return {"logs": []}
    
    try:
        # Читаем последние N строк
        with open(collector_manager.log_file, 'r') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        return {"logs": [line.strip() for line in last_lines]}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения логов: {e}")

@app.get("/api/database/stats")
async def get_database_stats():
    """Получает статистику из базы данных"""
    stats = await collector_manager.get_database_stats()
    return stats

@app.get("/api/symbols/available")
async def get_available_symbols():
    """Получает список доступных символов для конфигурации"""
    config = get_symbols_config()
    return {
        "total_symbols": len(config['symbols']),
        "symbols_by_category": {
            "high_frequency": config['high_frequency'],
            "medium_frequency": config['medium_frequency'], 
            "low_frequency": config['low_frequency']
        },
        "sharding_config": SHARDING_CONFIG
    }

# WebSocket для real-time мониторинга
@app.websocket("/ws/monitoring")
async def websocket_monitoring(websocket: WebSocket):
    """WebSocket endpoint для real-time мониторинга"""
    await websocket.accept()
    websocket_clients.append(websocket)
    
    try:
        while True:
            # Отправляем статус каждые 5 секунд
            status = collector_manager.get_status()
            db_stats = await collector_manager.get_database_stats()
            
            message = {
                "type": "status_update",
                "timestamp": datetime.utcnow().isoformat(),
                "collector_status": status.dict(),
                "database_stats": db_stats
            }
            
            await websocket.send_json(message)
            await asyncio.sleep(5)
            
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)

# Статическая веб-страница для мониторинга
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Веб-интерфейс для мониторинга коллектора"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Collector Management Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .status-card { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .running { background-color: #d4edda; }
            .stopped { background-color: #f8d7da; }
            .btn { padding: 10px 15px; margin: 5px; cursor: pointer; border: none; border-radius: 3px; }
            .btn-success { background-color: #28a745; color: white; }
            .btn-danger { background-color: #dc3545; color: white; }
            .btn-warning { background-color: #ffc107; color: black; }
            .logs { background-color: #f8f9fa; padding: 10px; border-radius: 3px; height: 300px; overflow-y: scroll; font-family: monospace; }
            .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Collector Management Dashboard</h1>
            
            <div id="status" class="status-card">
                <h2>Статус коллектора</h2>
                <p>Загрузка...</p>
            </div>
            
            <div>
                <button class="btn btn-success" onclick="startCollector()">▶️ Запустить</button>
                <button class="btn btn-danger" onclick="stopCollector()">⏹️ Остановить</button>
                <button class="btn btn-warning" onclick="restartCollector()">🔄 Перезапустить</button>
            </div>
            
            <div class="metrics">
                <div class="status-card">
                    <h3>📈 Метрики БД</h3>
                    <div id="db-stats">Загрузка...</div>
                </div>
                
                <div class="status-card">
                    <h3>🎯 Активные символы</h3>
                    <div id="active-symbols">Загрузка...</div>
                </div>
            </div>
            
            <div class="status-card">
                <h3>📋 Логи коллектора</h3>
                <div id="logs" class="logs">Загрузка логов...</div>
            </div>
        </div>

        <script>
            let ws = null;
            
            function connectWebSocket() {
                ws = new WebSocket(`ws://${window.location.host}/ws/monitoring`);
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    updateStatus(data.collector_status);
                    updateDatabaseStats(data.database_stats);
                };
                
                ws.onclose = function() {
                    setTimeout(connectWebSocket, 5000);
                };
            }
            
            function updateStatus(status) {
                const statusDiv = document.getElementById('status');
                const isRunning = status.is_running;
                
                statusDiv.className = `status-card ${isRunning ? 'running' : 'stopped'}`;
                statusDiv.innerHTML = `
                    <h2>Статус коллектора</h2>
                    <p><strong>Состояние:</strong> ${isRunning ? '🟢 Запущен' : '🔴 Остановлен'}</p>
                    ${status.pid ? `<p><strong>PID:</strong> ${status.pid}</p>` : ''}
                    ${status.uptime_seconds ? `<p><strong>Время работы:</strong> ${Math.floor(status.uptime_seconds / 60)} мин</p>` : ''}
                    ${status.cpu_percent ? `<p><strong>CPU:</strong> ${status.cpu_percent.toFixed(1)}%</p>` : ''}
                    ${status.memory_mb ? `<p><strong>Память:</strong> ${status.memory_mb.toFixed(0)} MB</p>` : ''}
                `;
            }
            
            function updateDatabaseStats(stats) {
                if (stats.error) {
                    document.getElementById('db-stats').innerHTML = `<p style="color: red;">Ошибка: ${stats.error}</p>`;
                    return;
                }
                
                document.getElementById('db-stats').innerHTML = `
                    <p><strong>Всего записей:</strong> ${stats.total_records || 0}</p>
                    <p><strong>Активных символов:</strong> ${stats.active_symbols?.length || 0}</p>
                `;
                
                const symbolsDiv = document.getElementById('active-symbols');
                if (stats.active_symbols && stats.active_symbols.length > 0) {
                    const symbolsList = stats.active_symbols
                        .slice(0, 10)
                        .map(s => `<li>${s.symbol}: ${s.records} записей</li>`)
                        .join('');
                    symbolsDiv.innerHTML = `<ul>${symbolsList}</ul>`;
                } else {
                    symbolsDiv.innerHTML = '<p>Нет активных символов</p>';
                }
            }
            
            async function startCollector() {
                const config = {
                    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "DOTUSDT"],
                    database_url: "postgresql://user:password@host:port/database",
                    log_level: "INFO"
                };
                
                try {
                    const response = await fetch('/api/collector/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(config)
                    });
                    const result = await response.json();
                    alert(result.message);
                } catch (error) {
                    alert('Ошибка запуска: ' + error.message);
                }
            }
            
            async function stopCollector() {
                try {
                    const response = await fetch('/api/collector/stop', {method: 'POST'});
                    const result = await response.json();
                    alert(result.message);
                } catch (error) {
                    alert('Ошибка остановки: ' + error.message);
                }
            }
            
            async function restartCollector() {
                try {
                    const response = await fetch('/api/collector/restart', {method: 'POST'});
                    const result = await response.json();
                    alert(result.message);
                } catch (error) {
                    alert('Ошибка перезапуска: ' + error.message);
                }
            }
            
            async function loadLogs() {
                try {
                    const response = await fetch('/api/collector/logs?lines=50');
                    const result = await response.json();
                    document.getElementById('logs').innerHTML = result.logs.join('\\n');
                } catch (error) {
                    document.getElementById('logs').innerHTML = 'Ошибка загрузки логов: ' + error.message;
                }
            }
            
            // Инициализация
            connectWebSocket();
            loadLogs();
            setInterval(loadLogs, 10000); // Обновляем логи каждые 10 секунд
        </script>
    </body>
    </html>
    """

async def main():
    """Запуск API сервера"""
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=8000, 
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    print("🚀 Collector Management API запущен на http://localhost:8000")
    print("📊 Dashboard доступен по адресу: http://localhost:8000")
    
    await server.serve()

if __name__ == "__main__":
    # Настраиваем логирование
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main())