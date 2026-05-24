"""
config.py: This file contains general static variables and project_root
directory
"""

from pathlib import Path
from src.grahamquant.ticker_registry import get_all_tickers

project_root = Path(__file__).resolve().parent

# Ticker list is dynamically built from the registry (active regions only).
# To add new tickers: expand REGISTRY in ticker_registry.py, then run:
#   python main.py --refresh          # to fetch and cache new data
#   python main.py                    # to launch UI with updated cache
ticker_list = get_all_tickers()