"""Screener.in comprehensive stock fundamentals fetcher.

Fetches 30+ fundamental metrics for a stock from Screener.in public page:
Valuation, Profitability, Growth, Financial Health, Ownership, Technical.
Implements rate limiting (1 req/sec) and daily caching.
"""
from __future__ import annotations
import json, logging, os, re, time
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup
from fetchers.models import StockFundamentals

logger = logging.getLogger(__name__)
SCREENER_URL = "https://www.screener.in/company/{symbol}/"
SCREENER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
REQUEST_TIMEOUT = 30
_last_request_time: float = 0.0
IST = timezone(timedelta(hours=5, minutes=30))
CACHE_FILE = "cache/fundamentals.json"


def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_request_time = time.time()


def _pn(text):
    """Parse numeric from Screener text like '1,234.56 Cr.' or '12.5%'."""
    if not text:
        return None
    c = text.replace(",", "").replace("₹", "").replace("%", "")
    c = c.replace("Cr.", "").replace("Cr", "").strip()
    try:
        return float(c)
    except (ValueError, TypeError):
        return None


def _extract(soup, label):
    """Extract a metric by label from Screener's name-value pairs."""
    for li in soup.find_all("li", class_="flex"):
        ns = li.find("span", class_="name")
        vs = li.find("span", class_="number")
        if ns and vs and label.lower() in ns.get_text(strip=True).lower():
            return _pn(vs.get_text(strip=True))
    pat = re.compile(re.escape(label) + r"[:\s]*([0-9,.\-]+)", re.IGNORECASE)
    m = pat.search(soup.get_text())
    return _pn(m.group(1)) if m else None


def _extract_growth(soup, section_label, period_label):
    """Extract growth from Screener's compounded growth tables.
    
    Tables have structure:
    Row 0: "Compounded Sales Growth" (header, single cell)
    Row 1: "10 Years:" | "5%"
    Row 2: "5 Years:" | "9%"
    Row 3: "3 Years:" | "12%"
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        # Check if first row matches the section
        first_text = rows[0].get_text(strip=True).lower()
        if section_label.lower() not in first_text:
            continue
        # Search remaining rows for the period
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) >= 2:
                lbl = cells[0].get_text(strip=True).lower()
                if period_label.lower() in lbl:
                    return _pn(cells[1].get_text(strip=True))
    return None


def _extract_shareholding(soup, holder_type):
    """Extract shareholding % from the shareholding pattern section."""
    sh_section = soup.find("section", id="shareholding")
    search_in = sh_section if sh_section else soup
    for table in search_in.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                row_label = cells[0].get_text(strip=True).lower()
                if holder_type.lower() in row_label:
                    # Last cell = most recent quarter
                    return _pn(cells[-1].get_text(strip=True))
    return None


def fetch_fundamentals(symbol: str) -> StockFundamentals:
    """Fetch comprehensive fundamentals from Screener.in.

    Extracts 30+ metrics: valuation, profitability, growth, financial health,
    ownership, and technical/price data. Rate limited to 1 req/sec.
    """
    _rate_limit()
    url = SCREENER_URL.format(symbol=symbol)
    try:
        logger.info("Fetching fundamentals for %s", symbol)
        resp = requests.get(url, headers=SCREENER_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Valuation
        pe = _extract(soup, "Stock P/E")
        pb = _extract(soup, "Price to book")
        mcap = _extract(soup, "Market Cap")
        bv = _extract(soup, "Book Value")
        dy = _extract(soup, "Dividend Yield")
        ev_ebitda = _extract(soup, "EV / EBITDA") or _extract(soup, "EV/EBITDA")
        peg = _extract(soup, "PEG Ratio")
        industry_pe = _extract(soup, "Industry PE")
        eps = _extract(soup, "EPS")

        # Profitability
        roce = _extract(soup, "ROCE")
        roe = _extract(soup, "ROE")
        opm = _extract(soup, "OPM") or _extract(soup, "Operating Margin")
        npm = _extract(soup, "Net Profit Margin") or _extract(soup, "NPM")

        # Growth (from compounded growth tables)
        sg3 = _extract_growth(soup, "compounded sales growth", "3 years")
        sg5 = _extract_growth(soup, "compounded sales growth", "5 years")
        pg3 = _extract_growth(soup, "compounded profit growth", "3 years")
        pg5 = _extract_growth(soup, "compounded profit growth", "5 years")

        # Financial Health
        de = _extract(soup, "Debt to equity") or _extract(soup, "Debt / Equity")
        ic = _extract(soup, "Interest Coverage")
        cr = _extract(soup, "Current Ratio")

        # Ownership
        promoter = _extract(soup, "Promoter Holding") or _extract_shareholding(soup, "promoter")
        pledge = _extract(soup, "Pledged") or _extract_shareholding(soup, "pledge")
        fii = _extract_shareholding(soup, "FII") or _extract_shareholding(soup, "foreign")
        dii = _extract_shareholding(soup, "DII") or _extract_shareholding(soup, "mutual fund")

        # Technical / Price
        h52 = _extract(soup, "High / Low")  # Usually "High / Low" shows 52w
        l52 = None
        cmp = _extract(soup, "Current Price")
        ath = _extract(soup, "All Time High") or _extract(soup, "High price")

        # Parse "52 Week High / Low" which Screener shows as "1234 / 567"
        for li in soup.find_all("li", class_="flex"):
            ns = li.find("span", class_="name")
            vs = li.find("span", class_="number")
            if ns and vs and "high" in ns.get_text(strip=True).lower() and "low" in ns.get_text(strip=True).lower():
                txt = vs.get_text(strip=True)
                parts = txt.split("/")
                if len(parts) == 2:
                    h52 = _pn(parts[0])
                    l52 = _pn(parts[1])

        # Derived
        pct_52h = ((cmp - h52) / h52 * 100) if cmp and h52 and h52 > 0 else None
        pct_ath = ((cmp - ath) / ath * 100) if cmp and ath and ath > 0 else None

        f = StockFundamentals(
            symbol=symbol,
            pe_ratio=pe, pb_ratio=pb, market_cap=mcap, book_value=bv,
            dividend_yield=dy, ev_to_ebitda=ev_ebitda, peg_ratio=peg,
            roce=roce, roe=roe, operating_margin=opm, net_profit_margin=npm,
            sales_growth_3y=sg3, sales_growth_5y=sg5,
            profit_growth_3y=pg3, profit_growth_5y=pg5, eps=eps,
            debt_to_equity=de, interest_coverage=ic, current_ratio=cr,
            promoter_holding=promoter, promoter_pledge=pledge,
            fii_holding=fii, dii_holding=dii,
            high_52w=h52, low_52w=l52, high_all_time=ath,
            current_price=cmp, industry_pe=industry_pe,
            pct_from_52w_high=round(pct_52h, 1) if pct_52h else None,
            pct_from_ath=round(pct_ath, 1) if pct_ath else None,
        )
        logger.info("Fundamentals for %s: PE=%s ROCE=%s ROE=%s D/E=%s Promoter=%s%%",
                     symbol, pe, roce, roe, de, promoter)
        return f
    except Exception as exc:
        logger.error("Failed to fetch fundamentals for %s: %s", symbol, exc)
        return StockFundamentals(symbol=symbol)


def fetch_fundamentals_cached(symbol: str, cache_dir: str = "cache") -> StockFundamentals:
    """Fetch fundamentals with daily caching to avoid repeated Screener hits."""
    cache_path = os.path.join(cache_dir, "fundamentals.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    today = datetime.now(IST).strftime("%Y-%m-%d")
    entry = cache.get(symbol)
    if entry and entry.get("_date") == today:
        # Return cached
        return StockFundamentals(**{k: v for k, v in entry.items() if k != "_date"})

    # Fetch fresh
    f = fetch_fundamentals(symbol)

    # Cache it
    data = {}
    for field_name in f.__dataclass_fields__:
        data[field_name] = getattr(f, field_name)
    data["_date"] = today
    cache[symbol] = data

    os.makedirs(cache_dir, exist_ok=True)
    try:
        with open(cache_path, "w") as fp:
            json.dump(cache, fp, indent=2, default=str)
    except Exception as e:
        logger.warning("Failed to write fundamentals cache: %s", e)

    return f


def compute_stock_score(f: StockFundamentals) -> dict:
    """Compute a multi-factor quality score like a veteran analyst.

    Returns dict with overall score (0-100), grade, and per-factor breakdown.
    """
    scores = {}
    total = 0
    count = 0

    # Valuation (lower PE relative to industry = better)
    if f.pe_ratio and f.industry_pe and f.industry_pe > 0:
        ratio = f.pe_ratio / f.industry_pe
        scores["valuation_pe"] = max(0, min(100, int((1.5 - ratio) * 66)))
    elif f.pe_ratio:
        scores["valuation_pe"] = 70 if f.pe_ratio < 25 else 50 if f.pe_ratio < 40 else 30

    if f.pb_ratio:
        scores["valuation_pb"] = 80 if f.pb_ratio < 3 else 60 if f.pb_ratio < 5 else 30

    # Profitability
    if f.roce:
        scores["profitability_roce"] = min(100, int(f.roce * 4)) if f.roce > 0 else 0
    if f.roe:
        scores["profitability_roe"] = min(100, int(f.roe * 5)) if f.roe > 0 else 0

    # Growth
    if f.sales_growth_5y:
        scores["growth_sales"] = min(100, int(f.sales_growth_5y * 4)) if f.sales_growth_5y > 0 else 0
    if f.profit_growth_5y:
        scores["growth_profit"] = min(100, int(f.profit_growth_5y * 4)) if f.profit_growth_5y > 0 else 0

    # Financial Health
    if f.debt_to_equity is not None:
        scores["health_de"] = 90 if f.debt_to_equity < 0.3 else 70 if f.debt_to_equity < 0.5 else 50 if f.debt_to_equity < 1 else 20
    if f.interest_coverage:
        scores["health_ic"] = min(100, int(f.interest_coverage * 10)) if f.interest_coverage > 0 else 0

    # Ownership
    if f.promoter_holding:
        scores["ownership_promoter"] = min(100, int(f.promoter_holding * 1.5))
    if f.promoter_pledge is not None:
        scores["ownership_pledge"] = 90 if f.promoter_pledge < 5 else 60 if f.promoter_pledge < 20 else 20

    # Technical
    if f.pct_from_52w_high is not None:
        # Closer to 52w high = stronger momentum
        scores["technical_52w"] = max(0, min(100, int(100 + f.pct_from_52w_high)))

    # Aggregate
    for v in scores.values():
        total += v
        count += 1

    overall = int(total / count) if count > 0 else 0
    grade = "A+" if overall >= 85 else "A" if overall >= 75 else "B+" if overall >= 65 else "B" if overall >= 55 else "C" if overall >= 40 else "D"

    return {
        "overall_score": overall,
        "grade": grade,
        "factors": scores,
        "verdict": _score_verdict(overall, f),
    }


def fetch_fundamentals_batch(symbols: list[str], cache_dir: str = "cache") -> dict[str, StockFundamentals]:
    """Fetch fundamentals for multiple symbols with caching and rate limiting.

    Args:
        symbols: List of NSE symbols to fetch
        cache_dir: Directory for caching

    Returns:
        Dict mapping symbol to StockFundamentals (only successful fetches)
    """
    results = {}

    for i, symbol in enumerate(symbols):
        if not symbol:
            continue

        try:
            logger.info("Fetching fundamentals for %s (%d/%d)", symbol, i+1, len(symbols))
            fund = fetch_fundamentals_cached(symbol, cache_dir)
            if fund:
                results[symbol] = fund
        except Exception as e:
            logger.warning("Failed to fetch fundamentals for %s: %s", symbol, e)
            continue

    logger.info("Fetched fundamentals for %d out of %d symbols", len(results), len(symbols))
    return results


def _score_verdict(score, f):
    """Generate a one-line analyst verdict based on score and fundamentals."""
    parts = []
    if f.roce and f.roce > 20:
        parts.append(f"Strong ROCE ({f.roce:.0f}%)")
    elif f.roce and f.roce < 10:
        parts.append(f"Weak ROCE ({f.roce:.0f}%)")
    if f.debt_to_equity is not None and f.debt_to_equity > 1:
        parts.append(f"High debt (D/E: {f.debt_to_equity:.1f})")
    elif f.debt_to_equity is not None and f.debt_to_equity < 0.3:
        parts.append("Low debt")
    if f.promoter_holding and f.promoter_holding > 60:
        parts.append(f"High promoter stake ({f.promoter_holding:.0f}%)")
    if f.pct_from_52w_high and f.pct_from_52w_high < -30:
        parts.append(f"Down {abs(f.pct_from_52w_high):.0f}% from 52W high")
    if score >= 75:
        parts.insert(0, "Quality pick")
    elif score < 40:
        parts.insert(0, "Weak fundamentals")
    return " | ".join(parts) if parts else "Insufficient data"
