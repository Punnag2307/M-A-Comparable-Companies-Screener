
# M&A Comparable Companies Screener

An institutional-grade M&A comparables analysis tool that automates 
the first two days of deal work — powered by Claude AI and live market data.

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-red)
![Claude AI](https://img.shields.io/badge/Claude-Sonnet-orange)

## Problem

In early-stage deal analysis, identifying relevant comps and transactions is:

1. Manual
2. Time-intensive
3. Inconsistent across analysts

## What it does

Given a company description or name, the tool:
1. Uses Claude AI to identify 5 relevant public comparable companies 
   and 5 historical M&A transactions
2. Fetches live financials for each comp via yfinance (global markets)
3. Calculates EV/EBITDA, EV/Revenue, and P/E multiples with 
   25th/median/75th percentile benchmarks
4. Runs a 3-scenario DCF model (Bear / Base / Bull)
5. Exports a formatted Excel model across 3 sheets — 
   styled like an actual IB deliverable

## Demo

**Input:** "B2B SaaS HR and payroll software, India mid-market, 
~$20M ARR, Series B, competitors include Darwinbox and Keka"

**Output in ~25 seconds:**
- Comparable companies: Workday, Paychex, Paycom, ADP, Info Edge
- Multiples: EV/EBITDA median 14.0x, EV/Revenue median 3.6x
- DCF implied EV: Bear $24M → Base $49M → Bull $89M
- Downloadable Excel model with 3 formatted sheets

## Why I built this

An IB analyst spends 2 days on a new deal doing exactly this manually — 
Googling comps, pulling financials, building a multiples table in Excel. 
This tool does it in 30 seconds. The goal was to understand both the 
methodology (what makes a good comp, how DCF assumptions flow through 
to value) and whether AI can meaningfully accelerate institutional 
finance workflows.

## Impact

1. Reduces benchmarking time from days → minutes
2. Standardizes initial comps screening
3. Helps analysts focus on judgment vs data gathering

## Architecture

```
ma-comps-screener/
├── src/
│   ├── data_fetcher.py    # yfinance wrapper — US + India (NSE) markets
│   ├── comp_finder.py     # Claude AI — comp identification + rationale
│   ├── multiples.py       # EV/EBITDA, EV/Revenue, P/E + percentile bands
│   ├── dcf.py             # 5-year DCF with Bear/Base/Bull scenarios
│   └── excel_export.py    # IB-style Excel export via openpyxl
└── app/
    └── streamlit_app.py   # Web UI
```

**Data flow:**
User input → Claude API (comp identification) → yfinance (live financials) 
→ Multiples calculation → DCF model → Excel export

## Setup

```bash
git clone https://github.com/Punnag2307/ma-comps-screener
cd ma-comps-screener
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
ANTHROPIC_API_KEY=your_key_here
```
Get your API key at [console.anthropic.com](https://console.anthropic.com)

Run the app:
```bash
streamlit run app/streamlit_app.py
```

## Methodology

**Comparable company selection:** Claude AI identifies comps based on 
business model similarity, sector, geography, and revenue scale. 
Users can filter by US markets, Indian markets (NSE), or both.

**Multiples calculation:**
- EV/EBITDA = Enterprise Value / EBITDA (trailing twelve months)
- EV/Revenue = Enterprise Value / Revenue (TTM)
- P/E = Market Cap / Net Income (TTM)
- Enterprise Value = Market Cap + Total Debt - Cash

**DCF model:**
- 5-year explicit forecast period
- Free Cash Flow = NOPAT + D&A - Capex
- Terminal value via Gordon Growth Model
- 3 scenarios: Bear (growth ×0.7), Base, Bull (growth ×1.3)

**Known limitations:**
- Indian company financials are in INR — multiples are comparable, 
  dollar values are not directly comparable to USD peers
- yfinance data quality varies for smaller companies — 
  "NM" is shown where data is unavailable
- Historical M&A transaction multiples are from Claude's training 
  data and should be independently verified
- DCF assumptions are user inputs — results are illustrative

## Tech stack

| Layer | Technology |
|-------|-----------|
| AI | Anthropic Claude Sonnet |
| Market data | yfinance (Yahoo Finance) |
| Web UI | Streamlit |
| Data | pandas, numpy |
| Excel export | openpyxl |
| Visualization | Plotly |

## What I learned

Building this required understanding both sides of the problem: 
the finance methodology (why EV/EBITDA matters more than P/E for 
high-growth companies, how terminal value dominates DCF outputs at 
high growth rates) and the engineering challenges (mixed-currency 
data normalization, structured JSON extraction from LLM outputs, 
Excel formatting that matches institutional standards).

The most interesting design decision was making the AI layer 
stateless — Claude identifies comps but doesn't store state, 
so every analysis is reproducible and auditable.

---

