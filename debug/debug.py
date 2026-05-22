import pandas as pd
from pathlib import Path

data_dir = Path("data/cache")
for region in ["US", "JP", "HK", "UK"]:
    pq_file = data_dir / f"region={region}" / "data.parquet"
    if pq_file.exists():
        df = pd.read_parquet(pq_file)
        null_rates = df[["Ticker", "Year", "Market Cap"]].groupby("Ticker")["Market Cap"].apply(
            lambda x: f"{x.isna().sum()}/{len(x)} null"
        )
        print(f"\n{region}:\n{null_rates}")