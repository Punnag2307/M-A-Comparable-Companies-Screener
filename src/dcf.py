"""
dcf.py — Implements a simple Discounted Cash Flow (DCF) model.
Projects free cash flows using analyst-estimated or user-supplied growth rates,
applies a terminal value, and discounts back at a given WACC to produce an
intrinsic value estimate. Returns None gracefully when required inputs are absent.
"""

import copy

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DA_PCT    = 0.04   # D&A as % of revenue
_TAX_RATE  = 0.25   # effective tax rate
_CAPEX_PCT = 0.03   # capex as % of revenue
_YEARS     = 5      # projection horizon

_EMPTY_RESULT = {
    "enterprise_value":    None,
    "equity_value":        None,
    "implied_share_price": None,
    "terminal_value":      None,
    "terminal_value_pct":  None,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _project_fcfs(params: dict) -> tuple[list[float], list[float], list[float]]:
    """
    Project revenues, FCFs, and per-year line items from params.

    Returns (revenues, fcfs, line_items_by_year)
    where line_items_by_year is a list of dicts, one per year.
    """
    base_revenue   = float(params["base_revenue"])
    growth_rates   = params["growth_rates"]
    ebitda_margin  = float(params["ebitda_margin"])
    wacc           = float(params["wacc"])

    revenues     = []
    line_items   = []    # list of dicts
    fcfs         = []

    rev = base_revenue
    for t in range(_YEARS):
        rev = rev * (1 + float(growth_rates[t]))
        ebitda = rev * ebitda_margin
        da     = rev * _DA_PCT
        ebit   = ebitda - da
        tax    = ebit * _TAX_RATE if ebit > 0 else 0.0
        nopat  = ebit - tax
        capex  = rev * _CAPEX_PCT
        fcf    = nopat + da - capex
        df     = 1 / (1 + wacc) ** (t + 1)
        pv_fcf = fcf * df

        revenues.append(rev)
        fcfs.append(fcf)
        line_items.append({
            "Revenue":          round(rev, 1),
            "EBITDA":           round(ebitda, 1),
            "D&A":              round(da, 1),
            "EBIT":             round(ebit, 1),
            "Tax":              round(tax, 1),
            "NOPAT":            round(nopat, 1),
            "Capex":            round(capex, 1),
            "Free Cash Flow":   round(fcf, 1),
            "Discount Factor":  round(df, 4),
            "PV of FCF":        round(pv_fcf, 1),
        })

    return revenues, fcfs, line_items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_dcf(params: dict) -> dict:
    """
    Run a 5-year DCF model.

    Parameters (all $M unless noted)
    ----------------------------------
    base_revenue        : float
    growth_rates        : list[float]  — 5 annual growth rates
    ebitda_margin       : float
    wacc                : float
    terminal_growth_rate: float
    net_debt            : float        — negative = net cash position
    shares_outstanding  : float | None — millions of shares

    Returns dict with enterprise_value, equity_value, implied_share_price,
    terminal_value, terminal_value_pct. All $M, rounded to 1 decimal.
    Returns all-None dict on any failure.
    """
    try:
        wacc                 = float(params["wacc"])
        terminal_growth_rate = float(params["terminal_growth_rate"])
        net_debt             = float(params["net_debt"])
        shares               = params.get("shares_outstanding")

        if wacc <= terminal_growth_rate:
            print(f"[WARNING] dcf: WACC ({wacc}) must be > terminal growth rate ({terminal_growth_rate})")
            return _EMPTY_RESULT.copy()

        _, fcfs, line_items = _project_fcfs(params)

        # Terminal value on FCF Year 5
        fcf_y5       = fcfs[-1]
        terminal_val = fcf_y5 * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
        pv_terminal  = terminal_val / (1 + wacc) ** _YEARS

        # Sum of discounted FCFs
        pv_fcfs = sum(item["PV of FCF"] for item in line_items)

        ev            = pv_fcfs + pv_terminal
        equity_val    = ev - net_debt
        tv_pct        = round((pv_terminal / ev) * 100, 1) if ev != 0 else None

        implied_price = None
        if shares is not None:
            try:
                implied_price = round(equity_val / float(shares), 1)
            except (TypeError, ZeroDivisionError):
                pass

        return {
            "enterprise_value":    round(ev, 1),
            "equity_value":        round(equity_val, 1),
            "implied_share_price": implied_price,
            "terminal_value":      round(pv_terminal, 1),
            "terminal_value_pct":  tv_pct,
        }

    except Exception as e:
        print(f"[WARNING] dcf: run_dcf failed — {e}")
        return _EMPTY_RESULT.copy()


def run_scenarios(base_params: dict) -> dict:
    """
    Generate Bear / Base / Bull scenarios from base_params and run DCF for each.

    Adjustments
    -----------
    Bear : growth_rates * 0.7,  ebitda_margin * 0.85,  wacc + 0.02
    Base : no change
    Bull : growth_rates * 1.3,  ebitda_margin * 1.10,  wacc - 0.015 (floor 0.08)

    Returns {"bear": {...}, "base": {...}, "bull": {...}}
    """
    def _scale_params(multiplier_growth, multiplier_margin, wacc_delta):
        p = copy.deepcopy(base_params)
        p["growth_rates"]  = [g * multiplier_growth for g in p["growth_rates"]]
        p["ebitda_margin"] = p["ebitda_margin"] * multiplier_margin
        p["wacc"]          = max(0.08, p["wacc"] + wacc_delta)
        return p

    return {
        "bear": run_dcf(_scale_params(0.70, 0.85,  +0.02)),
        "base": run_dcf(base_params),
        "bull": run_dcf(_scale_params(1.30, 1.10,  -0.015)),
    }


def build_dcf_table(params: dict) -> pd.DataFrame:
    """
    Build a year-by-year DCF projection table.

    Returns pd.DataFrame with line items as rows and Year 1–5 as columns.
    All values in $M, rounded to 1 decimal.
    Returns empty DataFrame on failure.
    """
    try:
        _, _, line_items = _project_fcfs(params)

        row_labels = [
            "Revenue", "EBITDA", "D&A", "EBIT", "Tax",
            "NOPAT", "Capex", "Free Cash Flow",
            "Discount Factor", "PV of FCF",
        ]
        cols = [f"Year {i+1}" for i in range(_YEARS)]

        data = {
            col: [line_items[i][label] for label in row_labels]
            for i, col in enumerate(cols)
        }

        return pd.DataFrame(data, index=row_labels)

    except Exception as e:
        print(f"[WARNING] dcf: build_dcf_table failed — {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DIVIDER = "-" * 70

    params = {
        "base_revenue":        20,
        "growth_rates":        [0.40, 0.35, 0.28, 0.22, 0.18],
        "ebitda_margin":       0.15,
        "wacc":                0.14,
        "terminal_growth_rate":0.04,
        "net_debt":            -5,       # net cash
        "shares_outstanding":  10,       # millions
    }

    # --- DCF projection table ---
    print(f"\n{DIVIDER}")
    print("DCF PROJECTION TABLE ($M)")
    table = build_dcf_table(params)
    if not table.empty:
        pd.set_option("display.float_format", lambda x: f"{x:,.4f}" if abs(x) < 1 else f"{x:,.1f}")
        pd.set_option("display.width", 160)
        print(table.to_string())
    else:
        print("  [Empty — check warnings above]")

    # --- Scenarios ---
    print(f"\n{DIVIDER}")
    print("SCENARIO ANALYSIS")
    scenarios = run_scenarios(params)

    scenario_rows = [
        ("Enterprise Value ($M)",  "enterprise_value"),
        ("Equity Value ($M)",      "equity_value"),
        ("Implied Share Price ($)", "implied_share_price"),
        ("Terminal Value ($M)",    "terminal_value"),
        ("TV as % of EV",          "terminal_value_pct"),
    ]

    col_w = 22
    print(f"\n  {'Metric':<30} {'Bear':>{col_w}} {'Base':>{col_w}} {'Bull':>{col_w}}")
    print(f"  {'-'*30} {'-'*col_w} {'-'*col_w} {'-'*col_w}")
    for label, key in scenario_rows:
        vals = []
        for s in ("bear", "base", "bull"):
            v = scenarios[s][key]
            if v is None:
                vals.append("N/A")
            elif key == "terminal_value_pct":
                vals.append(f"{v:.1f}%")
            elif key == "implied_share_price":
                vals.append(f"${v:,.1f}")
            else:
                vals.append(f"${v:,.1f}M")
        print(f"  {label:<30} {vals[0]:>{col_w}} {vals[1]:>{col_w}} {vals[2]:>{col_w}}")

    print(f"\n{DIVIDER}")
    print("Smoke-test complete.")
