"""
main.py: Starting point to engage the application.
"""
from config import project_root, ticker_list
from src.grahamquant.yfinance_pull import pull_yf_ticker_data
from src.grahamquant.formulas_calcs import create_calcs
from src.grahamquant.ui import launch

if __name__ == "__main__":
    launch(
        ticker_list=ticker_list,
        pull_fn=pull_yf_ticker_data,
        calc_fn=create_calcs,
    )



