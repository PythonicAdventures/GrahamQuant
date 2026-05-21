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
    "PE_Ratio", "PE_Ratio_TTM",
]

PERCENTAGE_COLS = ["ROE", "ROE_5YR"]


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
