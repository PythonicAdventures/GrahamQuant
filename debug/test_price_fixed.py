"""
Test the fixed _to_naive function with actual price history lookup
"""
import yfinance as yf
import pandas as pd

def _to_naive(ts):
    """Convert any Timestamp to tz-naive, handling both tz-aware and tz-naive."""
    if ts is None:
        return None
    # For pandas Timestamp with tzinfo
    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
        # Use tz_localize(None) to drop the timezone info (not convert)
        if hasattr(ts, 'tz_localize'):
            return ts.tz_localize(None)
        # Fallback for datetime objects without tz_localize
        return ts.replace(tzinfo=None)
    # Already naive
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
    print(f"\n  Report {i}: {report_date_naive.date()}")
    
    # Try to fetch price history around that date
    start_search = report_date_naive - pd.Timedelta(days=30)
    end_search   = report_date_naive + pd.Timedelta(days=30)
    
    print(f"    Searching: {start_search.date()} to {end_search.date()}")
    price_hist = ticker.history(start=start_search, end=end_search)
    
    if not price_hist.empty:
        # Convert index to naive datetimes
        price_hist.index = pd.DatetimeIndex([_to_naive(ts) for ts in price_hist.index])
        
        # Find closest date
        closest_date = min(price_hist.index, key=lambda x: abs(x - report_date_naive))
        close_price = price_hist.loc[closest_date, "Close"]
        days_away = abs((closest_date - report_date_naive).days)
        price_str = f"{close_price:.2f}"
        print(f"    Found: price  on {closest_date.date()} (+/- {days_away} days)")
    else:
        print(f"    No price data found")
