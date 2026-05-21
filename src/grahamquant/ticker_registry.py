"""
src/grahamquant/ticker_registry.py

Regional ticker registry — the single source of truth for which tickers
belong to which region and exchange.

Structure
---------
REGISTRY : dict[region_code, dict]
    region_code  : short string key used in parquet partitioning ("US", "UK", "JP", ...)
    name         : human-readable region name
    exchange     : primary exchange name (display only)
    suffix       : Yahoo Finance ticker suffix (e.g. ".T", ".L", "" for US)
    tickers      : list of ticker strings as they appear on Yahoo Finance
    currency     : primary reporting currency (informational)

Design notes
------------
- Tickers are stored WITH their exchange suffix already included so they can
  be passed directly to yfinance with no transformation.
- US tickers have no suffix (Yahoo Finance convention).
- Adding a new region = adding one entry to REGISTRY and populating tickers.
- The cache layer (cache_manager.py) reads from this registry to know what
  to download and how to partition the parquet store.

Rollout plan
------------
  Phase 1 (now)  : US, UK, JP — seeded with representative small/micro-cap
                   value names where Graham-style screening is most interesting.
  Phase 2        : HK, KR, AU
  Phase 3        : DE, FR, SE, SG
"""

REGISTRY: dict[str, dict] = {

    # ── United States ─────────────────────────────────────────────────────────
    # No suffix. Broad small/micro-cap universe is where net-nets historically
    # appear. Large-caps included for benchmark context.
    "US": {
        "name":     "United States",
        "exchange": "NYSE / NASDAQ",
        "suffix":   "",
        "currency": "USD",
        "tickers": [
            # Benchmark large-caps
            "AAPL", "MSFT", "BRK-B", "JPM", "BAC",
            # Small / micro-cap value candidates (expand this list)
            "KBAL", "TWST", "MGPI", "ZEUS", "GFF",
            "STLY", "HAYN", "CATO", "DXPE", "KELYA",
        ],
    },

    # ── United Kingdom ────────────────────────────────────────────────────────
    # Suffix: .L  (London Stock Exchange)
    # UK small-caps have historically had periods of deep value opportunity.
    "UK": {
        "name":     "United Kingdom",
        "exchange": "London Stock Exchange",
        "suffix":   ".L",
        "currency": "GBp",   # pence — yfinance often reports in pence, not pounds
        "tickers": [
            "VTU.L", "LLOY.L", "BARC.L", "AZN.L", "BP.L",
            "MKS.L", "TSCO.L", "RIO.L", "GSK.L", "ULVR.L",
            # Small-cap value candidates
            "TET.L", "TSTL.L", "SRC.L", "BVIC.L", "PGB.L",
        ],
    },

    # ── Japan ─────────────────────────────────────────────────────────────────
    # Suffix: .T  (Tokyo Stock Exchange)
    # Japan has the highest density of net-net stocks globally — the TSE has
    # had hundreds of companies trading below NCAV at any given time.
    # Figures reported in JPY (millions).
    "JP": {
        "name":     "Japan",
        "exchange": "Tokyo Stock Exchange",
        "suffix":   ".T",
        "currency": "JPY",
        "tickers": [
            "2267.T", "3435.T", "7399.T",
            "7974.T", "6758.T", "6501.T", "7267.T", "9984.T",
            # Small-cap value candidates
            "3099.T", "7936.T", "3116.T", "2751.T", "9830.T",
            "3635.T", "1780.T", "6412.T", "9740.T", "7919.T",
        ],
    },

    # ── Hong Kong ─────────────────────────────────────────────────────────────
    # Suffix: .HK  — Phase 2, seeded but not yet in active rollout.
    # HK has had persistent Graham-style value opportunities, especially
    # in small property-adjacent and industrial names.
    "HK": {
        "name":     "Hong Kong",
        "exchange": "Hong Kong Stock Exchange",
        "suffix":   ".HK",
        "currency": "HKD",
        "tickers": [
            "1846.HK", "6889.HK", "1913.HK",
            "0005.HK", "0700.HK", "0388.HK",
            "0016.HK", "0001.HK", "2318.HK",
        ],
        "active": True,   # Phase 2 — set True to include in downloads
    },

    # ── Future regions (Phase 3) ──────────────────────────────────────────────
    # Uncomment and populate tickers when ready to expand.

    # "AU": {
    #     "name": "Australia", "exchange": "ASX", "suffix": ".AX",
    #     "currency": "AUD", "tickers": [], "active": False,
    # },
    # "KR": {
    #     "name": "South Korea", "exchange": "KRX", "suffix": ".KS",
    #     "currency": "KRW", "tickers": [], "active": False,
    # },
    # "DE": {
    #     "name": "Germany", "exchange": "XETRA", "suffix": ".DE",
    #     "currency": "EUR", "tickers": [], "active": False,
    # },
}


def get_active_regions() -> list[str]:
    """Return region codes where active=True (or active key is absent, defaulting True)."""
    return [code for code, cfg in REGISTRY.items() if cfg.get("active", True)]


def get_all_tickers(regions: list[str] | None = None) -> list[str]:
    """Return flat list of all tickers for the given regions (default: active only)."""
    regions = regions or get_active_regions()
    tickers = []
    for code in regions:
        if code in REGISTRY:
            tickers.extend(REGISTRY[code]["tickers"])
    return tickers


def get_region_for_ticker(ticker: str) -> str | None:
    """Look up which region a ticker belongs to."""
    for code, cfg in REGISTRY.items():
        if ticker in cfg["tickers"]:
            return code
    return None


def get_tickers_by_region(region: str) -> list[str]:
    return REGISTRY.get(region, {}).get("tickers", [])
