"""
comp_finder.py — Uses the Anthropic Claude API to identify comparable public
companies and historical M&A transactions based on a user-supplied company
description. Returns structured lists of ticker symbols and deal metadata.
All Claude API calls use model: claude-sonnet-4-20250514.
"""

import json
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-20250514"

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list:
    """
    Try two strategies to extract a JSON array from a Claude response:
      1. Direct json.loads() on the full text
      2. Regex to pull the first [...] block

    Returns the parsed list, or [] if both fail.
    """
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: find the first JSON array in the text
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    print(f"[WARNING] comp_finder: could not parse JSON array from response:\n{text[:300]}")
    return []


_SYSTEM_PROMPT = (
    "You are an expert M&A analyst at a bulge bracket investment bank. "
    "When given a company description, identify the most relevant publicly "
    "traded comparable companies. Respond with valid JSON only — no "
    "explanation, no markdown, no code blocks. Just the raw JSON array."
)


def _call_claude(user_prompt: str, max_tokens: int = 1024) -> str:
    """Single-shot Claude API call. Returns response text, or '' on failure."""
    try:
        client = _get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        print(f"[WARNING] comp_finder: Claude API call failed — {e}")
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_comps(description: str, market: str = "both") -> list[dict]:
    """
    Ask Claude to identify 5 publicly traded comparable companies for the
    given business description.

    Parameters
    ----------
    description : str   Free-text company description
    market      : str   "us", "india", or "both"

    Returns
    -------
    list[dict] with keys: name, ticker, market, exchange, reason
    Empty list on any failure.
    """
    user_prompt = (
        f"Find 5 publicly traded comparable companies for this business:\n"
        f"{description}\n\n"
        f"Market focus: {market} (us = US listed, india = NSE listed, both = mix)\n\n"
        f"Return exactly this JSON format:\n"
        f"[\n"
        f"  {{\n"
        f'    "name": "Company Name",\n'
        f'    "ticker": "TICKER",\n'
        f'    "market": "us" or "india",\n'
        f'    "exchange": "NASDAQ" or "NSE" etc,\n'
        f'    "reason": "One sentence why this is a relevant comp"\n'
        f"  }}\n"
        f"]\n\n"
        f"For Indian companies use NSE tickers with .NS suffix (e.g. INFY.NS).\n"
        f"For US companies use standard tickers (e.g. CRM).\n"
        f"Return only the JSON array, nothing else."
    )

    raw = _call_claude(user_prompt)
    if not raw:
        return []

    items = _parse_json_array(raw)
    required_keys = {"name", "ticker", "market", "reason"}
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            print(f"[WARNING] comp_finder: skipping comp missing keys — {item}")
            continue
        valid.append(item)

    return valid


def find_transactions(description: str) -> list[dict]:
    """
    Ask Claude to surface 5 relevant historical M&A transactions for a
    company matching the given description.

    Returns
    -------
    list[dict] with keys: target, acquirer, year, deal_size_usd_m,
                          ev_revenue, ev_ebitda, notes
    Empty list on any failure.
    """
    user_prompt = (
        f"Find 5 relevant historical M&A transactions for a company like this:\n"
        f"{description}\n\n"
        f"These are past deals — use your training knowledge.\n\n"
        f"Return exactly this JSON format:\n"
        f"[\n"
        f"  {{\n"
        f'    "target": "Target Company",\n'
        f'    "acquirer": "Acquirer Company",\n'
        f'    "year": "2021",\n'
        f'    "deal_size_usd_m": "5200",\n'
        f'    "ev_revenue": "8.2",\n'
        f'    "ev_ebitda": "42.1",\n'
        f'    "notes": "One sentence context"\n'
        f"  }}\n"
        f"]\n\n"
        f'Use "NA" if a multiple is unknown.\n'
        f"Return only the JSON array, nothing else."
    )

    raw = _call_claude(user_prompt)
    if not raw:
        return []

    items = _parse_json_array(raw)
    required_keys = {"target", "acquirer", "year", "notes"}
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not required_keys.issubset(item.keys()):
            print(f"[WARNING] comp_finder: skipping transaction missing keys — {item}")
            continue
        valid.append(item)

    return valid


def generate_rationale(description: str, comps: list) -> str:
    """
    Ask Claude to write exactly 3 sentences explaining why the provided
    comparable companies are appropriate for the given business.

    Returns
    -------
    str   Rationale text, or '' on failure.
    """
    if not comps:
        return ""

    comp_names = ", ".join(
        c.get("name", c.get("ticker", "Unknown")) for c in comps
    )

    # Override system prompt for this call — we want prose, not JSON
    try:
        client = _get_client()
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=(
                "You are an expert M&A analyst at a bulge bracket investment bank. "
                "Write clear, concise financial analysis in plain English."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"In exactly 3 sentences, explain why the following companies are "
                    f"appropriate comparable companies for this business:\n\n"
                    f"Business: {description}\n\n"
                    f"Comparable companies: {comp_names}\n\n"
                    f"Be specific about shared business model characteristics, "
                    f"market positioning, and revenue drivers."
                ),
            }],
        )
        return response.content[0].text.strip() if response.content else ""
    except Exception as e:
        print(f"[WARNING] comp_finder: rationale generation failed — {e}")
        return ""


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DIVIDER = "-" * 70

    TEST_DESCRIPTION = (
        "B2B SaaS company focused on HR and payroll software, "
        "serving mid-market companies in India, approximately $20M ARR, "
        "Series B stage, direct competitors to Darwinbox and Keka"
    )

    print(f"\n{DIVIDER}")
    print("TEST DESCRIPTION:")
    print(f"  {TEST_DESCRIPTION}")

    # --- Comparable companies ---
    print(f"\n{DIVIDER}")
    print("COMPARABLE COMPANIES (market=india):")
    comps = find_comps(TEST_DESCRIPTION, market="india")
    if comps:
        for i, c in enumerate(comps, 1):
            print(f"  {i}. {c.get('name')} ({c.get('ticker')}) — {c.get('exchange')}")
            print(f"     Reason: {c.get('reason')}")
    else:
        print("  [No comps returned]")

    # --- M&A Transactions ---
    print(f"\n{DIVIDER}")
    print("HISTORICAL M&A TRANSACTIONS:")
    transactions = find_transactions(TEST_DESCRIPTION)
    if transactions:
        for i, t in enumerate(transactions, 1):
            print(
                f"  {i}. {t.get('target')} acquired by {t.get('acquirer')} "
                f"({t.get('year')}) — ${t.get('deal_size_usd_m')}M"
            )
            print(
                f"     EV/Rev: {t.get('ev_revenue')}x  "
                f"EV/EBITDA: {t.get('ev_ebitda')}x"
            )
            print(f"     Notes: {t.get('notes')}")
    else:
        print("  [No transactions returned]")

    # --- Rationale ---
    print(f"\n{DIVIDER}")
    print("ANALYST RATIONALE:")
    rationale = generate_rationale(TEST_DESCRIPTION, comps)
    if rationale:
        print(f"  {rationale}")
    else:
        print("  [No rationale generated]")

    print(f"\n{DIVIDER}")
    print("Smoke-test complete.")
