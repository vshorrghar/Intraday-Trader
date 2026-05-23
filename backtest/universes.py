"""
Universe definitions for backtest framework.
Tier 1: Nifty 50 + Next 50 (our primary trading universe)
"""

# Nifty 50 — all 50 stocks with Dhan security IDs
NIFTY50 = {
    "RELIANCE": "2885", "HDFCBANK": "1333", "ICICIBANK": "4963",
    "INFY": "1594", "TCS": "11536", "BHARTIARTL": "10604",
    "SBIN": "3045", "AXISBANK": "5900", "KOTAKBANK": "1922",
    "LT": "11483", "HCLTECH": "7229", "WIPRO": "3787",
    "MARUTI": "10999", "SUNPHARMA": "3351", "TITAN": "3506",
    "ULTRACEMCO": "11532", "BAJFINANCE": "317", "TECHM": "13538",
    "ADANIENT": "25", "ADANIPORTS": "15083", "NTPC": "11630",
    "POWERGRID": "14977", "ONGC": "2475", "COALINDIA": "20374",
    "TATASTEEL": "3499", "JSWSTEEL": "11723", "HINDALCO": "1363",
    "BAJAJ-AUTO": "16669", "EICHERMOT": "910", "HEROMOTOCO": "1348",
    "M&M": "2031", "TATAMOTORS": "3456", "DRREDDY": "881",
    "CIPLA": "694", "APOLLOHOSP": "157", "NESTLEIND": "17963",
    "HINDUNILVR": "1394", "BRITANNIA": "547", "TATACONSUM": "3432",
    "ITC": "1660", "HDFCLIFE": "467", "SBILIFE": "21808",
    "BAJAJFINSV": "16675", "GRASIM": "1232", "TRENT": "1964",
    "BEL": "383", "BPCL": "526", "INDUSINDBK": "5258",
    "SHRIRAMFIN": "4306", "ASIANPAINT": "236",
}

# Nifty Next 50 — your proven sweet spot
# HFCL, BHEL, Suzlon, Adani Power all live here
NIFTY_NEXT50 = {
    "HFCL": "21951", "BHEL": "438", "SUZLON": "12018",
    "ADANIPOWER": "17388", "ADANIGREEN": "3563", "ADANIENT": "25",
    "ZOMATO": "21690", "JIOFIN": "18143", "TRENT": "1964",
    "GODREJCP": "10099", "MUTHOOTFIN": "23650", "CHOLAFIN": "685",
    "TORNTPHARM": "3518", "TORNTPOWER": "13786", "SIEMENS": "3150",
    "ABB": "13", "BOSCHLTD": "2181", "HAVELLS": "9819",
    "VOLTAS": "3718", "WHIRLPOOL": "18011", "PAGEIND": "14413",
    "MPHASIS": "4503", "COFORGE": "11543", "PERSISTENT": "18365",
    "LTTS": "18564", "OFSS": "10738", "NAUKRI": "13751",
    "INDIGO": "11195", "IRCTC": "13611", "CONCOR": "4749",
    "RECLTD": "15355", "PFC": "14299", "IRFC": "2029",
    "NHPC": "17400", "SJVN": "18883", "HUDCO": "20825",
    "RVNL": "9552", "RAILTEL": "2431", "IREDA": "20261",
    "COCHINSHIP": "21508", "BDL": "2144", "HAL": "2303",
    "MAZDOCK": "509", "GRSE": "5475", "MDL": "2132",
    "BHEL": "438", "NTPCGREEN": "27176", "CANBK": "10794",
    "UNIONBANK": "10753", "INDIANB": "14309",
}

# High beta stocks — move more than market on catalyst days
HIGH_BETA = {
    "HFCL": "21951", "SUZLON": "12018", "ADANIPOWER": "17388",
    "ADANIGREEN": "3563", "YESBANK": "11915", "IDEA": "14366",
    "RPOWER": "15259", "JPPOWER": "11763", "IREDA": "20261",
    "RVNL": "9552", "RAILTEL": "2431", "COCHINSHIP": "21508",
    "BHEL": "438", "HAL": "2303", "BDL": "2144",
}

# Tier 1 combined — primary trading universe
TIER1 = {**NIFTY50, **NIFTY_NEXT50}

# Stocks to AVOID based on our data analysis
BLACKLIST = {
    "HDFCBANK",   # 5 trades, 0 wins, -₹2,445 total
    "WIPRO",      # consistent loser in our data
}

def get_universe(name: str) -> dict:
    """Get universe by name."""
    universes = {
        "nifty50": NIFTY50,
        "next50": NIFTY_NEXT50,
        "high_beta": HIGH_BETA,
        "tier1": TIER1,
    }
    return {k: v for k, v in universes.get(name, NIFTY50).items()
            if k not in BLACKLIST}

# F&O Eligible universe — all NSE stocks with active F&O
# Source: NSE F&O permitted list
# These have guaranteed liquidity and institutional interest
FNO_ELIGIBLE = {
    # Nifty 50 (already in NIFTY50)
    "RELIANCE": "2885", "HDFCBANK": "1333", "ICICIBANK": "4963",
    "INFY": "1594", "TCS": "11536", "BHARTIARTL": "10604",
    "SBIN": "3045", "AXISBANK": "5900", "KOTAKBANK": "1922",
    "LT": "11483", "HCLTECH": "7229", "WIPRO": "3787",
    "MARUTI": "10999", "SUNPHARMA": "3351", "TITAN": "3506",
    "ULTRACEMCO": "11532", "BAJFINANCE": "317", "TECHM": "13538",
    "ADANIENT": "25", "ADANIPORTS": "15083", "NTPC": "11630",
    "POWERGRID": "14977", "ONGC": "2475", "COALINDIA": "20374",
    "TATASTEEL": "3499", "JSWSTEEL": "11723", "HINDALCO": "1363",
    "BAJAJ-AUTO": "16669", "EICHERMOT": "910", "HEROMOTOCO": "1348",
    "M&M": "2031", "TATAMOTORS": "3456", "DRREDDY": "881",
    "CIPLA": "694", "APOLLOHOSP": "157", "NESTLEIND": "17963",
    "HINDUNILVR": "1394", "BRITANNIA": "547", "TATACONSUM": "3432",
    "ITC": "1660", "HDFCLIFE": "467", "SBILIFE": "21808",
    "BAJAJFINSV": "16675", "GRASIM": "1232", "TRENT": "1964",
    "BEL": "383", "BPCL": "526", "INDUSINDBK": "5258",
    "SHRIRAMFIN": "4306", "ASIANPAINT": "236",
    # Nifty Next 50
    "HFCL": "21951", "BHEL": "438", "SUZLON": "12018",
    "ADANIPOWER": "17388", "ADANIGREEN": "3563",
    "ZOMATO": "21690", "JIOFIN": "18143",
    "GODREJCP": "10099", "MUTHOOTFIN": "23650", "CHOLAFIN": "685",
    "TORNTPHARM": "3518", "TORNTPOWER": "13786", "SIEMENS": "3150",
    "ABB": "13", "BOSCHLTD": "2181", "HAVELLS": "9819",
    "VOLTAS": "3718", "PAGEIND": "14413",
    "MPHASIS": "4503", "COFORGE": "11543", "PERSISTENT": "18365",
    "LTTS": "18564", "OFSS": "10738", "NAUKRI": "13751",
    "INDIGO": "11195", "IRCTC": "13611", "CONCOR": "4749",
    "RECLTD": "15355", "PFC": "14299", "IRFC": "2029",
    "NHPC": "17400", "SJVN": "18883", "HUDCO": "20825",
    "RVNL": "9552", "RAILTEL": "2431", "IREDA": "20261",
    "COCHINSHIP": "21508", "BDL": "2144", "HAL": "2303",
    "MAZDOCK": "509", "GRSE": "5475",
    # Quality Midcap F&O
    "BANKBARODA": "4668", "CANBK": "10794", "UNIONBANK": "10753",
    "INDIANB": "14309", "PNB": "10666", "IOB": "9348",
    "IDFCFIRSTB": "11184", "FEDERALBNK": "1023", "BANDHANBNK": "2263",
    "AUBANK": "21238", "RBLBANK": "18391",
    "GAIL": "4717", "IOC": "1624", "HINDPETRO": "1406",
    "MRPL": "2283", "CHENNPETRO": "2049",
    "NMDC": "15332", "SAIL": "2963", "NATIONALUM": "6364",
    "HINDZINC": "1424", "VEDL": "3063",
    "GODREJIND": "10925", "GODREJPROP": "17875",
    "OBEROIRLTY": "20242", "PRESTIGE": "20302", "DLF": "14732",
    "LODHA": "3220", "SOBHA": "13826",
    "DIVISLAB": "10940", "AUROPHARMA": "275", "LUPIN": "10440",
    "ALKEM": "11703", "IPCALAB": "1633", "NATCOPHARM": "3918",
    "GRANULES": "11872", "LAURUSLABS": "19234",
    "MCDOWELL-N": "4067", "UBL": "16713", "RADICO": "10990",
    "ABCAPITAL": "21614", "IIFL": "11809", "MUTHOOTFIN": "23650",
    "BAJAJHFL": "25270", "LICHSGFIN": "1997", "PNBHOUSING": "18908",
    "CANFINHOME": "583",
    "TATAPOWER": "3426", "ADANIENSOL": "10217",
    "CESC": "628", "TORNTPOWER": "13786",
    "KPITTECH": "9683", "LTIM": "17818", "MPHASIS": "4503",
    "CYIENT": "5748", "SONACOMS": "4684", "SCHAEFFLER": "1011",
    "TIINDIA": "312", "MOTHERSON": "4204", "BOSCHLTD": "2181",
    "TVSMOTOR": "8479", "BAJAJ-AUTO": "16669",
    "APOLLOTYRE": "163", "CEATLTD": "15254", "MRF": "2277",
    "DEEPAKNTR": "19943", "PIIND": "24184", "AARTIIND": "7",
    "TATACHEM": "3405", "GNFC": "1174", "COROMANDEL": "739",
    "UPL": "11287", "RALLIS": "2816",
    "VOLTAS": "3718", "BLUESTARCO": "8311", "WHIRLPOOL": "18011",
    "DIXON": "21690", "AMBER": "1185",
    "ASTRAL": "14418", "SUPREMEIND": "3363", "POLYCAB": "9590",
    "KEI": "13310", "APLAPOLLO": "25780",
    "NYKAA": "6545", "DMART": "19913", "TRENT": "1964",
    "ABFRL": "30108", "SHOPERSTOP": "11813",
    "ZEEL": "3812", "SUNTV": "13404", "PVRINOX": "13147",
    "NAZARA": "2987", "NETWORK18": "14111",
    "LICI": "9480", "ICICIGI": "21770", "ICICIPRULI": "18652",
    "GICRE": "277", "NIACL": "399",
    "MCX": "31181", "BSE": "19585", "CDSL": "21174",
    "ANGELONE": "324", "IIFLSEC": "13072",
    "IRCON": "4986", "RITES": "3761", "NBCC": "31415",
    "PSUBNKBEES": "15032",
}

def get_universe(name: str) -> dict:
    """Get universe by name."""
    universes = {
        "nifty50": NIFTY50,
        "next50": NIFTY_NEXT50,
        "high_beta": HIGH_BETA,
        "tier1": TIER1,
        "fno": FNO_ELIGIBLE,
        "nifty500": NIFTY500,
    }
    return {k: v for k, v in universes.get(name, NIFTY50).items()
            if k not in BLACKLIST}

# Nifty 500 — broader universe including quality midcaps
# Combines F&O eligible + additional liquid midcaps
NIFTY500 = {
    **FNO_ELIGIBLE,
    # Additional quality midcaps not in F&O but liquid
    "HFCL": "21951", "SUZLON": "12018", "RVNL": "9552",
    "RAILTEL": "2431", "IREDA": "20261", "COCHINSHIP": "21508",
    "GRSE": "5475", "BDL": "2144", "HAL": "2303",
    "MAZDOCK": "509", "NBCC": "31415", "RITES": "3761",
    "IRCON": "4986", "SJVN": "18883", "NHPC": "17400",
    "RECLTD": "15355", "IRFC": "2029", "PFC": "14299",
    "HUDCO": "20825", "ADANIPOWER": "17388",
    "TATAPOWER": "3426", "CESC": "628", "TORNTPOWER": "13786",
    "NTPCGREEN": "27176", "ADANIGREEN": "3563",
    "ZOMATO": "21690", "NYKAA": "6545", "DMART": "19913",
    "POLICYBZR": "6656", "PAYTM": "6705",
    "DIXON": "21690", "AMBER": "1185", "VOLTAS": "3718",
    "BLUESTARCO": "8311",
    "DEEPAKNTR": "19943", "PIIND": "24184", "AARTIIND": "7",
    "GNFC": "1174", "COROMANDEL": "739", "UPL": "11287",
    "APOLLOTYRE": "163", "CEATLTD": "15254", "MRF": "2277",
    "TVSMOTOR": "8479", "MOTHERSON": "4204",
    "KALYANKJIL": "2955", "SENCO": "17271",
    "LICI": "9480", "ICICIGI": "21770",
    "MCX": "31181", "BSE": "19585", "CDSL": "21174",
    "ANGELONE": "324",
}

# Update get_universe to include nifty500

# Stocks that consistently fail on gap days
# Based on backtest analysis 2026-05-24
GAP_STRATEGY_BLACKLIST = {
    # Oil marketing — gap up on oil prices, fade quickly
    "BPCL", "HINDPETRO", "CHENNPETRO", "IOC", "MRPL",
    # Real estate — gap but low follow-through
    "GODREJPROP", "DLF", "OBEROIRLTY",
    # High volatility but unreliable direction
    "ADANIPOWER", "ADANIGREEN", "ADANIENT",
    # Consistent losers from previous backtest
    "APLAPOLLO", "JIOFIN", "COFORGE",
}

def get_universe_filtered(name: str) -> dict:
    """Get universe with both general and strategy-specific blacklists."""
    universe = get_universe(name)
    return {k: v for k, v in universe.items()
            if k not in GAP_STRATEGY_BLACKLIST}
