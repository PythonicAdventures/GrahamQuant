"""
main.py: Starting point to engage the application.

Usage
-----
  python main.py                      # launch UI (uses cache)
  python main.py --refresh            # force full refresh of all active regions, then launch UI
  python main.py --refresh-region JP  # refresh one region, then launch UI
  python main.py --refresh-only       # refresh without launching UI (for scheduled runs)
  python main.py --screen             # print net-net screen to stdout and exit
"""

import argparse
import logging
import sys

from config import project_root, ticker_list
from src.grahamquant.yfinance_pull import pull_yf_ticker_data
from src.grahamquant.formulas_calcs import create_calcs
from src.grahamquant.cache_manager import CacheManager
from src.grahamquant.ticker_registry import get_active_regions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _progress(ticker, idx, total, status):
    bar_filled = int((idx / total) * 30)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    symbol = {"ok": "✓", "failed": "✗", "empty": "–", "skipped": "→"}.get(status, " ")
    print(f"\r  [{bar}] {idx:>3}/{total}  {symbol} {ticker:<15}", end="", flush=True)
    if idx == total:
        print()


def main():
    parser = argparse.ArgumentParser(description="GrahamQuant — deep value screen")
    parser.add_argument("--refresh",        action="store_true", help="Force full data refresh")
    parser.add_argument("--refresh-region", metavar="REGION",   help="Refresh one region (e.g. JP)")
    parser.add_argument("--refresh-only",   action="store_true", help="Refresh without launching UI")
    parser.add_argument("--screen",         action="store_true", help="Print net-net screen and exit")
    args = parser.parse_args()

    data_dir = project_root / "data"
    cache = CacheManager(
        data_dir=data_dir,
        pull_fn=pull_yf_ticker_data,
        calc_fn=create_calcs,
    )

    # ── Refresh ────────────────────────────────────────────────────────────────
    if args.refresh_region:
        region = args.refresh_region.upper()
        if region not in get_active_regions():
            print(f"Unknown or inactive region: {region}. Active: {get_active_regions()}")
            sys.exit(1)
        print(f"\nRefreshing region: {region}")
        result = cache.refresh_region(region, force=True, progress_cb=_progress)
        print(f"\nDone — {result.get('ok',0)} ok / {result.get('failed',0)} failed / "
              f"{result.get('empty',0)} empty\n")

    elif args.refresh:
        print("\nRefreshing all active regions…")
        for region in get_active_regions():
            print(f"\n── {region} ──────────────────────────────────")
            result = cache.refresh_region(region, force=True, progress_cb=_progress)
            print(f"   {result.get('ok',0)} ok / {result.get('failed',0)} failed / "
                  f"{result.get('empty',0)} empty")
        print("\nAll regions refreshed.\n")

    else:
        manifest = cache.get_manifest()
        if manifest.empty:
            print("\n⚠  No cached data found. Run with --refresh to download data first.\n")

    # ── Screen mode ────────────────────────────────────────────────────────────
    if args.screen:
        print("\n── Net-Net Screen (P/NCAV ≤ 1, latest year) ────────────────────")
        results = cache.screen(max_pb=1.5, max_pncav=1.0)
        if results.empty:
            print("No stocks currently pass the net-net screen in cached data.")
        else:
            cols = ["Ticker", "Region", "Year", "Market Cap",
                    "Price_NCAV_Ratio", "Price_Book_Ratio", "ROE"]
            print(results[[c for c in cols if c in results.columns]].to_string(index=False))
        print()

        print("── Regional Breadth ─────────────────────────────────────────────")
        breadth = cache.regional_breadth()
        if not breadth.empty:
            print(breadth.to_string(index=False))
        print()

        if args.refresh_only:
            sys.exit(0)
        return

    if args.refresh_only:
        sys.exit(0)

    # ── Launch UI ──────────────────────────────────────────────────────────────
    from src.grahamquant.ui_new import launch
    launch(
        ticker_list=ticker_list,
        pull_fn=pull_yf_ticker_data,
        calc_fn=create_calcs,
        cache=cache,
    )


if __name__ == "__main__":
    main()
