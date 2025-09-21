"""
Конфигурация символов для сбора данных orderbook
Фокус на анализе market maker активности

Символы отсортированы по убывающей ликвидности, начиная с SOLUSDT
Исключены самые ликвидные пары (BTCUSDT, ETHUSDT) для чистоты MM сигналов
"""

# 200 уникальных символов в порядке убывания ликвидности
SYMBOLS_200 = [
    # Tier 1: Средняя ликвидность (хорошие для анализа MM)
    'SOLUSDT', 'ADAUSDT', 'DOTUSDT', 'AVAXUSDT', 'MATICUSDT', 'LINKUSDT', 'UNIUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT',
    
    # Tier 2: Умеренная ликвидность 
    'ATOMUSDT', 'VETUSDT', 'FILUSDT', 'TRXUSDT', 'ETCUSDT', 'ICPUSDT', 'NEARUSDT', 'FTMUSDT', 'SANDUSDT', 'MANAUSDT',
    'AXSUSDT', 'GALAUSDT', 'CHZUSDT', 'APEUSDT', 'GMTUSDT', 'FLOWUSDT', 'XTZUSDT', 'EGLDUSDT', 'AAVEUSDT', 'COMPUSDT',
    
    # Tier 3: Низкая ликвидность (отличные для MM анализа)
    'MKRUSDT', 'SUSHIUSDT', 'SNXUSDT', 'YFIUSDT', 'CRVUSDT', 'BALUSDT', 'RENUSDT', 'KNCUSDT', 'BANDUSDT', 'STORJUSDT',
    'OCEANUSDT', 'CTKUSDT', 'AKROUSDT', 'REEFUSDT', 'BADGERUSDT', 'INJUSDT', 'MASKUSDT', 'NUUSDT', 'XVGUSDT', 'DENTUSDT',
    
    # Tier 4: Очень низкая ликвидность (идеальные для MM следов)
    'HOTUSDT', 'ENJUSDT', 'ZILUSDT', 'FETUSDT', 'SKLUSDT', 'GRTUSDT', 'ONEUSDT', 'HARMONUSDT', 'OMGUSDT', 'LRCUSDT',
    'RNUSDT', 'ALGOUSDT', 'ZRXUSDT', 'BATUSDT', 'IOSTUSDT', 'CELRUSDT', 'COTIUSDT', 'CHRUSDT', 'STMXUSDT', 'HBARUSDT',
    
    # Tier 5: Малоликвидные альткоины 
    'ANKRUSDT', 'NKNUSDT', 'SCUSDT', 'KEYUSDT', 'NANOUSDT', 'VITEUSDT', 'ONGUSDT', 'RLCUSDT', 'WANUSDT', 'WAXPUSDT',
    'KAVAUSDT', 'ARPAUSDT', 'CTXCUSDT', 'LSKUSDT', 'BTSUSDT', 'ARDRUSDT', 'MDTUSDT', 'STPTUSDT', 'DOCKUSDT', 'PERLUSDT',
    
    # Tier 6: Микрокапы и новые проекты
    'PUNDIXUSDT', 'NULSUSDT', 'CVPUSDT', 'SLPUSDT', 'TRBUSDT', 'SXPUSDT', 'DCRUSDT', 'RAMPUSDT', 'FISUSDT', 'OXTUSDT',
    'UTKUSDT', 'XVSUSDT', 'ALPHAUSDT', 'VTHOUSDT', 'DFUSDT', 'FIROUSDT', 'WINGUSDT', 'TLMUSDT', 'MIRUSDT', 'BARUSDT',
    
    # Tier 7: Specialized DeFi/Gaming tokens
    'FORTHUSDT', 'CAKEUSDT', 'SPARTAUSDT', 'UFTUSDT', 'AUTOUSDT', 'WINUSDT', 'ELFUSDT', 'EZUSDT', 'GTOUSDT', 'TORNUSDT',
    'KEEPUSDT', 'ERNUSDT', 'KLAYUSDT', 'STRAXUSDT', 'UNFIUSDT', 'RADUSDT', 'BONDUSDT', 'RAREUSDT', 'ADXUSDT', 'AUCTIONUSDT',
    
    # Tier 8: Newer/smaller projects (excellent MM signal)
    'DARUSDT', 'RGTUSDT', 'MOVRUSDT', 'CITYUSDT', 'ENSUSDT', 'MBOXUSDT', 'REQUSDT', 'HIGHUSDT', 'PEOPLEUSDT', 'OOKIUSDT',
    'SPELLUSDT', 'USTUSDT', 'JASMYUSDT', 'AMPUSDT', 'PYRUSDT', 'PORTOUSDT', 'CLVUSDT', 'SANTOSUSDT', 'MCUSDT', 'ANYUSDT',
    
    # Tier 9: Low-cap altcoins (pure MM tracking territory)
    'FLUXUSDT', 'FXSUSDT', 'ACHUSDT', 'IMXUSDT', 'JUVEUSDT', 'PSIGUSDT', 'BETAUSDT', 'GLMRUSDT', 'LOKAUSDT', 'SCRTUSDT',
    'APIUSDT', 'BTTCUSDT', 'WRXUSDT', 'LPTUSDT', 'TVKUSDT', 'ALPINEUSDT', 'LAZIOUSDT', 'MULTIUSDT', 'FIDAUSDT', 'EPSUSDT',
    
    # Tier 10: Ultra low-cap (maximum MM signal clarity)
    'RAYUSDT', 'LQTYUSDT', 'POLYXUSDT', 'IDEXUSDT', 'DIAUSDT', 'TRIBEUSDT', 'PONDUSDT', 'OPUSDT', 'ARBUSDT', 'LDOUSDT',
    'CFXUSDT', 'STGUSDT', 'AMBUSDT', 'GASUSDT', 'GLMUSDT', 'PROMUSDT', 'QNTUSDT', 'POWRUSDT', 'VGXUSDT', 'SUPERUSDT',
    'ILVUSDT', 'YGGUSDT', 'FTTUSDT', 'LEVERUSDT', 'PHBUSDT', 'VIDTUSDT', 'OGUSDT', 'ASRUSDT', 'FARMUSDT', 'BELUSDT'
]

# Структура ликвидности для анализа MM активности
LIQUIDITY_TIERS = {
    'tier1_medium': SYMBOLS_200[0:10],    # Средняя ликвидность
    'tier2_moderate': SYMBOLS_200[10:30], # Умеренная ликвидность  
    'tier3_low': SYMBOLS_200[30:50],      # Низкая ликвидность
    'tier4_very_low': SYMBOLS_200[50:70], # Очень низкая ликвидность
    'tier5_micro': SYMBOLS_200[70:90],    # Малоликвидные альткоины
    'tier6_nano': SYMBOLS_200[90:110],    # Микрокапы
    'tier7_defi': SYMBOLS_200[110:130],   # DeFi/Gaming токены
    'tier8_newer': SYMBOLS_200[130:150],  # Новые проекты
    'tier9_lowcap': SYMBOLS_200[150:170], # Low-cap альткоины
    'tier10_ultra': SYMBOLS_200[170:200]  # Ultra low-cap
}

def validate_symbols():
    """Валидация списка символов"""
    # Проверка уникальности
    unique_symbols = set(SYMBOLS_200)
    assert len(unique_symbols) == len(SYMBOLS_200), f"Duplicate symbols found"
    
    # Проверка количества
    assert len(SYMBOLS_200) == 200, f"Expected 200 symbols, got {len(SYMBOLS_200)}"
    
    # Проверка формата
    for symbol in SYMBOLS_200:
        assert symbol.endswith('USDT'), f"Invalid symbol format: {symbol}"
        assert symbol.isupper(), f"Symbol must be uppercase: {symbol}"
    
    # Проверка покрытия тирами
    tier_symbols = []
    for tier_symbols_list in LIQUIDITY_TIERS.values():
        tier_symbols.extend(tier_symbols_list)
    
    assert set(tier_symbols) == set(SYMBOLS_200), "Tier coverage mismatch"
    
    print(f"✅ Validation passed: {len(SYMBOLS_200)} unique symbols")
    print(f"📊 Liquidity tiers: {len(LIQUIDITY_TIERS)} tiers")
    return True

def get_symbols_by_tier(tier_name):
    """Получить символы по уровню ликвидности"""
    return LIQUIDITY_TIERS.get(tier_name, [])

def get_mm_analysis_priority():
    """Получить символы в порядке приоритета для MM анализа"""
    # Лучшие для MM анализа - меньше ликвидность, чище сигнал
    priority_order = [
        'tier10_ultra',   # Самые чистые MM сигналы
        'tier9_lowcap',   # Очень хорошие для анализа  
        'tier8_newer',    # Хорошие новые проекты
        'tier7_defi',     # DeFi токены
        'tier6_nano',     # Микрокапы
        'tier5_micro',    # Малоликвидные
        'tier4_very_low', # Очень низкая ликвидность
        'tier3_low',      # Низкая ликвидность
        'tier2_moderate', # Умеренная ликвидность
        'tier1_medium'    # Средняя ликвидность
    ]
    
    result = []
    for tier in priority_order:
        result.extend(LIQUIDITY_TIERS[tier])
    
    return result

if __name__ == "__main__":
    validate_symbols()
    
    print(f"\n🎯 Market Maker Analysis Focus:")
    print(f"Starting symbol: {SYMBOLS_200[0]}")
    print(f"Ultra low-cap (best MM signals): {len(LIQUIDITY_TIERS['tier10_ultra'])} symbols")
    print(f"Low-cap altcoins: {len(LIQUIDITY_TIERS['tier9_lowcap'])} symbols")
    print(f"Total symbols for collection: {len(SYMBOLS_200)}")