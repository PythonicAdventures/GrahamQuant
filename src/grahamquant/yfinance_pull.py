"""
yfinance_pull.py: This function engages in pulling the initial data needed for analysis.
Helper functions for dealing with scalars and timestamps also included.

"""
# Import libaries
import yfinance as yf
import pandas as pd
import numpy as np
import warnings

# Suppress FutureWarnings that originate inside yfinance internals.
# These come from yfinance's own history.py (empty Series dtype) and
# are not actionable from user code — safe to filter permanently.
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module="yfinance",
)

def _to_naive(ts):
    """Convert any Timestamp to tz-naive. Aware => tz_convert(None), naive => passthrough."""
    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
        return ts.tz_convert(None)
    return ts


def _scalar(val):
    """Safely extract a scalar from a value that might be a Series or ndarray.

    yfinance occasionally returns a single-element Series instead of a scalar
    for balance sheet line items (e.g. Ordinary Shares Number). Evaluating
    `if series_val` raises 'truth value of a Series is ambiguous' and crashes
    the whole ticker. This helper collapses it to a plain Python float or None.
    """
    if val is None:
        return None
    if isinstance(val, pd.Series):
        val = val.iloc[0] if not val.empty else None
    if isinstance(val, np.ndarray):
        val = val.flat[0] if val.size > 0 else None
    if val is not None and pd.isna(val):
        return None
    return val


def pull_yf_ticker_data(ticker_list: list):
    """Pull all available annual balance sheet + income data from Yahoo Finance.
    Returns a multi-row DataFrame structured by Ticker and Year.
    """
    extracted_data = []

    for ticker_str in ticker_list:
        print(f"Fetching historical data for: {ticker_str}...")
        try:
            ticker = yf.Ticker(ticker_str)
            info = ticker.info

            # --- Currencies ---
            raw_trading = info.get("currency", None)
            raw_financial = info.get("financialCurrency", None)
            trading_curr = raw_trading.upper() if raw_trading else None
            financial_curr = raw_financial.upper() if raw_financial else None

            market_cap = info.get("marketCap", None)

            # --- FX rate ---
            fx_rate = 1.0
            if trading_curr and financial_curr and trading_curr != financial_curr:
                fx_ticker_str = f"{trading_curr}{financial_curr}=X"
                try:
                    fx_data = yf.Ticker(fx_ticker_str).history(period="1d")
                    if not fx_data.empty:
                        fx_rate = fx_data["Close"].iloc[-1]
                except Exception:
                    pass

            market_cap_converted = (market_cap * fx_rate) if market_cap is not None else None

            # --- Historical shares outstanding series ---
            shares_series = None
            try:
                shares_series = ticker.get_shares_full(start="2015-01-01", end=None)
            except Exception:
                pass

            # --- TTM Net Income ---
            ttm_net_inc = None
            try:
                ttm_inc = ticker.ttm_income_stmt
                if isinstance(ttm_inc, tuple): ttm_inc = ttm_inc[0]
                if not isinstance(ttm_inc, pd.DataFrame): ttm_inc = pd.DataFrame(ttm_inc)
                if not ttm_inc.empty and "Net Income" in ttm_inc.index:
                    ttm_net_inc = _scalar(ttm_inc.loc["Net Income"].iloc[0])
            except Exception:
                pass

            if ttm_net_inc is None:
                try:
                    q_inc = ticker.quarterly_income_stmt
                    if isinstance(q_inc, tuple): q_inc = q_inc[0]
                    if not isinstance(q_inc, pd.DataFrame): q_inc = pd.DataFrame(q_inc)
                    if not q_inc.empty and "Net Income" in q_inc.index:
                        ttm_net_inc = q_inc.loc["Net Income"].iloc[:4].sum()
                        if pd.isna(ttm_net_inc): ttm_net_inc = None
                except Exception:
                    pass

            # --- Annual statements ---
            raw_bs = ticker.balance_sheet
            raw_inc = ticker.income_stmt
            if isinstance(raw_bs, tuple): raw_bs = raw_bs[0]
            if isinstance(raw_inc, tuple): raw_inc = raw_inc[0]
            annual_bs = raw_bs if isinstance(raw_bs, pd.DataFrame) else pd.DataFrame(raw_bs)
            annual_inc = raw_inc if isinstance(raw_inc, pd.DataFrame) else pd.DataFrame(raw_inc)

            if not annual_bs.empty:
                for report_date in annual_bs.columns:
                    date_str = str(report_date.date())
                    year_val = report_date.year
                    bs_col = annual_bs[report_date]
                    report_date_naive = _to_naive(report_date)

                    total_assets              = _scalar(bs_col.get("Total Assets"))
                    current_assets            = _scalar(bs_col.get("Current Assets"))
                    total_liabilities         = _scalar(bs_col.get("Total Liabilities Net Minority Interest"))
                    total_goodwill_intangibles= _scalar(bs_col.get("Goodwill And Other Intangible Assets"))
                    total_equity              = _scalar(bs_col.get("Common Stock Equity"))
                    total_investments         = _scalar(
                        bs_col.get("Investment Properties") or bs_col.get("Investments And Advances")
                    )

                    # --- Historical Market Cap ---
                    hist_market_cap = None

                    # Strategy A: get_shares_full time series
                    shares_outstanding = None
                    if shares_series is not None and not shares_series.empty:
                        try:
                            closest_share_date = min(
                                shares_series.index,
                                key=lambda x: abs(_to_naive(x) - report_date_naive),
                            )
                            if abs((_to_naive(closest_share_date) - report_date_naive).days) <= 180:
                                shares_outstanding = _scalar(shares_series.loc[closest_share_date])
                        except Exception:
                            pass

                    # Strategy B: Ordinary Shares Number from balance sheet
                    if shares_outstanding is None:
                        shares_outstanding = _scalar(bs_col.get("Ordinary Shares Number"))

                    # Compute hist market cap from shares + historical close price
                    # _scalar() ensures shares_outstanding is a plain Python scalar,
                    # so the `is not None` check is safe — no Series ambiguity.
                    if shares_outstanding is not None:
                        try:
                            start_search = report_date_naive - pd.Timedelta(days=3)
                            end_search   = report_date_naive + pd.Timedelta(days=4)
                            price_hist = ticker.history(start=start_search, end=end_search)
                            if not price_hist.empty:
                                price_hist.index = price_hist.index.map(_to_naive)
                                closest_price_idx = min(
                                    price_hist.index,
                                    key=lambda x: abs(x - report_date_naive),
                                )
                                close_price = price_hist.loc[closest_price_idx, "Close"]
                                hist_market_cap = shares_outstanding * close_price * fx_rate
                        except Exception:
                            pass

                    # --- Income statement matching ---
                    fy_net_inc = None
                    if not annual_inc.empty:
                        if report_date in annual_inc.columns:
                            fy_net_inc = _scalar(annual_inc[report_date].get("Net Income"))
                        else:
                            closest_col = min(
                                annual_inc.columns,
                                key=lambda x: abs(x - report_date),
                            )
                            if abs((closest_col - report_date).days) <= 7:
                                fy_net_inc = _scalar(annual_inc[closest_col].get("Net Income"))

                    is_latest = report_date == annual_bs.columns[0]
                    final_market_cap = market_cap_converted if is_latest else hist_market_cap
                    if is_latest and final_market_cap is None:
                        final_market_cap = hist_market_cap

                    extracted_data.append({
                        "Ticker":                      ticker_str,
                        "Year":                        year_val,
                        "Report Date":                 date_str,
                        "Trading Currency":            trading_curr,
                        "Financial Currency":          financial_curr,
                        "Market Cap":                  final_market_cap,
                        "Total Assets":                total_assets,
                        "Total Current Assets":        current_assets,
                        "Total Goodwill and Intangibles": total_goodwill_intangibles,
                        "Total Liabilities":           total_liabilities,
                        "Total Equity":                total_equity,
                        "Total Investments":           total_investments,
                        "Latest FY Net Income":        fy_net_inc,
                        "TTM Net Income":              ttm_net_inc if is_latest else None,
                    })
            else:
                print(f"   No annual balance sheet found for {ticker_str}")

        except Exception as e:
            print(f"Error fetching data for {ticker_str}: {e}")

    df = pd.DataFrame(extracted_data)
    if not df.empty:
        df = df.sort_values(by=["Ticker", "Year"], ascending=[True, False]).reset_index(drop=True)
    return df