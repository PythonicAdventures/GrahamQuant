"""
Debug timezone handling in yfinance data
"""
import yfinance as yf
import pandas as pd

ticker_str = "AAPL"
ticker = yf.Ticker(ticker_str)

# Test balance sheet
print("Balance sheet columns:")
annual_bs = ticker.balance_sheet
if isinstance(annual_bs, tuple): 
    annual_bs = annual_bs[0]

for i, col in enumerate(list(annual_bs.columns)[:3]):
    print(f"  Type: {type(col)}, Value: {col}, TZ info: {col.tzinfo if hasattr(col, 'tzinfo') else 'N/A'}")

# Test price history
print("\nPrice history index:")
report_date = list(annual_bs.columns)[0]
start_search = report_date - pd.Timedelta(days=30)
end_search = report_date + pd.Timedelta(days=30)

print(f"  Searching {start_search} to {end_search}")
price_hist = ticker.history(start=start_search, end=end_search)
print(f"  Found {len(price_hist)} rows")

if not price_hist.empty:
    for i, idx in enumerate(list(price_hist.index)[:3]):
        print(f"  Type: {type(idx)}, Value: {idx}, TZ info: {idx.tzinfo if hasattr(idx, 'tzinfo') else 'N/A'}")

# Try tz_localize/tz_convert approaches
print("\nTesting timestamp conversion methods:")
ts = report_date
print(f"  Original: {ts}, TZ: {ts.tzinfo}")

# Method 1: tz_convert(None)
if ts.tzinfo:
    ts_naive_1 = ts.tz_convert(None)
    print(f"  After tz_convert(None): {ts_naive_1}, TZ: {ts_naive_1.tzinfo}")

# Method 2: replace(tzinfo=None)  
ts_naive_2 = ts.replace(tzinfo=None)
print(f"  After replace(tzinfo=None): {ts_naive_2}, TZ: {ts_naive_2.tzinfo}")

# Method 3: normalize and convert
if hasattr(ts, 'tz_localize'):
    try:
        ts_utc = ts.tz_localize('UTC') if ts.tzinfo is None else ts
        ts_naive_3 = ts_utc.tz_convert('UTC').tz_localize(None)
        print(f"  After tz_localize/convert: {ts_naive_3}, TZ: {ts_naive_3.tzinfo}")
    except Exception as e:
        print(f"  tz_localize approach failed: {e}")
