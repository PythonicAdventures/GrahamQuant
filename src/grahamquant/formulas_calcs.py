"""
formulas_calcs.py: This script layers on calculations and formulas required
for deep value analysis and screening. Helper functions to convert 1,000s,
ratios and percentages.
"""

# Import libraries
import pandas as pd
import numpy as np

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

def create_calcs(df_):
    df_ = df_.sort_values(by=["Ticker", "Year"], ascending=[True, True]).copy()

    # Only fill columns where 0 is a correct default (nothing held = 0).
    # All others stay NaN so ratios propagate NaN => 'N/A' after formatting.
    df_["Total Investments"]              = df_["Total Investments"].fillna(0)
    df_["Total Goodwill and Intangibles"] = df_["Total Goodwill and Intangibles"].fillna(0)

    df_ = df_.assign(
        NCAV=lambda d: d["Total Current Assets"] - d["Total Liabilities"],
        NCAV_Inv=lambda d: d["Total Current Assets"] - d["Total Liabilities"] + d["Total Investments"],
        Book_Value=lambda d: d["Total Assets"] - d["Total Liabilities"],
        Tangible_Book_Value=lambda d: (
            d["Total Assets"] - d["Total Liabilities"] - d["Total Goodwill and Intangibles"]
        ),
        ROE=lambda d: d["Latest FY Net Income"] / d["Total Equity"].replace(0, np.nan),
        Price_Book_Ratio=lambda d:          d["Market Cap"] / d["Book_Value"].replace(0, np.nan),
        Price_Tangible_Book_Ratio=lambda d: d["Market Cap"] / d["Tangible_Book_Value"].replace(0, np.nan),
        Price_NCAV_Ratio=lambda d:          d["Market Cap"] / d["NCAV"].replace(0, np.nan),
        Price_NCAV_Inv_Ratio=lambda d:      d["Market Cap"] / d["NCAV_Inv"].replace(0, np.nan),
        PE_Ratio=lambda d:                  d["Market Cap"] / d["Latest FY Net Income"].replace(0, np.nan),
        PE_Ratio_TTM=lambda d:              d["Market Cap"] / d["TTM Net Income"].replace(0, np.nan),
    )

    df_ = df_.sort_values(by=["Ticker", "Year"], ascending=[True, False]).reset_index(drop=True)

    currency_cols = [
        "Market Cap", "Total Assets", "Total Current Assets", "Total Liabilities",
        "Total Investments", "Total Goodwill and Intangibles", "Total Equity",
        "NCAV", "NCAV_Inv", "Book_Value", "Tangible_Book_Value",
        "Latest FY Net Income", "TTM Net Income",
    ]
    for col in currency_cols:
        if col in df_.columns:
            df_[col] = df_[col].map(format_currency)

    ratio_cols = [
        "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
        "Price_NCAV_Ratio", "Price_NCAV_Inv_Ratio",
        "PE_Ratio", "PE_Ratio_TTM",
    ]
    for col in ratio_cols:
        if col in df_.columns:
            df_[col] = df_[col].map(format_ratio)

    for col in ["ROE", "ROE_5YR"]:
        if col in df_.columns:
            df_[col] = df_[col].map(format_percentage)

    return df_
