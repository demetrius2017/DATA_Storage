"""
🎯 КОНФИГУРАЦИЯ СИМВОЛОВ ДЛЯ MASS MARKET DATA COLLECTION
=====================================================

Полный список из 200+ торговых пар Binance Futures
Разделённые по категориям для эффективного шардирования
"""

# Топ-20 по объёму (требуют отдельные потоки)
TOP_VOLUME_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'DOGEUSDT', 'ADAUSDT', 'TRXUSDT', 'AVAXUSDT', 'LINKUSDT',
    'DOTUSDT', 'TONUSDT', 'MATICUSDT', 'LTCUSDT', 'NEARUSDT',
    'UNIUSDT', 'ATOMUSDT', 'XLMUSDT', 'FILUSDT', 'ETCUSDT'
]

# Стабильные altcoins (средний объём)
STABLE_ALTCOINS = [
    'BCHUSDT', 'VETUSDT', 'ICPUSDT', 'APTUSDT', 'ALGOUSDT',
    'SHIBUSDT', 'HBARUSDT', 'SANDUSDT', 'MANAUSDT', 'AAVEUSDT',
    'FTMUSDT', 'EOSUSDT', 'THETAUSDT', 'AXSUSDT', 'CHZUSDT',
    'FLOWUSDT', 'KLAYUSDT', 'EGLDUSDT', 'COMPUSDT', 'SNXUSDT',
    'MKRUSDT', 'ZILUSDT', 'CRVUSDT', 'YFIUSDT', 'BANDUSDT',
    'SRMUSDT', 'OCEANUSDT', 'KNCUSDT', 'BTCDOMUSDT', 'DEFIUSDT'
]

# DeFi токены
DEFI_SYMBOLS = [
    'SUSHIUSDT', 'CAKEUSDT', 'PANCAKEUSDT', '1INCHUSDT', 'LUNAUSDT',
    'ALPHAUSDT', 'BALUSDT', 'ZENUSDT', 'AUDIOUSDT', 'CTSIUSDT',
    'DUSKUSDT', 'STORJUSDT', 'BZRXUSDT', 'KMDUSDT', 'NMRUSDT',
    'RSRUSDT', 'TRBUSDT', 'TRUUSDT', 'DEXEUSDT', 'DFUSDT',
    'LITUSDT', 'MATHUSDT', 'BNXUSDT', 'RAMPUSDT', 'XVSUSDT',
    'ALPHAUSDT', 'FISUSDT', 'OXTUSDT', 'TLMUSDT', 'BETAUSDT'
]

# Gaming & NFT
GAMING_NFT_SYMBOLS = [
    'ENJUSDT', 'WAXPUSDT', 'SLPUSDT', 'GALAUSDT', 'CHRUSDT',
    'PUNDIXUSDT', 'ALICEUSDT', 'SUPERUSDT', 'ILBUSDT', 'YGGUSDT',
    'STARUSDT', 'DEGOUSDT', 'LPTUSDT', 'PSGUSDT', 'CITYUSDT',
    'ASRUSDT', 'ATONUSDT', 'OYUSDT', 'IBMUSDT', 'SUSUSUSDT',
    'ACMUSDT', 'JUVUSDT', 'BARUSDT', 'ATLETICOOFANUSDT', 'NOVUSDT',
    'MINAUSDT', 'RAYUSDT', 'FARMUSDT', 'PERPUSDT', 'FTTUSDT'
]

# Layer 1 & Infrastructure
LAYER1_SYMBOLS = [
    'ONEUSDT', 'ZILUSDT', 'IOTAUSDT', 'ONTUSDT', 'QTUMUSDT',
    'NULSUSDT', 'RVNUSDT', 'ZENUSDT', 'WAVESUSDT', 'KSMUSDT',
    'LDOUSDT', 'CFXUSDT', 'CKBUSDT', 'STPTUSDT', 'FXSUSDT',
    'DARUSDT', 'RADUSDT', 'VIDTUSDT', 'FIDAUSDT', 'FTXTT',
    'AGLDUSDT', 'RADUSDT', 'BADGERUSDT', 'FISUSDT', 'TORNUSDT',
    'ACHUSDT', 'CELOUSDT', 'REEFUSDT', 'KLAYUSDT', 'ANKRUSDT'
]

# Meme & Community
MEME_SYMBOLS = [
    'PEPEUSDT', 'FLOKIUSDT', 'BONKUSDT', 'BOMEUSDT', 'WIFUSDT',
    'MEMEUSDT', 'DOGSUSDT', 'NOTUSDT', '1000SATSUSDT', 'ORDIUSDT',
    'RATSUSDT', 'MYUSDT', 'PEOPLEUSDT', 'SPELLUSDT', 'JASMYUSDT',
    'HOOKUSDT', 'MAGICUSDT', 'HIGHUSDT', 'ASRUSDT', 'PHBUSDT',
    'GASUSDT', 'GLMRUSDT', 'LQTYUSDT', 'IDUSDT', 'ARBUSDT',
    'OPUSDT', 'MAVUSDT', 'PENDLEUSDT', 'ARKMUSDT', 'WLDUSDT'
]

# Emerging & New
EMERGING_SYMBOLS = [
    'SUIUSDT', 'SEIUSDT', 'CYBERUSDT', 'ARKUSDT', 'IQUSDT',
    'NTRNUSDT', 'TIAUSDT', 'BEAMXUSDT', 'PIVXUSDT', 'VICUSDT',
    'BLURUSDT', 'VANRYUSDT', 'AEURUSDT', 'JOEUSDT', 'ACEUSDT',
    'NFPUSDT', 'BNTUSDT', 'AIUSDT', 'XAIUSDT', 'MANTAUSDT',
    'ALTUSDT', 'PYTHUSDT', 'RONINUSDT', 'DYMUSDT', 'PIXELUSDT',
    'STRKUSDT', 'PORTALUSDT', 'PDAUSDT', 'AXLUSDT', 'METISUSDT'
]

# Все символы объединённые
ALL_SYMBOLS = (
    TOP_VOLUME_SYMBOLS + 
    STABLE_ALTCOINS + 
    DEFI_SYMBOLS + 
    GAMING_NFT_SYMBOLS + 
    LAYER1_SYMBOLS + 
    MEME_SYMBOLS + 
    EMERGING_SYMBOLS
)

# Конфигурация шардирования WebSocket потоков
SHARDING_CONFIG = {
    # Высокочастотные потоки для топ-символов  
    'high_frequency': {
        'symbols': TOP_VOLUME_SYMBOLS[:10],  # Топ-10
        'streams': ['bookTicker', 'aggTrade', 'depth5@100ms'],
        'max_symbols_per_stream': 5
    },
    
    # Средние потоки для стабильных altcoins
    'medium_frequency': {
        'symbols': TOP_VOLUME_SYMBOLS[10:] + STABLE_ALTCOINS,
        'streams': ['bookTicker', 'aggTrade'],
        'max_symbols_per_stream': 20
    },
    
    # Низкочастотные потоки для остальных
    'low_frequency': {
        'symbols': DEFI_SYMBOLS + GAMING_NFT_SYMBOLS + LAYER1_SYMBOLS + MEME_SYMBOLS + EMERGING_SYMBOLS,
        'streams': ['bookTicker'],
        'max_symbols_per_stream': 50
    }
}

# Приоритеты для depth данных (только для топ-символов)
DEPTH_PRIORITY_SYMBOLS = TOP_VOLUME_SYMBOLS[:15]

# Конфигурация батчей для PostgreSQL
BATCH_CONFIG = {
    'book_ticker': {
        'batch_size': 1000,
        'flush_interval': 5  # секунд
    },
    'trades': {
        'batch_size': 500,
        'flush_interval': 3
    },
    'depth_events': {
        'batch_size': 100,
        'flush_interval': 2
    }
}

# Rate limiting конфигурация
RATE_LIMITS = {
    'connections_per_stream': 5,  # Максимум подключений на поток
    'requests_per_minute': 1200,  # Binance limit
    'reconnect_delay': [1, 2, 5, 10, 30]  # Exponential backoff
}

def get_symbol_shards():
    """Возвращает сконфигурированные шарды символов для WebSocket потоков"""
    shards = []
    
    # High frequency shards
    hf_config = SHARDING_CONFIG['high_frequency']
    symbols = hf_config['symbols']
    chunk_size = hf_config['max_symbols_per_stream']
    
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        for stream_type in hf_config['streams']:
            shards.append({
                'symbols': chunk,
                'stream_type': stream_type,
                'priority': 'high',
                'batch_config': BATCH_CONFIG.get(stream_type.split('@')[0], BATCH_CONFIG['book_ticker'])
            })
    
    # Medium frequency shards
    mf_config = SHARDING_CONFIG['medium_frequency']
    symbols = mf_config['symbols']
    chunk_size = mf_config['max_symbols_per_stream']
    
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        for stream_type in mf_config['streams']:
            shards.append({
                'symbols': chunk,
                'stream_type': stream_type,
                'priority': 'medium',
                'batch_config': BATCH_CONFIG.get(stream_type.split('@')[0], BATCH_CONFIG['book_ticker'])
            })
    
    # Low frequency shards
    lf_config = SHARDING_CONFIG['low_frequency']
    symbols = lf_config['symbols']
    chunk_size = lf_config['max_symbols_per_stream']
    
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        for stream_type in lf_config['streams']:
            shards.append({
                'symbols': chunk,
                'stream_type': stream_type,
                'priority': 'low',
                'batch_config': BATCH_CONFIG.get(stream_type.split('@')[0], BATCH_CONFIG['book_ticker'])
            })
    
    return shards

def get_stats():
    """Возвращает статистику по символам и конфигурации"""
    shards = get_symbol_shards()
    
    return {
        'total_symbols': len(ALL_SYMBOLS),
        'total_shards': len(shards),
        'high_priority_symbols': len(TOP_VOLUME_SYMBOLS),
        'depth_enabled_symbols': len(DEPTH_PRIORITY_SYMBOLS),
        'shards_by_priority': {
            'high': len([s for s in shards if s['priority'] == 'high']),
            'medium': len([s for s in shards if s['priority'] == 'medium']),
            'low': len([s for s in shards if s['priority'] == 'low'])
        },
        'streams_breakdown': {
            stream: len([s for s in shards if stream in s['stream_type']])
            for stream in ['bookTicker', 'aggTrade', 'depth']
        }
    }

if __name__ == '__main__':
    print("🎯 MARKET DATA COLLECTION - SYMBOL CONFIGURATION")
    print("=" * 60)
    
    stats = get_stats()
    print(f"📊 Всего символов: {stats['total_symbols']}")
    print(f"🎯 Всего шардов: {stats['total_shards']}")
    print(f"⭐ Высокий приоритет: {stats['high_priority_symbols']}")
    print(f"🧊 Depth enabled: {stats['depth_enabled_symbols']}")
    print()
    
    print("📈 Распределение по приоритетам:")
    for priority, count in stats['shards_by_priority'].items():
        print(f"   {priority}: {count} шардов")
    print()
    
    print("📡 Распределение по типам потоков:")
    for stream, count in stats['streams_breakdown'].items():
        print(f"   {stream}: {count} шардов")