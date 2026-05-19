"""
Sector classification for swing universe.
Hardcoded for Phase 1. Automated via NSE API in Week 3.
"""

# TODO Week 3: Replace flat sector bonus with full correlation matrix
# TODO Week 3: Automate sector classification from NSE index constituents

SECTOR_MAP = {
    # IT
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT",
    "TECHM": "IT", "COFORGE": "IT_MID", "PERSISTENT": "IT_MID",
    "MPHASIS": "IT_MID", "LTIM": "IT_MID",
    # Private Banks
    "HDFCBANK": "PRIVATE_BANK", "ICICIBANK": "PRIVATE_BANK",
    "AXISBANK": "PRIVATE_BANK", "KOTAKBANK": "PRIVATE_BANK",
    "INDUSINDBK": "PRIVATE_BANK",
    # PSU Banks
    "SBIN": "PSU_BANK", "PNB": "PSU_BANK",
    "BANKBARODA": "PSU_BANK", "CANBK": "PSU_BANK",
    # NBFC
    "BAJFINANCE": "NBFC", "BAJAJFINSV": "NBFC",
    "CHOLAFIN": "NBFC", "MUTHOOTFIN": "NBFC",
    # Pharma + Healthcare
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA",
    "CIPLA": "PHARMA", "DIVISLAB": "PHARMA",
    "TORNTPHARM": "PHARMA", "LUPIN": "PHARMA",
    "BIOCON": "PHARMA", "AUROPHARMA": "PHARMA",
    "APOLLOHOSP": "HEALTHCARE", "FORTIS": "HEALTHCARE",
    "MAXHEALTH": "HEALTHCARE",
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG",
    "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "DABUR": "FMCG", "MARICO": "FMCG",
    "COLPAL": "FMCG", "TATACONSUM": "FMCG",
    "GODREJCP": "FMCG",
    # Metals
    "TATASTEEL": "METAL_FERROUS", "JSWSTEEL": "METAL_FERROUS",
    "SAIL": "METAL_FERROUS", "JINDALSTEL": "METAL_FERROUS",
    "HINDALCO": "METAL_NON_FERROUS", "VEDL": "METAL_NON_FERROUS",
    "NATIONALUM": "METAL_NON_FERROUS",
    "COALINDIA": "MINING",
    # Auto
    "MARUTI": "AUTO_4W", "TATAMOTORS": "AUTO_4W",
    "M&M": "AUTO_4W", "EICHERMOT": "AUTO_4W",
    "BAJAJ-AUTO": "AUTO_2W", "HEROMOTOCO": "AUTO_2W",
    "TVSMOTOR": "AUTO_2W",
    # Cement
    "ULTRACEMCO": "CEMENT", "GRASIM": "CEMENT",
    "SHREECEM": "CEMENT", "AMBUJACEM": "CEMENT",
    # Power
    "NTPC": "POWER", "POWERGRID": "POWER",
    "TATAPOWER": "POWER", "ADANIPOWER": "POWER",
    # Oil & Gas
    "RELIANCE": "OIL_GAS", "ONGC": "OIL_GAS",
    "BPCL": "OIL_GAS", "IOC": "OIL_GAS", "GAIL": "OIL_GAS",
    # Telecom
    "BHARTIARTL": "TELECOM",
    # Consumer Durables
    "TITAN": "CONSUMER_DURABLE", "ASIANPAINT": "CONSUMER_DURABLE",
    "BERGEPAINT": "CONSUMER_DURABLE", "HAVELLS": "CONSUMER_DURABLE",
    "VOLTAS": "CONSUMER_DURABLE",
    # Insurance
    "SBILIFE": "INSURANCE", "HDFCLIFE": "INSURANCE",
    "ICICIPRULI": "INSURANCE",
    # Infra / Capital Goods
    "LT": "INFRA", "ADANIPORTS": "INFRA",
    "SIEMENS": "CAPITAL_GOODS", "ABB": "CAPITAL_GOODS",
    "HAL": "DEFENCE",
}

# Defensive sectors for scanner Signal 4 bonus
DEFENSIVE_SECTORS = {"PHARMA", "FMCG", "HEALTHCARE", "CONSUMER_DURABLE"}
