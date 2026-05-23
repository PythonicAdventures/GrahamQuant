"""
yfinance_pull.py: This function engages in pulling the initial data needed for analysis.
Helper functions for dealing with scalars and timestamps also included.

"""
# Import libaries
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import logging

from .ticker_registry import get_region_for_ticker

logger = logging.getLogger(__name__)

# Suppress FutureWarnings that originate inside yfinance internals.
# These come from yfinance's own history.py (empty Series dtype) and
# are not actionable from user code — safe to filter permanently.
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module="yfinance",
)

def _to_naive(ts):
    """Convert any Timestamp to tz-naive, handling both tz-aware and tz-naive."""
    if ts is None:
        return None
    # For pandas Timestamp with tzinfo
    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
        # Use tz_localize(None) to drop the timezone info (not convert)
        if hasattr(ts, 'tz_localize'):
            return ts.tz_localize(None)
        # Fallback for datetime objects without tz_localize
        return ts.replace(tzinfo=None)
    # Already naive
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


def _calculate_historical_market_cap(ticker, report_date_naive, shares_outstanding, fx_rate, ticker_str=None, year=None):
    """
    Calculate historical market cap from shares outstanding and historical price.
    
    Strategies (in order):
    1. Fetch price from ±30 day window around report date (generous for non-trading days)
    2. Use closest trading day found in history
    3. Return None if price data unavailable
    
    Returns: market_cap (float) or None
    """
    if shares_outstanding is None or shares_outstanding <= 0:
        return None
    
    try:
        # Fetch a wider window to capture the closest trading day to report_date
        start_search = report_date_naive - pd.Timedelta(days=30)
        end_search   = report_date_naive + pd.Timedelta(days=30)
        
        print(f"        Fetching price for {ticker_str} {year} from {start_search.date()} to {end_search.date()}")
        price_hist = ticker.history(start=start_search, end=end_search)
        print(f"        Got {len(price_hist)} rows of price data")
        
        if price_hist.empty:
            print(f"        No price data in ±30 day window")
            logger.debug(f"{ticker_str} {year} ({report_date_naive.date()}): No price data in ±30 day window")
            return None
        
        # Convert DatetimeIndex to tz-naive if needed
        if price_hist.index.tz is not None:
            price_hist.index = price_hist.index.tz_localize(None)
        
        print(f"        Price data range: {price_hist.index.min().date()} to {price_hist.index.max().date()}")
        
        # Find the closest trading day to report_date
        closest_price_date = min(
            price_hist.index,
            key=lambda x: abs(x - report_date_naive),
        )
        close_price = price_hist.loc[closest_price_date, "Close"]
        
        if pd.isna(close_price) or close_price <= 0:
            print(f"        Invalid close price: {close_price}")
            logger.debug(f"{ticker_str} {year}: Invalid close price {close_price}")
            return None
        
        hist_market_cap = shares_outstanding * close_price * fx_rate
        days_away = abs((closest_price_date - report_date_naive).days)
        result = f"{hist_market_cap:.2e}"
        print(f"        ✓ Calc'd: {result} (shares={shares_outstanding:.2e}, price={close_price:.2f}, price_date={closest_price_date.date()}, days_away={days_away})")
        logger.debug(f"{ticker_str} {year}: Calc'd market cap = {hist_market_cap:.2e} (price_date={closest_price_date.date()}, days_away={days_away})")
        return hist_market_cap if hist_market_cap > 0 else None
        
    except Exception as e:
        print(f"        ✗ Exception: {e}")
        logger.debug(f"{ticker_str} {year}: Historical market cap calculation failed for {report_date_naive}: {e}")
        return None


def pull_yf_ticker_data(ticker_list: list):
    """Pull all available annual balance sheet + income data from Yahoo Finance.
    Returns a multi-row DataFrame structured by Ticker and Year.
    """
    extracted_data = []

    for ticker_str in ticker_list:
        print(f"Fetching historical data for: {ticker_str}...")
        try:
            region = get_region_for_ticker(ticker_str)
            ticker = yf.Ticker(ticker_str)
            info = ticker.info

            # --- Currencies ---
            raw_trading = info.get("currency", None)
            raw_financial = info.get("financialCurrency", None)
            trading_curr = raw_trading.upper() if raw_trading else None
            financial_curr = raw_financial.upper() if raw_financial else None

            # --- Company Info ---
            company_name = info.get("longName", info.get("shortName", None))
            industry = info.get("industry", None)
            sector = info.get("sector", None)

            market_cap = info.get("marketCap", None)

            # --- Beta ---
            beta = info.get("beta", None)
            
            # --- Dividend Yield ---
            dividend_yield = info.get("dividendYield", None)

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

            # --- Cash Flow Statement ---
            raw_cf = ticker.cash_flow
            if isinstance(raw_cf, tuple): raw_cf = raw_cf[0]
            annual_cf = raw_cf if isinstance(raw_cf, pd.DataFrame) else pd.DataFrame(raw_cf)

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
                    current_liabilities       = _scalar(bs_col.get("Current Liabilities"))
                    total_liabilities         = _scalar(bs_col.get("Total Liabilities Net Minority Interest"))
                    total_goodwill_intangibles= _scalar(bs_col.get("Goodwill And Other Intangible Assets"))
                    total_equity              = _scalar(bs_col.get("Common Stock Equity"))
                    retained_earnings         = _scalar(bs_col.get("Retained Earnings"))
                    total_investments         = _scalar(
                        bs_col.get("Investment Properties") or bs_col.get("Investments And Advances")
                    )
                    
                    # --- Asset Composition ---
                    cash                      = _scalar(bs_col.get("Cash And Cash Equivalents"))
                    receivables               = _scalar(bs_col.get("Accounts Receivable"))
                    inventory                 = _scalar(bs_col.get("Inventory"))
                    ppe                       = _scalar(bs_col.get("Property Plant Equipment"))
                    
                    # --- Debt and Cash ---
                    current_debt              = _scalar(bs_col.get("Current Debt"))
                    long_term_debt            = _scalar(bs_col.get("Long Term Debt"))
                    
                    # Total Debt = Current Debt + Long-term Debt (or use Total Liabilities as fallback)
                    total_debt = None
                    if current_debt is not None or long_term_debt is not None:
                        total_debt = (current_debt or 0) + (long_term_debt or 0)
                    
                    # Net Debt = Total Debt - Cash
                    net_debt = None
                    if total_debt is not None and cash is not None:
                        net_debt = total_debt - cash

                    # --- Historical Market Cap ---
                    # Multi-strategy approach to get shares outstanding:
                    
                    # Strategy A: Fetch shares from time series (most reliable for historical data)
                    shares_outstanding = None
                    shares_source = None
                    
                    if shares_series is not None and not shares_series.empty:
                        try:
                            # Find closest share date within 180 days
                            closest_share_date = min(
                                shares_series.index,
                                key=lambda x: abs(_to_naive(x) - report_date_naive),
                            )
                            days_diff = abs((_to_naive(closest_share_date) - report_date_naive).days)
                            if days_diff <= 180:
                                shares_outstanding = _scalar(shares_series.loc[closest_share_date])
                                if shares_outstanding is not None and shares_outstanding > 0:
                                    shares_source = "time_series"
                                    logger.debug(f"{ticker_str} {year_val}: Got shares from time_series ({shares_outstanding:.2e})")
                        except Exception as e:
                            logger.debug(f"{ticker_str} {year_val}: shares_series lookup failed: {e}")
                            pass

                    # Strategy B: Ordinary Shares Number from balance sheet
                    if shares_outstanding is None:
                        try:
                            shares_outstanding = _scalar(bs_col.get("Ordinary Shares Number"))
                            if shares_outstanding is not None and shares_outstanding > 0:
                                shares_source = "balance_sheet"
                                logger.debug(f"{ticker_str} {year_val}: Got shares from balance_sheet ({shares_outstanding:.2e})")
                        except Exception:
                            pass

                    # Strategy C: Common Stock from balance sheet (fallback)
                    if shares_outstanding is None:
                        try:
                            shares_outstanding = _scalar(bs_col.get("Common Stock"))
                            if shares_outstanding is not None and shares_outstanding > 0:
                                shares_source = "common_stock_value"
                                logger.debug(f"{ticker_str} {year_val}: Got shares from common_stock ({shares_outstanding:.2e})")
                        except Exception:
                            pass
                    
                    if shares_outstanding is None:
                        logger.debug(f"{ticker_str} {year_val}: No shares outstanding found from any strategy")

                    # Now calculate historical market cap using the shares we found
                    hist_market_cap = None
                    if shares_outstanding is not None and shares_outstanding > 0:
                        hist_market_cap = _calculate_historical_market_cap(
                            ticker, report_date_naive, shares_outstanding, fx_rate, 
                            ticker_str=ticker_str, year=year_val
                        )

                    # --- Income statement matching ---
                    fy_net_inc = None
                    fy_operating_income = None
                    fy_gross_profit = None
                    fy_revenue = None
                    fy_operating_cash_flow = None
                    fy_ebitda = None
                    
                    try:
                        if not annual_inc.empty:
                            if report_date in annual_inc.columns:
                                fy_net_inc = _scalar(annual_inc[report_date].get("Net Income"))
                                fy_operating_income = _scalar(annual_inc[report_date].get("Operating Income"))
                                fy_gross_profit = _scalar(annual_inc[report_date].get("Gross Profit"))
                                fy_revenue = _scalar(annual_inc[report_date].get("Total Revenue"))
                                fy_ebitda = _scalar(annual_inc[report_date].get("EBITDA"))
                            else:
                                try:
                                    closest_col = min(
                                        annual_inc.columns,
                                        key=lambda x: abs(x - report_date),
                                    )
                                    if abs((closest_col - report_date).days) <= 7:
                                        fy_net_inc = _scalar(annual_inc[closest_col].get("Net Income"))
                                        fy_operating_income = _scalar(annual_inc[closest_col].get("Operating Income"))
                                        fy_gross_profit = _scalar(annual_inc[closest_col].get("Gross Profit"))
                                        fy_revenue = _scalar(annual_inc[closest_col].get("Total Revenue"))
                                        fy_ebitda = _scalar(annual_inc[closest_col].get("EBITDA"))
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"{ticker_str} {year_val}: Income statement extraction failed: {e}")
                    
                    # --- Operating Cash Flow ---
                    try:
                        if not annual_cf.empty:
                            if report_date in annual_cf.columns:
                                fy_operating_cash_flow = _scalar(annual_cf[report_date].get("Operating Cash Flow"))
                            else:
                                try:
                                    closest_cf_col = min(
                                        annual_cf.columns,
                                        key=lambda x: abs(x - report_date),
                                    )
                                    if abs((closest_cf_col - report_date).days) <= 7:
                                        fy_operating_cash_flow = _scalar(annual_cf[closest_cf_col].get("Operating Cash Flow"))
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"{ticker_str} {year_val}: Cash flow extraction failed: {e}")

                    is_latest = report_date == annual_bs.columns[0]
                    final_market_cap = market_cap_converted if is_latest else hist_market_cap
                    if is_latest and final_market_cap is None:
                        final_market_cap = hist_market_cap
                    
                    # DEBUG: Print market cap calculation result
                    if is_latest:
                        print(f"      {ticker_str} {year_val}: market_cap_converted={market_cap_converted}, hist_market_cap={hist_market_cap}, final={final_market_cap}")
                    else:
                        print(f"      {ticker_str} {year_val}: hist_market_cap={hist_market_cap} (shares={shares_outstanding}, source={shares_source})")

                    extracted_data.append({
                        "Ticker":                      ticker_str,
                        "Region":                      region,
                        "Company Name":                company_name,
                        "Industry":                    industry,
                        "Sector":                      sector,
                        "Year":                        year_val,
                        "Report Date":                 date_str,
                        "Trading Currency":            trading_curr,
                        "Financial Currency":          financial_curr,
                        "Beta":                        beta,
                        "Dividend Yield":              dividend_yield if is_latest else None,
                        "Market Cap":                  final_market_cap,
                        "Total Assets":                total_assets,
                        "Total Current Assets":        current_assets,
                        "Current Liabilities":         current_liabilities,
                        "Total Goodwill and Intangibles": total_goodwill_intangibles,
                        "Total Liabilities":           total_liabilities,
                        "Total Equity":                total_equity,
                        "Retained Earnings":           retained_earnings,
                        "Total Investments":           total_investments,
                        "Cash":                        cash,
                        "Receivables":                 receivables,
                        "Inventory":                   inventory,
                        "PPE":                         ppe,
                        "Total Debt":                  total_debt,
                        "Net Debt":                    net_debt,
                        "Latest FY Net Income":        fy_net_inc,
                        "Latest FY Operating Income":  fy_operating_income,
                        "Latest FY Gross Profit":      fy_gross_profit,
                        "Latest FY Revenue":           fy_revenue,
                        "Latest FY Operating Cash Flow": fy_operating_cash_flow,
                        "Latest FY EBITDA":            fy_ebitda,
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