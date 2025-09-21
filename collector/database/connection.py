"""
DatabaseConnection - простой класс для подключения к PostgreSQL
"""

import asyncpg
import ssl
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """Управление подключением к PostgreSQL"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection = None
    
    async def connect(self):
        """Установка соединения с базой данных"""
        try:
            # Map sslmode from DSN to asyncpg ssl context (asyncpg doesn't honor libpq sslmode in DSN)
            ssl_ctx = None
            try:
                parsed = urlparse(self.database_url)
                query = {}
                if parsed.query:
                    for part in parsed.query.split('&'):
                        if not part:
                            continue
                        k, _, v = part.partition('=')
                        query[k] = v
                sslmode = (query.get('sslmode') or 'require').lower()
                if sslmode in ('disable', 'allow', 'prefer'):
                    ssl_ctx = False
                elif sslmode in ('require', 'verify-none'):
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    ssl_ctx = ctx
                elif sslmode in ('verify-full', 'verify-ca'):
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

            self.connection = await asyncpg.connect(self.database_url, ssl=ssl_ctx)
            logger.info("✅ Database connection established")
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            raise
    
    async def execute_script(self, sql_script: str):
        """Выполнение SQL скрипта"""
        if not self.connection:
            raise RuntimeError("Database connection not established")
        
        try:
            await self.connection.execute(sql_script)
            logger.info("✅ SQL script executed successfully")
        except Exception as e:
            logger.error(f"❌ Failed to execute SQL script: {e}")
            raise
    
    async def close(self):
        """Закрытие соединения"""
        if self.connection:
            await self.connection.close()
            logger.info("✅ Database connection closed")