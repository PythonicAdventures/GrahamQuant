"""
Test refresh on single US ticker to see market cap calculation
"""
from src.grahamquant.yfinance_pull import pull_yf_ticker_data

print("\nPulling data for AAPL...")
df = pull_yf_ticker_data(["AAPL"])

print("\nResult:")
print(df[["Ticker", "Year", "Report Date", "Market Cap", "Total Equity"]].to_string(index=False))
