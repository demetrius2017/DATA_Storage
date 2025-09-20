"""
Настройки и конфигурация системы сбора данных.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional


DEFAULT_CONFIG = {
    "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "websocket": {
        "url": "wss://fstream.binance.com/ws/",
        "testnet_url": "wss://stream.binancefuture.com/ws/",
        "reconnect_interval": 5,
        "ping_interval": 20,
        "max_reconnects": 100
    },
    "api": {
        "use_testnet": True,  # По умолчанию используем testnet для безопасности
        "base_url": "https://fapi.binance.com",
        "testnet_base_url": "https://testnet.binancefuture.com"
    },
    "storage": {
        "base_dir": "./data/binance_orderbook",  # Относительный путь
        "compression": "gzip",
        "rotation_hours": 24,
        "backup_enabled": True
    },
    "monitoring": {
        "web_port": 8080,
        "metrics_interval": 60,
        "health_check_interval": 30
    }
}


def load_env_file(env_path: str = ".env") -> None:
    """
    Загрузка переменных окружения из .env файла.
    
    Args:
        env_path: Путь к .env файлу
    """
    env_file = Path(env_path)
    if not env_file.exists():
        return
        
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Удаление кавычек
                value = value.strip('"\'')
                os.environ[key] = value


def get_api_credentials(use_testnet: bool = True) -> Dict[str, str]:
    """
    Получение API ключей из переменных окружения.
    
    Args:
        use_testnet: Использовать testnet ключи
        
    Returns:
        Словарь с API ключами
    """
    if use_testnet:
        return {
            "api_key": os.getenv("BINANCE_TESTNET_API_KEY", ""),
            "secret_key": os.getenv("BINANCE_TESTNET_SECRET", ""),
            "base_url": "https://testnet.binancefuture.com",
            "ws_url": "wss://stream.binancefuture.com/ws/"
        }
    else:
        return {
            "api_key": os.getenv("BINANCE_API_KEY", ""),
            "secret_key": os.getenv("BINANCE_SECRET_KEY", ""),
            "base_url": "https://fapi.binance.com",
            "ws_url": "wss://fstream.binance.com/ws/"
        }


def get_tardis_api_key() -> str:
    """
    Получение API ключа Tardis для исторических данных.
    
    Returns:
        API ключ Tardis
    """
    return os.getenv("TARDIS_API_KEY", "")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Загрузка конфигурации из файла или использование значений по умолчанию.
    
    Args:
        config_path: Путь к файлу конфигурации
        
    Returns:
        Словарь с настройками
    """
    logger = logging.getLogger(__name__)
    
    # Загрузка переменных окружения
    load_env_file()
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {config_path}")
            
            # Объединение с настройками по умолчанию
            result = DEFAULT_CONFIG.copy()
            result.update(config)
            
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            result = DEFAULT_CONFIG.copy()
    else:
        result = DEFAULT_CONFIG.copy()
    
    # Добавление API ключей
    use_testnet = result.get("api", {}).get("use_testnet", True)
    result["api_credentials"] = get_api_credentials(use_testnet)
    result["tardis_api_key"] = get_tardis_api_key()
    
    logger.info(f"Using {'testnet' if use_testnet else 'production'} API")
    return result


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Сохранение конфигурации в файл.
    
    Args:
        config: Словарь с настройками
        config_path: Путь для сохранения
    """
    logger = logging.getLogger(__name__)
    
    try:
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Config saved to {config_path}")
        
    except Exception as e:
        logger.error(f"Failed to save config to {config_path}: {e}")
        raise