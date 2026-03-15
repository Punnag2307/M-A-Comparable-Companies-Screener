"""
streamlit_app.py — Main Streamlit application for the M&A Comparable Companies Screener.
Provides a UI for entering a company description, displays comparable public companies,
historical M&A transactions, valuation multiples (EV/EBITDA, EV/Revenue, P/E),
a DCF model summary, and a button to export everything to a formatted Excel file.
Results are cached in st.session_state to prevent redundant API calls on re-renders.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.comp_finder import find_comps, find_transactions, generate_rationale
from src.dcf import build_dcf_table, run_dcf, run_scenarios
from src.excel_export import export_to_excel
from src.multiples import build_comps_table, get_implied_value

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="M&A Comps Screener",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 M&A Comps Screener")
    st.caption("Institutional-grade comparable analysis")
    st.divider()

    market_label = st.radio(
        "Market Focus",
        options=["🌍 Both", "🇺🇸 US Only", "🇮🇳 India Only"],
        index=0,
    )
    market_map = {"🌍 Both": "both", "🇺🇸 US Only": "us", "🇮🇳 India Only": "india"}
    market = market_map[market_label]

    st.markdown("---")
    st.markdown("**Sample inputs to try:**")
    st.markdown("• `Zepto` — quick commerce")
    st.markdown("• `Razorpay` — fintech payments")
    st.markdown("• `HDFC Bank` — private banking")
    st.markdown("• `OpenAI` — AI infrastructure")

    st.divider()

    with st.expander("ℹ️ How it works"):
        st.write(
            "Enter a company description → Claude AI identifies comparable "
            "public companies → Live financials fetched via yfinance → "
            "Valuation multiples calculated → Export to Excel"
        )

# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------
st.title("M&A Comparable Companies Screener")
st.caption("Powered by Claude AI + Live Market Data")

description = st.text_area(
    "Describe the target company",
    height=120,
    placeholder=(
        "Example: B2B SaaS company providing HR and payroll software to "
        "mid-market companies in India. ~$20M ARR, Series B stage, "
        "competitors include Darwinbox and Keka."
    ),
    key="company_desc",
)

run_btn = st.button("Run Analysis", type="primary")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(
    ["📊 Comparable Companies", "📈 DCF Model", "📁 Export"]
)

# ===========================================================================
# TAB 1 — Comparable Companies
# ===========================================================================
with tab1:

    # --- Trigger analysis ---
    if run_btn:
        if not description.strip():
            st.error("Please enter a company description before running the analysis.")
        else:
            with st.spinner("Finding comparable companies via Claude AI..."):
                try:
                    comps = find_comps(description.strip(), market)
                    if not comps:
                        st.error(
                            "Claude did not return any comparables. "
                            "Try a more detailed description."
                        )
                    else:
                        comps_df = build_comps_table(comps)
                        transactions = find_transactions(description.strip())
                        rationale = generate_rationale(description.strip(), comps)

                        st.session_state.comps          = comps
                        st.session_state.comps_df       = comps_df
                        st.session_state.transactions   = transactions
                        st.session_state.rationale      = rationale
                        st.session_state.description    = description.strip()
                        st.session_state.analysis_run   = True

                except Exception as e:
                    st.error(f"Analysis failed: {e}")

    # --- Display results ---
    if st.session_state.get("analysis_run"):
        comps_df     = st.session_state.comps_df
        transactions = st.session_state.transactions
        rationale    = st.session_state.rationale
        comps        = st.session_state.comps

        # Currency warning
        has_india = any(c.get("market", "").lower() == "india" for c in comps)
        if has_india:
            st.info(
                "ℹ️ Indian company financials are in INR. "
                "US company financials are in USD."
            )

        # --- Comps table ---
        st.subheader("Public Comparable Companies")

        summary_labels = {"Median", "25th Pct", "75th Pct"}

        def style_comps_table(df):
            def highlight_rows(row):
                if row["Company"] in summary_labels:
                    return (
                        ["background-color: #FFF2CC; color: #1F3864; font-weight: bold"]
                        * len(row)
                    )
                return [""] * len(row)
            return df.style.apply(highlight_rows, axis=1)

        display_df = comps_df.copy()
        dollar_cols = ["Market Cap ($M)", "EV ($M)", "Revenue ($M)", "EBITDA ($M)"]
        for col in dollar_cols:
            display_df[col] = pd.to_numeric(display_df[col], errors="coerce").round(1)

        st.dataframe(
            style_comps_table(display_df),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("💡 Tip: Indian company financials are in INR — multiples are still comparable, dollar values are not.")

        # --- Transactions table ---
        st.subheader("Historical M&A Transactions")
        if transactions:
            txn_df = pd.DataFrame(transactions)
            txn_df.columns = [c.replace("_", " ").title() for c in txn_df.columns]
            st.dataframe(txn_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No transaction data returned.")

        # --- Rationale ---
        with st.expander("💡 Why these comparables?"):
            st.write(rationale if rationale else "No rationale generated.")

        # --- Plotly chart: EV/EBITDA multiples ---
        st.subheader("Multiple Benchmarks")
        try:
            comp_only = comps_df[~comps_df["Company"].isin(summary_labels)].copy()
            chart_data = []
            for _, row in comp_only.iterrows():
                val = row.get("EV/EBITDA")
                if val not in ("NM", None, "") and isinstance(val, (int, float)):
                    chart_data.append({
                        "company": row["Company"],
                        "ev_ebitda": float(val),
                        "market": str(row.get("Market", "US")).upper(),
                    })

            if chart_data:
                chart_df = pd.DataFrame(chart_data)
                colors = [
                    "#4FC3F7" if m == "US" else "#FFB74D"
                    for m in chart_df["market"]
                ]

                # Pull median from the summary row already computed
                median_row = comps_df[comps_df["Company"] == "Median"]
                if not median_row.empty:
                    med_val = median_row.iloc[0].get("EV/EBITDA")
                    median_val = float(med_val) if med_val not in ("NM", None, "") else None
                else:
                    numeric_vals = [r["ev_ebitda"] for r in chart_data]
                    median_val = sorted(numeric_vals)[len(numeric_vals) // 2]

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=chart_df["company"],
                    y=chart_df["ev_ebitda"],
                    marker_color=colors,
                    text=[f"{v:.1f}x" for v in chart_df["ev_ebitda"]],
                    textposition="outside",
                    textfont=dict(color="white", size=13),
                    name="EV/EBITDA",
                    showlegend=False,
                ))

                if median_val is not None:
                    fig.add_hline(
                        y=median_val,
                        line_dash="dash",
                        line_color="#EF5350",
                        line_width=2,
                        annotation_text=f"Median: {median_val:.1f}x",
                        annotation_position="top right",
                        annotation_font_color="white",
                    )

                # Manual legend traces for market colour coding
                fig.add_trace(go.Bar(
                    x=[None], y=[None],
                    marker_color="#4FC3F7",
                    name="US",
                    showlegend=True,
                ))
                fig.add_trace(go.Bar(
                    x=[None], y=[None],
                    marker_color="#FFB74D",
                    name="India",
                    showlegend=True,
                ))

                fig.update_layout(
                    title=dict(
                        text="EV/EBITDA Multiples Comparison",
                        font=dict(color="white", size=16),
                    ),
                    xaxis=dict(
                        title="Company",
                        tickfont=dict(color="white"),
                        title_font=dict(color="white"),
                        gridcolor="rgba(255,255,255,0.1)",
                    ),
                    yaxis=dict(
                        title="EV/EBITDA (x)",
                        tickfont=dict(color="white"),
                        title_font=dict(color="white"),
                        gridcolor="rgba(255,255,255,0.1)",
                    ),
                    plot_bgcolor="rgba(30,30,30,0.8)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white"),
                    legend=dict(
                        font=dict(color="white"),
                        bgcolor="rgba(0,0,0,0)",
                    ),
                    height=420,
                    barmode="group",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No numeric EV/EBITDA values available to chart.")

        except Exception as e:
            st.caption(f"Chart unavailable: {e}")

# ===========================================================================
# TAB 2 — DCF Model
# ===========================================================================
with tab2:
    left_col, right_col = st.columns([1, 1.4])

    with left_col:
        st.subheader("DCF Assumptions")

        base_revenue = st.number_input(
            "Base Revenue ($M)", min_value=0.1, value=20.0, step=0.5
        )

        st.write("**5-Year Revenue Growth Rates**")
        gr_cols   = st.columns(5)
        defaults  = [35, 28, 22, 18, 14]
        growth_rates = []
        for i, col in enumerate(gr_cols):
            g = col.number_input(
                f"Yr {i+1}%",
                min_value=0, max_value=200,
                value=defaults[i],
                key=f"gr_{i}",
            )
            growth_rates.append(g / 100)

        ebitda_margin = st.slider(
            "EBITDA Margin %", min_value=0, max_value=60, value=15
        ) / 100

        wacc = st.slider(
            "WACC %", min_value=8, max_value=30, value=14
        ) / 100

        terminal_growth = st.slider(
            "Terminal Growth Rate %", min_value=1, max_value=8, value=4
        ) / 100

        net_debt = st.number_input(
            "Net Debt ($M) — negative = net cash",
            value=-5.0, step=1.0,
        )

        run_dcf_btn = st.button("Run DCF", type="primary")

    with right_col:
        st.subheader("DCF Results")

        if run_dcf_btn or st.session_state.get("dcf_run"):
            try:
                params = {
                    "base_revenue":         base_revenue,
                    "growth_rates":         growth_rates,
                    "ebitda_margin":        ebitda_margin,
                    "wacc":                 wacc,
                    "terminal_growth_rate": terminal_growth,
                    "net_debt":             net_debt,
                }

                scenarios = run_scenarios(params)
                dcf_table = build_dcf_table(params)

                st.session_state.dcf_scenarios = scenarios
                st.session_state.dcf_table     = dcf_table
                st.session_state.dcf_params    = params
                st.session_state.dcf_run       = True

                # Scenario metrics
                c1, c2, c3 = st.columns(3)
                for col, name, key in [
                    (c1, "🐻 Bear", "bear"),
                    (c2, "📊 Base", "base"),
                    (c3, "🚀 Bull", "bull"),
                ]:
                    s = scenarios.get(key, {})
                    with col:
                        ev  = s.get("enterprise_value")
                        eq  = s.get("equity_value")
                        tv  = s.get("terminal_value_pct")
                        st.metric(
                            f"{name} EV",
                            f"${ev:,.1f}M" if ev is not None else "N/A",
                        )
                        st.metric(
                            "Equity Value",
                            f"${eq:,.1f}M" if eq is not None else "N/A",
                        )
                        st.metric(
                            "TV % of EV",
                            f"{tv:.1f}%" if tv is not None else "N/A",
                        )

                st.subheader("5-Year Projection")
                if not dcf_table.empty:
                    st.dataframe(
                        dcf_table.style.format("{:,.2f}"),
                        use_container_width=True,
                    )
                else:
                    st.warning("DCF table could not be built. Check WACC vs terminal growth rate.")

                st.caption(
                    "⚠️ DCF assumptions are user inputs. Results are illustrative only."
                )

            except Exception as e:
                st.error(f"DCF failed: {e}")

# ===========================================================================
# TAB 3 — Export
# ===========================================================================
with tab3:
    st.subheader("Export Analysis to Excel")

    if not st.session_state.get("analysis_run"):
        st.warning("Run the analysis first (Tab 1) before exporting.")
    else:
        st.success("Analysis ready to export")

        st.write("Your Excel file will contain 3 sheets:")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info("**Sheet 1**\nComparable Companies\nWith multiples table")
        with col2:
            st.info("**Sheet 2**\nTransaction Comps\nHistorical M&A deals")
        with col3:
            st.info("**Sheet 3**\nDCF Analysis\nBear / Base / Bull")

        if st.button("📥 Generate & Download Excel", type="primary"):
            with st.spinner("Generating Excel model..."):
                try:
                    buffer = export_to_excel(
                        comps_df=st.session_state.comps_df,
                        transactions_list=st.session_state.transactions,
                        dcf_scenarios=st.session_state.get("dcf_scenarios", {}),
                        dcf_table=st.session_state.get("dcf_table", pd.DataFrame()),
                        rationale=st.session_state.rationale,
                        company_description=st.session_state.description,
                        output=None,
                    )

                    if buffer:
                        st.download_button(
                            label="💾 Download Excel Model",
                            data=buffer,
                            file_name="ma_comps_analysis.xlsx",
                            mime=(
                                "application/vnd.openxmlformats-officedocument"
                                ".spreadsheetml.sheet"
                            ),
                        )
                    else:
                        st.error(
                            "Excel generation failed. Check the terminal for details."
                        )

                except Exception as e:
                    st.error(f"Export failed: {e}")
