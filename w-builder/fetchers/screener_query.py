"""Screener.in stock screening query fetcher."""
from __future__ import annotations
import logging, time
from dataclasses import dataclass
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
URL = "https://www.screener.in/screens/raw/"
HDRS = {"User-Agent": "Mozilla/5.0 Chrome/120.0", "Referer": "https://www.screener.in/"}

@dataclass
class ScreenResult:
    name: str
    symbol: str
    url: str
    market_cap: float | None = None
    current_price: float | None = None
    pe_ratio: float | None = None
    roce: float | None = None
    roe: float | None = None
    query_type: str = ""

QUERIES = {
    "strong_fundamentals": "Return on capital employed > 18 AND Return on equity > 15 AND Sales growth 5Years > 12 AND Profit growth 5Years > 12 AND Debt to equity < 0.5 AND Interest Coverage > 5 AND Promoter holding > 50",
    "crash_opportunity": "Return on capital employed > 18 AND Return on equity > 15 AND Sales growth 5Years > 10 AND Profit growth 5Years > 10 AND Debt to equity < 0.5 AND Price to Earning < Industry PE AND Current price < 0.9 * High price all time",
    "midcap_multibagger": "Market Capitalization > 5000 AND Market Capitalization < 50000 AND Return on capital employed > 20 AND Return on equity > 18 AND Sales growth 3Years > 15 AND Profit growth 3Years > 15 AND Debt to equity < 0.5 AND Promoter holding > 55",
}

def _pn(t):
    if not t: return None
    c = t.replace(",","").replace("%","").replace("₹","").strip()
    try: return float(c)
    except: return None

def _parse_table(html, qt):
    soup = BeautifulSoup(html, "lxml")
    tbl = soup.find("table", class_="data-table")
    if not tbl: return []
    hs = [th.get_text(strip=True).lower() for th in (tbl.find("thead") or tbl).find_all("th")]
    tb = tbl.find("tbody")
    if not tb: return []
    out = []
    for tr in tb.find_all("tr"):
        cs = tr.find_all("td")
        if len(cs) < 2: continue
        a = cs[0].find("a")
        if not a: continue
        nm = a.get_text(strip=True)
        u = a.get("href", "")
        sy = u.strip("/").split("/")[-1] if u else ""
        rd = {}
        for i in range(min(len(hs), len(cs))):
            rd[hs[i]] = cs[i].get_text(strip=True)
        out.append(ScreenResult(name=nm, symbol=sy, url="https://www.screener.in"+u if u.startswith("/") else u, market_cap=_pn(rd.get("market cap",rd.get("mcap",""))), current_price=_pn(rd.get("cmp",rd.get("current price",""))), pe_ratio=_pn(rd.get("p/e",rd.get("pe",""))), roce=_pn(rd.get("roce","")), roe=_pn(rd.get("roe","")), query_type=qt))
    return out

def run_screen_query(query, qt):
    try:
        r = requests.get(URL, params={"query": query}, headers=HDRS, timeout=30)
        r.raise_for_status()
        return _parse_table(r.text, qt)
    except Exception as e:
        logger.error("Query [%s] failed: %s", qt, e)
        return []

def run_all_screens():
    o = {}
    for qt, q in QUERIES.items():
        o[qt] = run_screen_query(q, qt)
        time.sleep(2)
    return o

def format_screen_results(ar):
    ls = []
    lb = {"strong_fundamentals": "Strong Fundamentals", "crash_opportunity": "Crash Opportunity", "midcap_multibagger": "Midcap Multibagger"}
    for qt, rs in ar.items():
        ls.append("\n" + "="*60 + "\n  " + lb.get(qt,qt) + " (" + str(len(rs)) + " stocks)\n" + "="*60)
        if not rs:
            ls.append("  No stocks matched.")
            continue
        for i, r in enumerate(rs[:20], 1):
            p = f"{r.current_price:,.0f}" if r.current_price else "N/A"
            m = f"{r.market_cap:,.0f}Cr" if r.market_cap else "N/A"
            pe = f"{r.pe_ratio:.1f}" if r.pe_ratio else "N/A"
            rc = f"{r.roce:.1f}%" if r.roce else "N/A"
            ls.append(f"  {i:2d}. {r.name} ({r.symbol}) | Price:{p} MCap:{m} PE:{pe} ROCE:{rc}")
    return "\n".join(ls)
