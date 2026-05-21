"""
debug_refresh.py: Test refresh with DEBUG logging enabled
"""

import logging
import sys
from pathlib import Path

# Setup DEBUG logging BEFORE importing other modules
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(name)s %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

from config import project_root, ticker_list
from src.grahamquant.yfinance_pull import pull_yf_ticker_data
from src.grahamquant.formulas_calcs import create_calcs
from src.grahamquant.cache_manager import CacheManager
from src.grahamquant.ticker_registry import get_active_regions

log = logging.getLogger(__name__)

def _progress(ticker, idx, total, status):
    bar_filled = int((idx / total) * 30)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    symbol = {"ok": "✓", "failed": "✗", "empty": "–", "skipped": "→"}.get(status, " ")
    print(f"\r  [{bar}] {idx:>3}/{total}  {symbol} {ticker:<15}", end="", flush=True)
    if idx == total:
        print()

def main():
    data_dir = project_root / "data"
    cache = CacheManager(
        data_dir=data_dir,
        pull_fn=pull_yf_ticker_data,
        calc_fn=create_calcs,
    )
    
    print("\nRefreshing HK region with DEBUG logging...")
    result = cache.refresh_region("HK", force=True, progress_cb=_progress)
    print(f"\nDone — {result.get('ok',0)} ok / {result.get('failed',0)} failed / "
          f"{result.get('empty',0)} empty\n")

if __name__ == "__main__":
    main()
