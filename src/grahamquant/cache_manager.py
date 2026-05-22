"""
src/grahamquant/cache_manager.py

Parquet cache layer for GrahamQuant.

Directory layout
----------------
data/
  cache/
    region=US/
      data.parquet        ← all tickers for this region, all years
    region=UK/
      data.parquet
    region=JP/
      data.parquet
    region=HK/
      data.parquet
  manifest.parquet        ← one row per ticker: status, last_updated, years_available

Design decisions
----------------
1.  Partitioned by REGION (not ticker).
    Writing one file per ticker (hundreds of files) creates filesystem overhead
    and makes cross-ticker regional queries slow. One file per region is the
    right granularity — small enough to refresh individually, large enough to
    read the whole UK market in one shot for regional breadth analysis.

2.  Manifest tracks per-ticker metadata.
    The cache data files don't tell you whether a ticker failed or just has
    no data. The manifest records: last_updated, status (ok/partial/failed),
    years_available, and error_msg. The UI and refresh logic reads the manifest
    first.

3.  Canonical schema enforced at write time.
    yfinance field availability varies by exchange. Every write passes through
    _enforce_schema() which casts to a fixed column set, filling missing cols
    with NaN. This prevents schema drift across regions or yfinance upgrades.

4.  Incremental refresh by region.
    refresh_region() re-downloads all tickers for one region and overwrites
    that region's parquet file. A full refresh is just looping over regions.
    Tickers that fail mid-refresh are recorded in the manifest but don't
    abort the whole run.

5.  Staleness threshold.
    is_stale() checks the manifest — if a ticker's last_updated is older than
    STALE_DAYS (default 7), it's considered stale. Callers can force a refresh.
"""

import time
import logging
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

from .ticker_registry import REGISTRY, get_active_regions, get_tickers_by_region, get_region_for_ticker
from .formulas_calcs import apply_calcs

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
STALE_DAYS          = 7      # days before a ticker's data is considered stale
REQUEST_DELAY_SEC   = 1.5    # polite delay between yfinance ticker requests
MAX_RETRIES         = 2      # retry attempts on empty/failed pulls
RETRY_DELAY_SEC     = 5.0    # delay between retries

# ── Canonical schema ──────────────────────────────────────────────────────────
# Every parquet write is cast to exactly these columns in this order.
# Add new columns here (with a sensible NaN default) rather than in the pull fn.
CANONICAL_COLUMNS: dict[str, str] = {
    "Ticker":                       "object",
    "Region":                       "object",
    "Company Name":                 "object",      # Long name from yfinance
    "Industry":                     "object",      # Industry from yfinance
    "Sector":                       "object",      # Sector from yfinance
    "Year":                         "Int64",       # nullable int
    "Report Date":                  "object",      # stored as string "YYYY-MM-DD"
    "Trading Currency":             "object",
    "Financial Currency":           "object",
    "Beta":                         "float64",
    "Market Cap":                   "float64",     # raw numeric — formatting happens in UI
    "Total Assets":                 "float64",
    "Total Current Assets":         "float64",
    "Current Liabilities":          "float64",
    "Total Goodwill and Intangibles": "float64",
    "Total Liabilities":            "float64",
    "Total Equity":                 "float64",
    "Retained Earnings":            "float64",
    "Total Investments":            "float64",
    "Latest FY Net Income":         "float64",
    "Latest FY Operating Income":   "float64",
    "Latest FY Gross Profit":       "float64",
    "Latest FY Revenue":            "float64",
    "Latest FY Operating Cash Flow": "float64",
    "TTM Net Income":               "float64",
    # Calculated columns (added by apply_calcs)
    "NCAV":                         "float64",
    "NCAV_Inv":                     "float64",
    "Book_Value":                   "float64",
    "Tangible_Book_Value":          "float64",
    "ROE":                          "float64",
    "ROA":                          "float64",
    "Price_Book_Ratio":             "float64",
    "Price_Tangible_Book_Ratio":    "float64",
    "Price_NCAV_Ratio":             "float64",
    "Price_NCAV_Inv_Ratio":         "float64",
    "PE_Ratio":                     "float64",
    "PE_Ratio_TTM":                 "float64",
    "Z_Score":                      "float64",
    "F_Score":                      "float64",
}

# Manifest schema
MANIFEST_COLUMNS: dict[str, str] = {
    "Ticker":          "object",
    "Region":          "object",
    "Status":          "object",   # "ok" | "partial" | "failed" | "empty"
    "Last Updated":    "object",   # ISO datetime string
    "Years Available": "Int64",
    "Error":           "object",
}


# ══════════════════════════════════════════════════════════════════════════════
class CacheManager:
    """
    Manages reading, writing, and refreshing the parquet data cache.

    Parameters
    ----------
    data_dir    : root path for the cache (default: project_root / "data")
    pull_fn     : reference to pull_yf_ticker_data
    calc_fn     : reference to create_calcs
    """

    def __init__(self, data_dir: Path, pull_fn, calc_fn=None):
        self.cache_dir    = data_dir / "cache"
        self.manifest_path = data_dir / "manifest.parquet"
        self._pull_fn     = pull_fn
        self._calc_fn     = calc_fn  # kept for compatibility but cache always uses apply_calcs

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def read_region(self, region: str) -> pd.DataFrame:
        """Read all cached data for a region. Returns empty DataFrame if not cached."""
        path = self._region_path(region)
        if not path.exists():
            return pd.DataFrame(columns=list(CANONICAL_COLUMNS.keys()))
        df = pd.read_parquet(path)
        return df

    def read_ticker(self, ticker: str) -> pd.DataFrame:
        """Read cached rows for a single ticker."""
        region = get_region_for_ticker(ticker)
        if region is None:
            logger.warning(f"Ticker {ticker} not found in registry.")
            return pd.DataFrame(columns=list(CANONICAL_COLUMNS.keys()))
        df = self.read_region(region)
        if df.empty:
            return df
        return df[df["Ticker"] == ticker].reset_index(drop=True)

    def read_all_active(self) -> pd.DataFrame:
        """Read and concatenate all active regions into one DataFrame."""
        frames = []
        for region in get_active_regions():
            df = self.read_region(region)
            if not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=list(CANONICAL_COLUMNS.keys()))
        return pd.concat(frames, ignore_index=True)

    def refresh_ticker(self, ticker: str, force: bool = False) -> bool:
        """
        Refresh a single ticker's data.
        Returns True on success, False on failure.
        If force=False, skips tickers that are fresh (< STALE_DAYS old).
        """
        if not force and not self.is_stale(ticker):
            logger.info(f"{ticker}: cache is fresh, skipping.")
            return True

        region = get_region_for_ticker(ticker)
        if region is None:
            logger.warning(f"{ticker}: not in registry, cannot refresh.")
            return False

        logger.info(f"Refreshing {ticker} ({region})…")
        success, df_new, error_msg = self._fetch_one(ticker)

        # Merge into region file
        df_region = self.read_region(region)
        if not df_region.empty:
            df_region = df_region[df_region["Ticker"] != ticker]  # drop old rows

        if success and not df_new.empty:
            df_new["Region"] = region
            df_merged = pd.concat([df_region, df_new], ignore_index=True)
        else:
            df_merged = df_region

        df_merged = _enforce_schema(df_merged)
        df_merged.to_parquet(self._region_path(region), index=False, compression="snappy")

        years = len(df_new) if (success and not df_new.empty) else 0
        status = "ok" if success else "failed"
        if success and df_new.empty:
            status = "empty"
        self._update_manifest(ticker, region, status, years, error_msg)

        return success

    def refresh_region(
        self,
        region: str,
        force: bool = False,
        progress_cb=None,
    ) -> dict:
        """
        Refresh all tickers for a region.

        Parameters
        ----------
        region      : region code from REGISTRY
        force       : re-download even if data is fresh
        progress_cb : optional callable(ticker, idx, total, status) for UI updates

        Returns summary dict: {ok, partial, failed, empty, total}
        """
        tickers = get_tickers_by_region(region)
        if not tickers:
            logger.warning(f"No tickers registered for region {region}.")
            return {}

        total = len(tickers)
        results = {"ok": 0, "partial": 0, "failed": 0, "empty": 0, "total": total}
        region_rows = []

        for idx, ticker in enumerate(tickers):
            if not force and not self.is_stale(ticker):
                logger.info(f"  [{idx+1}/{total}] {ticker}: fresh, skipping.")
                # Still load existing rows into region_rows
                existing = self.read_ticker(ticker)
                if not existing.empty:
                    region_rows.append(existing)
                results["ok"] += 1
                if progress_cb:
                    progress_cb(ticker, idx + 1, total, "skipped")
                continue

            logger.info(f"  [{idx+1}/{total}] Fetching {ticker}…")
            success, df_new, error_msg = self._fetch_one(ticker)

            if success and not df_new.empty:
                df_new["Region"] = region
                region_rows.append(df_new)
                years = len(df_new)
                status = "ok"
                results["ok"] += 1
            elif success and df_new.empty:
                status = "empty"
                results["empty"] += 1
                years = 0
            else:
                status = "failed"
                results["failed"] += 1
                years = 0
                logger.error(f"  {ticker} failed: {error_msg}")

            self._update_manifest(ticker, region, status, years, error_msg)

            if progress_cb:
                progress_cb(ticker, idx + 1, total, status)

            # Polite delay between requests to avoid rate limiting
            if idx < total - 1:
                time.sleep(REQUEST_DELAY_SEC)

        # Write full region file atomically
        if region_rows:
            df_region = pd.concat(region_rows, ignore_index=True)
            df_region = _enforce_schema(df_region)
            df_region.to_parquet(self._region_path(region), index=False, compression="snappy")
            logger.info(
                f"Region {region}: wrote {len(df_region)} rows "
                f"({results['ok']} ok, {results['failed']} failed, {results['empty']} empty)"
            )
        else:
            logger.warning(f"Region {region}: no data to write.")

        return results

    def refresh_all_active(self, force: bool = False, progress_cb=None) -> dict:
        """Refresh all active regions. Returns combined summary."""
        combined = {"ok": 0, "partial": 0, "failed": 0, "empty": 0, "total": 0}
        for region in get_active_regions():
            logger.info(f"=== Refreshing region: {region} ===")
            result = self.refresh_region(region, force=force, progress_cb=progress_cb)
            for k in combined:
                combined[k] += result.get(k, 0)
        return combined

    def is_stale(self, ticker: str) -> bool:
        """True if ticker has no cache entry or was last updated > STALE_DAYS ago."""
        manifest = self._read_manifest()
        if manifest.empty or ticker not in manifest["Ticker"].values:
            return True
        row = manifest[manifest["Ticker"] == ticker].iloc[0]
        if row["Status"] in ("failed", "empty"):
            return True
        try:
            last = datetime.fromisoformat(str(row["Last Updated"]))
            return datetime.now() - last > timedelta(days=STALE_DAYS)
        except Exception:
            return True

    def get_manifest(self) -> pd.DataFrame:
        """Return the full manifest as a DataFrame."""
        return self._read_manifest()

    # ── Regional analysis helpers ─────────────────────────────────────────────

    def regional_breadth(self, region: str | None = None) -> pd.DataFrame:
        """
        Compute value breadth statistics per region.

        For each region (or a specific one), calculates:
          - total stocks in cache
          - % trading below Book Value (P/B < 1)
          - % trading below Tangible Book (P/TBV < 1)
          - % trading below NCAV (Graham net-net, P/NCAV < 1)
          - % trading below NCAV+Investments
          - median P/B, median P/NCAV

        Uses only the most recent reporting year per ticker.
        """
        if region:
            df = self.read_region(region)
            df["Region"] = region
        else:
            df = self.read_all_active()

        if df.empty:
            return pd.DataFrame()

        # Most recent year per ticker
        latest = (
            df.sort_values("Year", ascending=False)
            .groupby("Ticker", as_index=False)
            .first()
        )

        records = []
        for rgn, grp in latest.groupby("Region"):
            n = len(grp)
            if n == 0:
                continue

            def pct_below(col, threshold=1.0):
                valid = grp[col].dropna()
                valid = valid[valid > 0]   # exclude negative/zero (not meaningful)
                if valid.empty:
                    return None
                return (valid < threshold).sum() / len(valid) * 100

            records.append({
                "Region":               rgn,
                "Region Name":          REGISTRY.get(rgn, {}).get("name", rgn),
                "Tickers in Cache":     n,
                "% Below Book (P/B<1)":    round(pct_below("Price_Book_Ratio") or 0, 1),
                "% Below Tang BV":         round(pct_below("Price_Tangible_Book_Ratio") or 0, 1),
                "% Below NCAV (Net-Net)":  round(pct_below("Price_NCAV_Ratio") or 0, 1),
                "% Below NCAV+Inv":        round(pct_below("Price_NCAV_Inv_Ratio") or 0, 1),
                "Median P/B":   round(grp["Price_Book_Ratio"].median(), 2) if not grp["Price_Book_Ratio"].dropna().empty else None,
                "Median P/NCAV":round(grp["Price_NCAV_Ratio"].median(), 2) if not grp["Price_NCAV_Ratio"].dropna().empty else None,
            })

        return pd.DataFrame(records)

    def screen(
        self,
        region: str | None = None,
        max_pb: float | None = 1.0,
        max_pncav: float | None = 1.0,
        min_roe: float | None = None,
        latest_only: bool = True,
    ) -> pd.DataFrame:
        """
        Screen all cached tickers against value thresholds.

        Parameters
        ----------
        region     : filter to one region, or None for all active
        max_pb     : maximum P/B ratio (None = no filter)
        max_pncav  : maximum P/NCAV ratio (None = no filter)
        min_roe    : minimum ROE as decimal e.g. 0.05 = 5% (None = no filter)
        latest_only: use only the most recent year per ticker

        Returns filtered DataFrame sorted by P/NCAV ascending.
        """
        df = self.read_region(region) if region else self.read_all_active()
        if df.empty:
            return df

        if latest_only:
            df = (
                df.sort_values("Year", ascending=False)
                .groupby("Ticker", as_index=False)
                .first()
            )

        mask = pd.Series(True, index=df.index)
        if max_pb is not None:
            mask &= df["Price_Book_Ratio"].notna() & (df["Price_Book_Ratio"] > 0) & (df["Price_Book_Ratio"] <= max_pb)
        if max_pncav is not None:
            mask &= df["Price_NCAV_Ratio"].notna() & (df["Price_NCAV_Ratio"] > 0) & (df["Price_NCAV_Ratio"] <= max_pncav)
        if min_roe is not None:
            mask &= df["ROE"].notna() & (df["ROE"] >= min_roe)

        result = df[mask].copy()
        if not result.empty and "Price_NCAV_Ratio" in result.columns:
            result = result.sort_values("Price_NCAV_Ratio", ascending=True)

        return result.reset_index(drop=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fetch_one(self, ticker: str) -> tuple[bool, pd.DataFrame, str | None]:
        """
        Pull and calculate data for one ticker.
        Returns (success, df, error_message).
        Retries up to MAX_RETRIES on empty results.
        """
        error_msg = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = self._pull_fn(ticker_list=[ticker])
                if raw.empty:
                    if attempt < MAX_RETRIES:
                        logger.warning(f"  {ticker}: empty pull, retrying in {RETRY_DELAY_SEC}s…")
                        time.sleep(RETRY_DELAY_SEC)
                        continue
                    return True, pd.DataFrame(), None

                # apply_calcs returns raw floats — safe to write to parquet.
                # Never use create_calcs here as that formats strings in-place.
                df = apply_calcs(df_=raw)
                return True, df, None

            except Exception as exc:
                error_msg = str(exc)
                logger.error(f"  {ticker} attempt {attempt+1} error: {error_msg}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC)

        return False, pd.DataFrame(), error_msg

    def _region_path(self, region: str) -> Path:
        region_dir = self.cache_dir / f"region={region}"
        region_dir.mkdir(parents=True, exist_ok=True)
        return region_dir / "data.parquet"

    def _read_manifest(self) -> pd.DataFrame:
        if not self.manifest_path.exists():
            return pd.DataFrame(columns=list(MANIFEST_COLUMNS.keys()))
        try:
            df = pd.read_parquet(self.manifest_path)
            # Ensure all expected columns exist even if file predates a schema change
            for col in MANIFEST_COLUMNS:
                if col not in df.columns:
                    df[col] = pd.NA
            return df
        except Exception as e:
            logger.error(f"Failed to read manifest, starting fresh: {e}")
            return pd.DataFrame(columns=list(MANIFEST_COLUMNS.keys()))

    def _update_manifest(
        self,
        ticker: str,
        region: str,
        status: str,
        years: int,
        error: str | None,
    ):
        try:
            manifest = self._read_manifest()

            # Remove existing row for this ticker
            if not manifest.empty and "Ticker" in manifest.columns:
                manifest = manifest[manifest["Ticker"] != ticker].copy()

            new_row = pd.DataFrame([{
                "Ticker":          ticker,
                "Region":          region,
                "Status":          status,
                "Last Updated":    datetime.now().isoformat(timespec="seconds"),
                "Years Available": int(years),
                "Error":           str(error) if error else "",
            }])

            manifest = pd.concat([manifest, new_row], ignore_index=True)
            manifest = _cast_manifest(manifest)
            manifest.to_parquet(self.manifest_path, index=False, compression="snappy")
            logger.debug(f"Manifest updated: {ticker} -> {status} ({years} years)")
        except Exception as e:
            logger.error(f"Failed to update manifest for {ticker}: {e}")



# ── Schema enforcement ────────────────────────────────────────────────────────

def _enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast df to the canonical column set.
    - Missing columns are added as NaN.
    - Extra columns (e.g. display-formatted strings) are dropped.
    - Dtypes are coerced where possible.
    """
    result = pd.DataFrame()
    for col, dtype in CANONICAL_COLUMNS.items():
        if col in df.columns:
            try:
                if dtype == "Int64":
                    result[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                elif dtype == "float64":
                    # If column contains formatted strings like "1.5b", coerce to NaN
                    result[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
                else:
                    result[col] = df[col].astype(str).where(df[col].notna(), other=pd.NA)
            except Exception:
                result[col] = pd.NA
        else:
            if dtype == "Int64":
                result[col] = pd.array([pd.NA] * len(df), dtype="Int64")
            elif dtype == "float64":
                result[col] = np.nan
            else:
                result[col] = pd.NA

    return result


def _cast_manifest(df: pd.DataFrame) -> pd.DataFrame:
    for col, dtype in MANIFEST_COLUMNS.items():
        if col not in df.columns:
            df[col] = pd.NA
        if dtype == "Int64":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df
