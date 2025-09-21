"""
DatabaseConnection - простой класс для подключения к PostgreSQL
"""

import asyncpg
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
            self.connection = await asyncpg.connect(self.database_url)
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