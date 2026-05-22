"""
debug/refresh_and_test.py

Debug script to refresh a single region and test Z-Score/F-Score calculations.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import ticker_list
from src.grahamquant.yfinance_pull import pull_yf_ticker_data
from src.grahamquant.formulas_calcs import apply_calcs, apply_formatting
from src.grahamquant.ticker_registry import get_tickers_by_region

# Test with just a few US tickers first
test_tickers = ["AAPL", "MSFT", "JPM"]

print("\n" + "="*80)
print("Testing Z-Score and F-Score calculation")
print("="*80 + "\n")

print(f"Pulling data for: {test_tickers}")
try:
    raw_df = pull_yf_ticker_data(test_tickers)
    print(f"\n✓ Successfully pulled {len(raw_df)} rows")
    print(f"Columns: {list(raw_df.columns)}")
    
    print("\nFirst few rows (raw):")
    print(raw_df[["Ticker", "Year", "Latest FY Operating Income", "Latest FY Net Income", "Market Cap"]].head())
    
    print("\n" + "-"*80)
    print("Applying calculations...")
    calc_df = apply_calcs(raw_df)
    
    print(f"✓ Calculations applied")
    print(f"Columns: {list(calc_df.columns)}")
    
    print("\nZ-Score and F-Score columns:")
    z_f_cols = ["Ticker", "Year", "Z_Score", "F_Score", "ROE", "ROA"]
    print(calc_df[[c for c in z_f_cols if c in calc_df.columns]].head(10))
    
    print("\n" + "-"*80)
    print("Formatting for display...")
    fmt_df = apply_formatting(calc_df)
    
    print(f"✓ Formatting applied")
    print("\nFormatted Z-Score and F-Score:")
    print(fmt_df[["Ticker", "Year", "Z_Score", "F_Score", "ROE", "ROA"]].head(10))
    
    print("\n✓ All operations completed successfully!")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
