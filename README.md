# QuantGraham (README is WIP as development progresses)

Note Financial Disclaimer: The content provided is strictly for informational and educational purposes. It does not constitute, and should not be construed as, investment, financial, legal, or tax advice.Always conduct your own due diligence and consider consulting a certified financial advisor before making any financial or investment decisions.

## Introduction
A quantiative stock screener and analytics tool for Deep Value/Graham &amp; Dodd type investors backed by the yfinance API. Deep Value investing is an investing philosophy originated from Benjamin Graham and David Dodd in the early 20th century. These authors written books that have influenced the value investing world such as "Security Analysis" and the more famed "The Intelligent Investor". Well known successful investors have employed their strategy such as Warren Buffett during his early years, Peter Cundill, Walter Schloss and many others. 

The iconic investment for this strategy is buying what is called a "net-net" which is a stock that is selling on a price per share basis less than all total current assets minus all total liabilities as a per share value which is one of the most conservative estimates for intrinsic value of an enterprise. Example: ABC Stock is selling at $1/sh with net current asset value (NCAV) per share is at $2. 

## Purpose
The reason for developing this tool was to create a small and light-weight Python based app that would allow for investment screening and discovery of stocks trading around certain metrics utilized by deep value investors leveraging the yfinance Python package.

## Features (WIP)
- Calculation of relevant metrics based on yfinance information utilizing recent financials or balance sheet information.
- Price charts with valuation comparisons
- Watchlist tracking
- Market Cap conversion into financial statement currency

## Formulas and Metrics
- Market Cap: Direct pull
- Net Current Asset Value (NCAV): Total Current Assets - Total Liabilities
- NCAV + Investments: Total Current Assets - Total Liabilities + Total Investments
- Book Value: Total Assets - Total Liabilities
- Tangible Book Value: Total Assets - Total Liabilities - Goodwill & Intangible Assets
- Price/NCAV Ratio: Market Cap / NCAV
- Price/NCAV + Investments Ratio: Market Cap / NCAV + Investments
- Price/Book Ratio: Market Cap / Book Value
- Price/Tangible Book Ratio: Market Cap / Tangible Book Value
- Z-Score (Altman): 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MVE/TL) + 1.0*(Sales/TA)
- F-Score (Piotroski): Composite 9-signal profitability and quality metric (0-9)
- Beta: Volatility measure relative to market
- Price 1 Year Low: WIP
- Price 3 Year Low: WIP
- Price 5 Year Low: WIP
- Price 10 Year Low: WIP

## Repository Structure

<!-- readme-tree start -->
```
.
├── .github
│   └── workflows
│       └── auto-tree.yml
├── .gitignore
├── README.md
├── SCREENER_GUIDE.md
├── config.py
├── data
│   ├── cache
│   │   ├── region=HK
│   │   │   └── data.parquet
│   │   ├── region=JP
│   │   │   └── data.parquet
│   │   ├── region=UK
│   │   │   └── data.parquet
│   │   └── region=US
│   │       └── data.parquet
│   └── manifest.parquet
├── debug
│   ├── check_market_cap.py
│   ├── debug_refresh.py
│   ├── debug_tz.py
│   ├── refresh_and_test.py
│   ├── test_price_fixed.py
│   ├── test_price_history.py
│   └── test_single_ticker.py
├── debug.py
├── main.py
├── notebooks
│   ├── cache_test.ipynb
│   ├── yfinance_test.ipynb
│   ├── yfinance_ver2.1.ipynb
│   ├── yfinance_ver2.2.ipynb
│   └── yfinance_ver2.ipynb
├── repair
│   └── rebuild_manifest.py
├── src
│   ├── __init__.py
│   └── grahamquant
│       ├── cache_manager.py
│       ├── formulas_calcs.py
│       ├── ticker_registry.py
│       ├── ui.py
│       ├── ui_new.py
│       └── yfinance_pull.py
└── tree.bak

14 directories, 33 files
```
<!-- readme-tree end -->


