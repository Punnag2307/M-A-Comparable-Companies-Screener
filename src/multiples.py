"""
multiples.py — Calculates valuation multiples for a set of comparable companies.
Computes EV/EBITDA, EV/Revenue, and P/E ratios from raw financial data.
Returns a pandas DataFrame; individual missing values are filled with "NM"
so that the rest of the table remains usable.
"""

import os
import sys

import numpy as np
import pandas as pd

# Allow both `python src/multiples.py` and `from src.multiples import ...`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data_fetcher import get_financials, sanitize_ticker

_M = 1_000_000  # divisor for $ → $M conversions

# Exact column order required everywhere
COLUMNS = [
    "Company", "Ticker", "Market",
    "Market Cap ($M)", "EV ($M)",
    "Revenue ($M)", "EBITDA ($M)",
    "EV/EBITDA", "EV/Revenue", "P/E",
]

MULTIPLE_COLS = ["EV/EBITDA", "EV/Revenue", "P/E"]
SUMMARY_LABELS = ["Median", "25th Pct", "75th Pct"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_multiple(numerator, denominator) -> str | float:
    """
    Return numerator / denominator rounded to 1 decimal.
    Returns "NM" if denominator is None, zero, negative,
    or if numerator is None.
    """
    try:
        if numerator is None or denominator is None:
            return "NM"
        d = float(denominator)
        n = float(numerator)
        if d <= 0:
            return "NM"
        return round(n / d, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return "NM"


def _to_millions(value) -> str | float:
    """Convert raw dollar value to $M rounded to 1 decimal, or None."""
    try:
        if value is None:
            return None
        return round(float(value) / _M, 1)
    except (TypeError, ValueError):
        return None


def _numeric_values(series: pd.Series) -> list[float]:
    """Extract numeric (non-NM, non-NaN, non-None) values from a series."""
    result = []
    for v in series:
        if v == "NM" or v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        try:
            result.append(float(v))
        except (TypeError, ValueError):
            continue
    return result


def _percentile(values: list[float], pct: float):
    """Return the given percentile of values, or None if empty."""
    if not values:
        return None
    return round(float(np.percentile(values, pct)), 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_comps_table(comps_list: list[dict]) -> pd.DataFrame:
    """
    Build a comparable companies valuation table.

    Parameters
    ----------
    comps_list : list[dict]
        Output from find_comps(); each dict must have:
        name, ticker, market, reason

    Returns
    -------
    pd.DataFrame  with columns defined in COLUMNS.
    Appends Median / 25th Pct / 75th Pct summary rows at the bottom.
    Returns an empty DataFrame on complete failure.
    """
    rows = []

    for comp in comps_list:
        try:
            raw_ticker = comp.get("ticker", "")
            market     = comp.get("market", "both")
            name       = comp.get("name", raw_ticker)

            ticker = sanitize_ticker(raw_ticker, market)
            fin    = get_financials(ticker)

            ev_ebitda  = _safe_multiple(fin["enterprise_value"], fin["ebitda"])
            ev_revenue = _safe_multiple(fin["enterprise_value"], fin["revenue"])
            pe_ratio   = _safe_multiple(fin["market_cap"],       fin["net_income"])

            rows.append({
                "Company":         name,
                "Ticker":          ticker,
                "Market":          market.upper(),
                "Market Cap ($M)": _to_millions(fin["market_cap"]),
                "EV ($M)":         _to_millions(fin["enterprise_value"]),
                "Revenue ($M)":    _to_millions(fin["revenue"]),
                "EBITDA ($M)":     _to_millions(fin["ebitda"]),
                "EV/EBITDA":       ev_ebitda,
                "EV/Revenue":      ev_revenue,
                "P/E":             pe_ratio,
            })

        except Exception as e:
            print(f"[WARNING] multiples: failed to process {comp} — {e}")
            continue

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    df = pd.DataFrame(rows, columns=COLUMNS)

    # --- Summary rows ---
    summary_rows = []
    for label, pct in [("Median", 50), ("25th Pct", 25), ("75th Pct", 75)]:
        row = {col: "" for col in COLUMNS}
        row["Company"] = label
        for col in MULTIPLE_COLS:
            vals = _numeric_values(df[col])
            row[col] = _percentile(vals, pct) if vals else "NM"
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows, columns=COLUMNS)
    return pd.concat([df, summary_df], ignore_index=True)


def get_implied_value(
    target_ebitda: float,
    target_revenue: float,
    comps_df: pd.DataFrame,
) -> dict:
    """
    Derive implied enterprise value ranges from comps table multiples.

    Parameters
    ----------
    target_ebitda   : float  Target company EBITDA in $M
    target_revenue  : float  Target company Revenue in $M
    comps_df        : pd.DataFrame  Output of build_comps_table()

    Returns
    -------
    dict with keys:
        ev_ebitda_low, ev_ebitda_median, ev_ebitda_high
        ev_revenue_low, ev_revenue_median, ev_revenue_high
    All values in $M, rounded to 1 decimal.
    Returns all-None dict on failure.
    """
    _empty = {
        "ev_ebitda_low":    None,
        "ev_ebitda_median": None,
        "ev_ebitda_high":   None,
        "ev_revenue_low":   None,
        "ev_revenue_median":None,
        "ev_revenue_high":  None,
    }

    try:
        # Strip summary rows so we only use company-level data
        comp_rows = comps_df[~comps_df["Company"].isin(SUMMARY_LABELS)]

        ev_ebitda_vals  = _numeric_values(comp_rows["EV/EBITDA"])
        ev_revenue_vals = _numeric_values(comp_rows["EV/Revenue"])

        def _implied(multiple_vals: list[float], metric: float) -> tuple:
            if not multiple_vals or metric is None:
                return None, None, None
            low    = round(_percentile(multiple_vals, 25) * metric, 1)
            median = round(_percentile(multiple_vals, 50) * metric, 1)
            high   = round(_percentile(multiple_vals, 75) * metric, 1)
            return low, median, high

        eb_low, eb_med, eb_high = _implied(ev_ebitda_vals,  target_ebitda)
        rv_low, rv_med, rv_high = _implied(ev_revenue_vals, target_revenue)

        return {
            "ev_ebitda_low":     eb_low,
            "ev_ebitda_median":  eb_med,
            "ev_ebitda_high":    eb_high,
            "ev_revenue_low":    rv_low,
            "ev_revenue_median": rv_med,
            "ev_revenue_high":   rv_high,
        }

    except Exception as e:
        print(f"[WARNING] multiples: get_implied_value failed — {e}")
        return _empty


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DIVIDER = "-" * 70

    TEST_COMPS = [
        {"name": "Workday",    "ticker": "WDAY",      "market": "us",    "reason": "HR SaaS"},
        {"name": "Paycom",     "ticker": "PAYC",      "market": "us",    "reason": "HR SaaS"},
        {"name": "Info Edge",  "ticker": "NAUKRI.NS", "market": "india", "reason": "Indian HR tech"},
    ]

    print(f"\n{DIVIDER}")
    print("Building comps table for:")
    for c in TEST_COMPS:
        print(f"  {c['name']} ({c['ticker']})")

    df = build_comps_table(TEST_COMPS)

    print(f"\n{DIVIDER}")
    print("COMPS TABLE:")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", lambda x: f"{x:,.1f}")
    print(df.to_string(index=False))

    print(f"\n{DIVIDER}")
    print("IMPLIED VALUE RANGES (target EBITDA=$50M, target Revenue=$200M):")
    implied = get_implied_value(
        target_ebitda=50,
        target_revenue=200,
        comps_df=df,
    )
    for key, val in implied.items():
        label = key.replace("_", " ").title()
        print(f"  {label:<25} {f'${val:,.1f}M' if val is not None else 'N/A'}")

    print(f"\n{DIVIDER}")
    print("Smoke-test complete.")
