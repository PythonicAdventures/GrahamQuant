import pandas as pd
from pathlib import Path

data_dir = Path("data/cache")
pq_file = data_dir / "region=HK" / "data.parquet"
df = pd.read_parquet(pq_file)

print("\n" + "="*60)
print("HK Market Cap Analysis")
print("="*60)

null_rates = df[["Ticker", "Year", "Market Cap"]].groupby("Ticker")["Market Cap"].apply(
    lambda x: f"{x.isna().sum()}/{len(x)} null"
)
print("\nNull rates by ticker:")
print(null_rates)

print("\nDetailed breakdown:")
for ticker in sorted(df["Ticker"].unique()):
    ticker_data = df[df["Ticker"] == ticker][["Year", "Report Date", "Market Cap", "Total Equity"]].sort_values("Year", ascending=False)
    print(f"\n{ticker}:")
    print(ticker_data.to_string(index=False))
