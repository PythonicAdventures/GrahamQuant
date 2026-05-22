"""
formulas_calcs.py: Calculations, formulas, and formatting for deep value analysis.

Structure
---------
apply_calcs()      — pure math only, returns raw floats. Used by cache layer.
apply_formatting() — converts raw floats to display strings. Used by UI layer.
create_calcs()     — calls both in sequence. Backwards-compatible entry point
                     for any code that called create_calcs() directly.
"""

import pandas as pd
import numpy as np


# ── Formatters ────────────────────────────────────────────────────────────────

def format_currency(val):
    """Format large numbers into readable strings. Returns 'N/A' for missing data."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000_000:
        return f"{val / 1_000_000_000_000:.1f}t"
    elif abs_val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f}b"
    elif abs_val >= 1_000_000:
        return f"{val / 1_000_000:.1f}m"
    elif abs_val >= 1_000:
        return f"{val / 1_000:.1f}k"
    return str(int(val)) if val == int(val) else f"{val:.1f}"


def format_ratio(val):
    if pd.isna(val) or val < 0 or val in (float("inf"), float("-inf")):
        return "N/A"
    return f"{val:.2f}x"


def format_percentage(val):
    if pd.isna(val) or val in (float("inf"), float("-inf")):
        return "N/A"
    return f"{val:.2%}"


def format_score(val):
    """Format F-Score as integer (0-9)."""
    if pd.isna(val) or val in (float("inf"), float("-inf")):
        return "N/A"
    return str(int(round(val)))


# ── Calculation layer (raw floats — safe to write to parquet) ─────────────────

def apply_calcs(df_: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all deep value calculations to the DataFrame.
    All output columns are raw numeric (float64 / NaN).
    No formatting is applied here — safe to write directly to parquet.
    """
    df_ = df_.sort_values(by=["Ticker", "Year"], ascending=[True, True]).copy()

    # 0 is the correct default for these — absence means none held
    df_["Total Investments"]              = df_["Total Investments"].fillna(0)
    df_["Total Goodwill and Intangibles"] = df_["Total Goodwill and Intangibles"].fillna(0)

    # Ensure required fields exist for Z-Score and F-Score calculations
    for col in ["Current Liabilities", "Retained Earnings", "Latest FY Operating Income", 
                "Latest FY Gross Profit", "Latest FY Revenue", "Latest FY Operating Cash Flow"]:
        if col not in df_.columns:
            df_[col] = None

    df_ = df_.assign(
        NCAV=lambda d: d["Total Current Assets"] - d["Total Liabilities"],
        NCAV_Inv=lambda d: (
            d["Total Current Assets"] - d["Total Liabilities"] + d["Total Investments"]
        ),
        Book_Value=lambda d: d["Total Assets"] - d["Total Liabilities"],
        Tangible_Book_Value=lambda d: (
            d["Total Assets"] - d["Total Liabilities"] - d["Total Goodwill and Intangibles"]
        ),
        ROE=lambda d: (
            d["Latest FY Net Income"] / d["Total Equity"].replace(0, np.nan)
        ),
        ROA=lambda d: (
            d["Latest FY Net Income"] / d["Total Assets"].replace(0, np.nan)
        ),
        Price_Book_Ratio=lambda d: (
            d["Market Cap"] / d["Book_Value"].replace(0, np.nan)
        ),
        Price_Tangible_Book_Ratio=lambda d: (
            d["Market Cap"] / d["Tangible_Book_Value"].replace(0, np.nan)
        ),
        Price_NCAV_Ratio=lambda d: (
            d["Market Cap"] / d["NCAV"].replace(0, np.nan)
        ),
        Price_NCAV_Inv_Ratio=lambda d: (
            d["Market Cap"] / d["NCAV_Inv"].replace(0, np.nan)
        ),
        PE_Ratio=lambda d: (
            d["Market Cap"] / d["Latest FY Net Income"].replace(0, np.nan)
        ),
        PE_Ratio_TTM=lambda d: (
            d["Market Cap"] / d["TTM Net Income"].replace(0, np.nan)
        ),
    )

    # ── Altman Z-Score ────────────────────────────────────────────────────────
    # Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    # X1 = Working Capital / Total Assets
    # X2 = Retained Earnings / Total Assets
    # X3 = EBIT (Operating Income) / Total Assets
    # X4 = Market Value of Equity / Total Liabilities
    # X5 = Sales / Total Assets
    # Returns NaN if critical data is missing
    
    working_capital = (
        df_["Total Current Assets"] - df_["Current Liabilities"].fillna(0)
    )
    x1 = working_capital / df_["Total Assets"].replace(0, np.nan)
    x2 = df_["Retained Earnings"] / df_["Total Assets"].replace(0, np.nan)
    x3 = df_["Latest FY Operating Income"] / df_["Total Assets"].replace(0, np.nan)
    x4 = df_["Market Cap"] / df_["Total Liabilities"].replace(0, np.nan)
    x5 = df_["Latest FY Revenue"] / df_["Total Assets"].replace(0, np.nan)
    
    # Only calculate Z-Score if we have at least 3 of the 5 components
    z_score_components = pd.concat([x1.notna(), x2.notna(), x3.notna(), x4.notna(), x5.notna()], axis=1)
    has_enough_data = z_score_components.sum(axis=1) >= 3
    
    df_["Z_Score"] = np.where(
        has_enough_data,
        1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5,
        np.nan
    )
    
    # ── Piotroski F-Score ─────────────────────────────────────────────────────
    # Score ranges from 0-9. Calculate year-over-year signals.
    # Only computed if we have valid ROA and operating cash flow.
    
    # Signal 1: ROA > 0
    sig1 = (df_["ROA"] > 0).astype(int).fillna(0)
    
    # Signal 2: Operating Cash Flow > 0
    sig2 = (df_["Latest FY Operating Cash Flow"] > 0).astype(int).fillna(0)
    
    # Signals 3-9 require year-over-year comparisons grouped by ticker
    # Initialize lists to hold results
    f_score_data = []
    
    for ticker in df_["Ticker"].unique():
        ticker_df = df_[df_["Ticker"] == ticker].sort_values("Year", ascending=False).reset_index(drop=True)
        
        for idx, (orig_idx, row) in enumerate(ticker_df.iterrows()):
            sig3 = sig4 = sig5 = sig6 = sig7 = sig8 = sig9 = 0
            
            # Signal 3: Change in ROA > 0 (compare to prior year)
            if idx + 1 < len(ticker_df):
                prior_roa = ticker_df.iloc[idx + 1]["ROA"]
                current_roa = row["ROA"]
                if pd.notna(current_roa) and pd.notna(prior_roa) and current_roa > prior_roa:
                    sig3 = 1
            
            # Signal 4: Operating Cash Flow > Net Income (earnings quality)
            if pd.notna(row.get("Latest FY Operating Cash Flow")) and pd.notna(row.get("Latest FY Net Income")):
                if row["Latest FY Operating Cash Flow"] > row["Latest FY Net Income"]:
                    sig4 = 1
            
            # Signal 5: Change in Long-term Debt < 0 (decreasing leverage)
            if idx + 1 < len(ticker_df):
                try:
                    prior_ltd = (ticker_df.iloc[idx + 1].get("Total Liabilities") or 0) - \
                               (ticker_df.iloc[idx + 1].get("Current Liabilities") or 0)
                    current_ltd = (row.get("Total Liabilities") or 0) - (row.get("Current Liabilities") or 0)
                    if current_ltd < prior_ltd:
                        sig5 = 1
                except:
                    pass
            
            # Signal 6: Change in Current Ratio > 0 (improving liquidity)
            if idx + 1 < len(ticker_df):
                try:
                    prior_cr = (ticker_df.iloc[idx + 1].get("Total Current Assets") or 1) / \
                              (ticker_df.iloc[idx + 1].get("Current Liabilities") or 1)
                    current_cr = (row.get("Total Current Assets") or 1) / (row.get("Current Liabilities") or 1)
                    if current_cr > prior_cr:
                        sig6 = 1
                except:
                    pass
            
            # Signal 7: No increase in shares outstanding (not tracked yet, skip)
            sig7 = 0
            
            # Signal 8: Change in Gross Margin > 0 (improving margin)
            if idx + 1 < len(ticker_df):
                try:
                    prior_gm = (ticker_df.iloc[idx + 1].get("Latest FY Gross Profit") or 0) / \
                              (ticker_df.iloc[idx + 1].get("Latest FY Revenue") or 1)
                    current_gm = (row.get("Latest FY Gross Profit") or 0) / (row.get("Latest FY Revenue") or 1)
                    if current_gm > prior_gm:
                        sig8 = 1
                except:
                    pass
            
            # Signal 9: Change in Asset Turnover > 0 (Sales / Total Assets)
            if idx + 1 < len(ticker_df):
                try:
                    prior_ato = (ticker_df.iloc[idx + 1].get("Latest FY Revenue") or 0) / \
                               (ticker_df.iloc[idx + 1].get("Total Assets") or 1)
                    current_ato = (row.get("Latest FY Revenue") or 0) / (row.get("Total Assets") or 1)
                    if current_ato > prior_ato:
                        sig9 = 1
                except:
                    pass
            
            f_score_data.append((orig_idx, sig1[orig_idx] + sig2[orig_idx] + sig3 + sig4 + sig5 + sig6 + sig7 + sig8 + sig9))
    
    # Build F_Score series from collected data
    f_score_dict = dict(f_score_data)
    df_["F_Score"] = df_.index.map(lambda x: f_score_dict.get(x, 0))


    # Historical Market Cap: the pull computes shares × price per year but this
    # frequently fails for non-US tickers (tz issues, missing share data).
    # Where a year has no Market Cap we do NOT forward/back-fill — that would
    # silently misrepresent the data. Ratios for those years will show N/A,
    # which is correct. Fix is in yfinance_pull.py share lookup robustness.
    # The most-recent year always has market_cap_converted from info["marketCap"]
    # which is reliable.

    df_ = df_.sort_values(
        by=["Ticker", "Year"], ascending=[True, False]
    ).reset_index(drop=True)

    return df_


# ── Formatting layer (strings for UI display) ─────────────────────────────────

CURRENCY_COLS = [
    "Market Cap", "Total Assets", "Total Current Assets", "Total Liabilities",
    "Total Investments", "Total Goodwill and Intangibles", "Total Equity",
    "NCAV", "NCAV_Inv", "Book_Value", "Tangible_Book_Value",
    "Latest FY Net Income", "TTM Net Income",
]

RATIO_COLS = [
    "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
    "Price_NCAV_Ratio", "Price_NCAV_Inv_Ratio",
    "PE_Ratio", "PE_Ratio_TTM", "Z_Score", "Beta",
]

PERCENTAGE_COLS = ["ROE", "ROE_5YR", "ROA"]

SCORE_COLS = ["F_Score"]


def _fmt_year(val) -> str:
    """Convert a Year value (int, float, Int64) to a clean 4-digit string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    try:
        return str(int(float(str(val))))
    except (ValueError, TypeError):
        return str(val)


def apply_formatting(df_: pd.DataFrame) -> pd.DataFrame:
    """
    Format all numeric columns to display strings.
    Call this only for UI display — never before writing to parquet.
    Operates on a copy so the caller's numeric df is not mutated.
    """
    df_ = df_.copy()

    # Year is stored as Int64 in parquet — convert to clean string before UI renders it
    if "Year" in df_.columns:
        df_["Year"] = df_["Year"].map(_fmt_year)

    for col in CURRENCY_COLS:
        if col in df_.columns:
            df_[col] = df_[col].map(format_currency)

    for col in RATIO_COLS:
        if col in df_.columns:
            df_[col] = df_[col].map(format_ratio)

    for col in PERCENTAGE_COLS:
        if col in df_.columns:
            df_[col] = df_[col].map(format_percentage)

    for col in SCORE_COLS:
        if col in df_.columns:
            df_[col] = df_[col].map(format_score)

    return df_


# ── Combined entry point (backwards compatible) ───────────────────────────────

def create_calcs(df_: pd.DataFrame) -> pd.DataFrame:
    """
    Apply calculations then formatting in one call.
    Kept for backwards compatibility — any existing code calling
    create_calcs() will continue to work unchanged.

    Note: the returned DataFrame contains formatted strings, not floats.
    Do NOT pass this output to the cache layer — use apply_calcs() instead.
    """
    return apply_formatting(apply_calcs(df_))
