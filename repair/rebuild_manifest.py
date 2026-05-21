"""
rebuild_manifest.py

Run this once to rebuild the manifest.parquet from existing cache files.
Place in project root and run:  python rebuild_manifest.py
"""
from pathlib import Path
from datetime import datetime

import pandas as pd

from config import project_root

data_dir      = project_root / "data"
cache_dir     = data_dir / "cache"
manifest_path = data_dir / "manifest.parquet"

rows = []

for region_dir in sorted(cache_dir.iterdir()):
    if not region_dir.is_dir():
        continue

    # Extract region code from folder name "region=JP" -> "JP"
    region = region_dir.name.split("=")[-1]
    parquet_file = region_dir / "data.parquet"

    if not parquet_file.exists():
        print(f"  {region}: no data.parquet found, skipping.")
        continue

    try:
        df = pd.read_parquet(parquet_file)
        print(f"  {region}: {len(df)} rows, columns: {list(df.columns[:6])}...")
    except Exception as e:
        print(f"  {region}: failed to read parquet — {e}")
        continue

    if df.empty:
        print(f"  {region}: empty dataframe, skipping.")
        continue

    # One manifest row per ticker
    ticker_col = "Ticker" if "Ticker" in df.columns else None
    if ticker_col is None:
        print(f"  {region}: no Ticker column found, skipping.")
        continue

    for ticker, grp in df.groupby(ticker_col):
        year_col = "Year" if "Year" in grp.columns else None
        years_available = grp[year_col].nunique() if year_col else len(grp)

        rows.append({
            "Ticker":          ticker,
            "Region":          region,
            "Status":          "ok",
            "Last Updated":    datetime.now().isoformat(timespec="seconds"),
            "Years Available": years_available,
            "Error":           "",
        })
        print(f"    {ticker}: {years_available} year(s)")

if not rows:
    print("\nNo data found in cache — nothing to write.")
else:
    manifest = pd.DataFrame(rows)
    manifest["Years Available"] = pd.to_numeric(
        manifest["Years Available"], errors="coerce"
    ).astype("Int64")

    manifest.to_parquet(manifest_path, index=False, compression="snappy")
    print(f"\n✓ Manifest rebuilt: {len(manifest)} tickers written to {manifest_path}")
    print(manifest.to_string(index=False))
