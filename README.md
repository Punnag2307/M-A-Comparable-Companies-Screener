# M&A Comparable Companies Screener

A Streamlit web app that takes a company description, uses the Anthropic Claude API to identify comparable public companies and historical M&A transactions, fetches their financials via yfinance, calculates valuation multiples (EV/EBITDA, EV/Revenue, P/E), runs a simple DCF model, and exports a formatted Excel report.

## Project Structure

```
ma-comps-screener/
├── src/
│   ├── __init__.py
│   ├── data_fetcher.py     # yfinance financial data retrieval
│   ├── comp_finder.py      # Claude API — comparable company & deal identification
│   ├── multiples.py        # EV/EBITDA, EV/Revenue, P/E calculation
│   ├── dcf.py              # Simple DCF model
│   └── excel_export.py     # Formatted Excel workbook export
├── app/
│   ├── __init__.py
│   └── streamlit_app.py    # Streamlit front-end
├── tests/
│   └── test_fetcher.py     # Unit tests for data_fetcher
├── .env                    # API keys (never commit)
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

1. **Clone the repo and create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure your API key:**
   Edit `.env` and replace the placeholder:
   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

3. **Run the app:**
   ```bash
   streamlit run app/streamlit_app.py
   ```

## Key Design Decisions

- API keys are loaded from `.env` via `python-dotenv` — never hardcoded.
- All functions handle missing data gracefully (return `None`, never crash).
- Indian NSE tickers automatically receive the `.NS` suffix (e.g. `RELIANCE.NS`).
- All Claude API calls use model `claude-sonnet-4-20250514`.
- Streamlit results are stored in `st.session_state` to avoid redundant API calls.
