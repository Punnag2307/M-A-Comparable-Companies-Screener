"""
data_fetcher.py — Fetches financial data for public companies using yfinance.
Handles ticker lookups, income statement, balance sheet, and cash flow data.
Indian NSE tickers are automatically suffixed with .NS (e.g. RELIANCE.NS).
All functions return None on failure and never raise exceptions to callers.
"""

import warnings
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

# Suppress noisy yfinance deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)


def get_financials(ticker: str) -> dict:
    """
    Fetch key financial metrics for a public company via yfinance.

    Returns a dict with keys:
        ticker, name, market_cap, enterprise_value,
        revenue, ebitda, net_income, total_debt, cash,
        shares_outstanding, current_price

    All values default to None if unavailable. Never raises.
    """
    base = {
        "ticker": ticker,
        "name": None,
        "market_cap": None,
        "enterprise_value": None,
        "revenue": None,
        "ebitda": None,
        "net_income": None,
        "total_debt": None,
        "cash": None,
        "shares_outstanding": None,
        "current_price": None,
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        def _get(key):
            val = info.get(key)
            if val in (None, "", "N/A", 0):
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _get_str(key):
            val = info.get(key)
            return str(val) if val else None

        name           = _get_str("longName") or _get_str("shortName")
        market_cap     = _get("marketCap")
        total_debt     = _get("totalDebt")
        cash           = _get("totalCash")
        revenue        = _get("totalRevenue")
        ebitda         = _get("ebitda")
        net_income     = _get("netIncomeToCommon")
        shares_out     = _get("sharesOutstanding")
        current_price  = _get("currentPrice") or _get("regularMarketPrice")

        # Derived: EV = market_cap + total_debt - cash
        if market_cap is not None:
            ev = market_cap
            ev += (total_debt or 0)
            ev -= (cash or 0)
        else:
            ev = None

        missing = [k for k, v in {
            "name": name, "market_cap": market_cap,
            "total_debt": total_debt, "cash": cash,
            "revenue": revenue, "ebitda": ebitda,
            "net_income": net_income, "shares_outstanding": shares_out,
            "current_price": current_price,
        }.items() if v is None]

        if missing:
            print(f"[WARNING] {ticker}: missing fields — {', '.join(missing)}")

        return {
            "ticker":             ticker,
            "name":               name,
            "market_cap":         market_cap,
            "enterprise_value":   ev,
            "revenue":            revenue,
            "ebitda":             ebitda,
            "net_income":         net_income,
            "total_debt":         total_debt,
            "cash":               cash,
            "shares_outstanding": shares_out,
            "current_price":      current_price,
        }

    except Exception as e:
        print(f"[WARNING] {ticker}: fetch failed — {e}")
        return base


def get_price_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    """
    Download historical OHLCV price data for a ticker.

    Parameters
    ----------
    ticker : str
    period : str  yfinance period string, default "2y"

    Returns empty DataFrame on any failure, never raises.
    """
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df is None or df.empty:
            print(f"[WARNING] {ticker}: no price history returned for period='{period}'")
            return pd.DataFrame()
        return df
    except Exception as e:
        print(f"[WARNING] {ticker}: price history fetch failed — {e}")
        return pd.DataFrame()


def validate_ticker(ticker: str) -> bool:
    """
    Return True if yfinance recognises the ticker (non-None market_cap).
    Return False otherwise. Never raises.
    """
    try:
        data = get_financials(ticker)
        return data.get("market_cap") is not None
    except Exception:
        return False


def sanitize_ticker(ticker: str, market: str) -> str:
    """
    Normalise a ticker string for the target market.

    Parameters
    ----------
    ticker : str   Raw ticker symbol
    market : str   One of "india", "us", "both"

    Rules
    -----
    - "india" → append .NS if neither .NS nor .BO suffix present
    - "us"    → return uppercased ticker as-is
    - "both"  → return ticker as-is (Claude already added suffix)
    """
    ticker = ticker.strip()
    market = market.lower()

    if market == "india":
        upper = ticker.upper()
        if not upper.endswith(".NS") and not upper.endswith(".BO"):
            return upper + ".NS"
        return upper
    elif market == "us":
        return ticker.upper()
    else:  # "both" or unknown
        return ticker


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    DIVIDER = "-" * 60

    test_cases = [
        ("AAPL",         "us",    "US — Apple Inc."),
        ("RELIANCE.NS",  "india", "India — Reliance Industries"),
        ("FAKEXYZ123",   "us",    "Invalid ticker"),
    ]

    for raw_ticker, market, label in test_cases:
        print(f"\n{DIVIDER}")
        print(f"TEST: {label}")

        clean = sanitize_ticker(raw_ticker, market)
        print(f"  sanitize_ticker('{raw_ticker}', '{market}') -> '{clean}'")

        valid = validate_ticker(clean)
        print(f"  validate_ticker('{clean}') -> {valid}")

        financials = get_financials(clean)
        # Pretty-print with commas for large numbers
        display = {}
        for k, v in financials.items():
            if isinstance(v, float) and v > 1_000:
                display[k] = f"{v:,.0f}"
            else:
                display[k] = v
        print(f"  get_financials:")
        for k, v in display.items():
            print(f"    {k:<22} {v}")

        hist = get_price_history(clean, period="1mo")
        if hist.empty:
            print(f"  get_price_history: empty DataFrame")
        else:
            print(f"  get_price_history: {len(hist)} rows, "
                  f"cols={list(hist.columns)}, "
                  f"range={hist.index[0].date()} to {hist.index[-1].date()}")

    print(f"\n{DIVIDER}")
    print("Smoke-test complete.")
