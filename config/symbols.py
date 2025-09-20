# 200 Most Active Trading Pairs for OrderBook Collection
# Updated: September 2025
# Source: Binance Futures volume analysis

TOP_200_SYMBOLS = [
    # Tier 1: Major cryptocurrencies (Top 20 by volume)
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOGEUSDT", "TRXUSDT", "MATICUSDT", "DOTUSDT",
    "AVAXUSDT", "LTCUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT",
    "ETCUSDT", "XLMUSDT", "BCHUSDT", "FILUSDT", "ICPUSDT",
    
    # Tier 2: DeFi and Ecosystem tokens (20)
    "AAVEUSDT", "COMPUSDT", "MKRUSDT", "SUSHIUSDT", "CRVUSDT",
    "YFIUSDT", "1INCHUSDT", "ALPHAUSDT", "SNXUSDT", "BALAUSDT",
    "RENUSDT", "KNCUSDT", "BANDUSDT", "STORJUSDT", "OCEANUSDT",
    "INJUSDT", "DYDXUSDT", "ENSUSDT", "AXSUSDT", "MANAUSDT",
    
    # Tier 3: Layer 1 & Layer 2 blockchains (25)
    "NEARUSDT", "FTMUSDT", "ALGOUSDT", "EOSUSDT", "XTZUSDT",
    "VETUSDT", "ICXUSDT", "ZILUSDT", "ONTUSDT", "QTUMUSDT",
    "WAVESUSDT", "KSMUSDT", "FLOWUSDT", "HBARUSDT", "EGLDUSDT",
    "RUNEUSDT", "LUNAUSDT", "USTUSDT", "MIRRUSDT", "ANCUSDT",
    "SCRTUSDT", "CTSIUSDT", "RLCUSDT", "COTIUSDT", "OCEANUSDT",
    
    # Tier 4: Gaming & Metaverse (15)
    "SANDUSDT", "ENJUSDT", "CHRUSDT", "ALICEUSDT", "TLMUSDT",
    "DEGOUSDT", "YGGUSDT", "GALUSDT", "BARUSDT", "ATMUSDT",
    "PSGUSDT", "JUVUSDT", "ASRUSDT", "OGUSDT", "ACMUSDT",
    
    # Tier 5: Meme & Social tokens (15) 
    "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT", "WIFUSDT",
    "DOGEUSDT", "ELON1000USDT", "BABYDOGEUSDT", "SAITAMAUSDT", "NFTUSDT",
    "APEUSDT", "LOOKSUSDT", "X2Y2USDT", "SUDOUSDT", "BLZUSDT",
    
    # Tier 6: Infrastructure & Oracle (20)
    "CHZUSDT", "HOTUSDT", "ZILUSDT", "BNBUSDT", "CAKEUSDT",
    "BAKEUSDT", "BURGERUSDT", "SXPUSDT", "COSUSDT", "KEYUSDT",
    "HARDUSDT", "STMXUSDT", "DENTUSDT", "CELRUSDT", "OGNUSDT",
    "NKNUSDT", "SCUSDT", "ONEUSDT", "FTMUSDT", "CKBUSDT",
    
    # Tier 7: AI & Data (10)
    "FETUSDT", "AGIXUSDT", "OCEANUSDT", "NMRUSDT", "CTXCUSDT",
    "PHBUSDT", "AIUSDT", "ARKMUSDT", "CVCUSDT", "DNTUSDT",
    
    # Tier 8: Privacy & Security (10)
    "XMRUSDT", "ZECUSDT", "DASHUSDT", "SCRTUSDT", "BEAMUSDT",
    "GRTTUSDT", "TORNUSDT", "PERPUSDT", "BADGERUSDT", "KEEPUSDT",
    
    # Tier 9: Cross-chain & Bridges (10)
    "CELUSDT", "KAVAUSDT", "HARDUSDT", "ANYUSDT", "SYNUSDT",
    "RENBCUSDT", "BTCBUSDT", "ETHWUSDT", "STETHUSDT", "WBTCUSDT",
    
    # Tier 10: Emerging & New tokens (35)
    "OPUSDT", "ARBUSDT", "GMXUSDT", "GALAUSDT", "APTUSDT",
    "SUIUSDT", "LDOUSDT", "RDNTUSDT", "STGUSDT", "SPELLUSDT",
    "IDUSDT", "CFXUSDT", "EDUUSDT", "IDEXUSDT", "UMAUSDT",
    "RADUSDT", "KEYUSDT", "COMBOUSDT", "MAVUSDT", "PENDLEUSDT",
    "ARKMUSDT", "WLDUSDT", "SEIUSDT", "CYBERUSDT", "ARKUSDT",
    "IQUSDT", "NTRNUSDT", "TIAUSDT", "BEAMXUSDT", "PIVXUSDT",
    "VICUSDT", "BLURUSDT", "VANRYUSDT", "ACEUSDT", "NFPUSDT",
    
    # Tier 11: Additional volume pairs (20)
    "1000SATSUSDT", "ORDIUSDT", "ETHFIUSDT", "BOMEUSDT", "REZUSDT",
    "NOTUSDT", "IOUSDT", "ZKUSDT", "LISTAUSDT", "ZROUSDT",
    "GUSDT", "BANANAUSDT", "RENDERUSDT", "TONUSDT", "DOGSUSDT",
    "POPCATUSDT", "SUNUSDT", "CATUSDT", "XUSDT", "HMSTRUSDT"
]

# Символы сгруппированы по приоритетам для поэтапного развертывания
PRIORITY_GROUPS = {
    "critical": TOP_200_SYMBOLS[:20],      # Запускаем первыми
    "high": TOP_200_SYMBOLS[20:60],        # Добавляем через час
    "medium": TOP_200_SYMBOLS[60:120],     # Добавляем через день
    "low": TOP_200_SYMBOLS[120:200]        # Добавляем через неделю
}

# Проверка уникальности символов
assert len(TOP_200_SYMBOLS) == len(set(TOP_200_SYMBOLS)), "Duplicate symbols found!"
assert len(TOP_200_SYMBOLS) == 200, f"Expected 200 symbols, got {len(TOP_200_SYMBOLS)}"

print(f"✅ Configured {len(TOP_200_SYMBOLS)} unique trading pairs")
print(f"📊 Priority groups: {[len(group) for group in PRIORITY_GROUPS.values()]}")