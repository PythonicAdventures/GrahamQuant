"""
Test price history retrieval for a single ticker across multiple years
"""
import yfinance as yf
import pandas as pd
from datetime import datetime

def _to_naive(ts):
    """Convert any Timestamp to tz-naive"""
    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
        return ts.tz_convert(None)
    return ts

ticker_str = "AAPL"
print(f"\nTesting price history for {ticker_str}")

ticker = yf.Ticker(ticker_str)

# Get all annual balance sheet dates
annual_bs = ticker.balance_sheet
if isinstance(annual_bs, tuple): 
    annual_bs = annual_bs[0]

print(f"\nBalance sheet dates available: {len(annual_bs.columns)}")
for i, report_date in enumerate(annual_bs.columns[:5]):  # Show first 5
    report_date_naive = _to_naive(pd.Timestamp(report_date))
    print(f"  {i}: {report_date_naive.date()}")
    
    # Try to fetch price history around that date
    start_search = report_date_naive - pd.Timedelta(days=30)
    end_search   = report_date_naive + pd.Timedelta(days=30)
    
    print(f"      Searching for price data: {start_search.date()} to {end_search.date()}")
    price_hist = ticker.history(start=start_search, end=end_search)
    
    if not price_hist.empty:
        # Find closest date
        price_hist.index = price_hist.index.map(_to_naive)
        closest_date = min(price_hist.index, key=lambda x: abs(x - report_date_naive))
        close_price = price_hist.loc[closest_date, "Close"]
        days_away = abs((closest_date - report_date_naive).days)
        print(f"      ✓ Found price: {close_price:.2f} on {closest_date.date()} (±{days_away} days)")
        print(f"        Price data range in window: {price_hist.index.min().date()} to {price_hist.index.max().date()}")
    else:
        print(f"      ✗ No price data found!")
        print(f"        (This is the problem - price history fetch returned nothing)")
    print()
