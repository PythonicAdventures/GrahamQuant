"""
src/grahamquant/ui_fastapi.py

FastAPI web UI for GrahamQuant with two views:
  1. SCREENER VIEW: Population table with key metrics
  2. DETAILS VIEW: Historical data for selected ticker

Replaces the tkinter UI with a modern web interface.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.grahamquant.formulas_calcs import apply_formatting

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ── Ensure directories exist ──────────────────────────────────────────────────
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
class GrahamQuantWebApp:
    def __init__(self, ticker_list: list, pull_fn, calc_fn, cache=None, host: str = "127.0.0.1", port: int = 8000):
        self.ticker_list = ticker_list
        self.pull_fn = pull_fn
        self.calc_fn = calc_fn
        self.cache = cache
        self.host = host
        self.port = port

        # Data state
        self.all_data: Optional[pd.DataFrame] = None
        self.loading_status = "Loading all ticker data…"
        self.loading_complete = False

        # Filter state
        self.active_regions = set()
        self.active_industries = set()

        # Create FastAPI app
        self.app = FastAPI(title="GrahamQuant")

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            """Serve main page."""
            return self._render_html()

        @self.app.get("/api/status")
        async def get_status():
            """Get loading status."""
            return {
                "loading": not self.loading_complete,
                "status": self.loading_status,
                "data_loaded": self.all_data is not None,
            }

        @self.app.get("/api/screener")
        async def get_screener(
            sort_col: Optional[str] = None,
            sort_reverse: Optional[bool] = False,
            sectors: Optional[str] = None,
            industries: Optional[str] = None,
        ):
            """Get screener data with optional filtering and sorting."""
            if self.all_data is None or self.all_data.empty:
                return {"data": [], "count": 0, "total": 0}

            # Get latest year for each ticker
            df = self.all_data.sort_values("Year", ascending=False).drop_duplicates("Ticker").copy()

            # Apply filters
            if sectors:
                sector_list = json.loads(sectors)
                df = df[df["Sector"].isin(sector_list)]
            if industries:
                industry_list = json.loads(industries)
                df = df[df["Industry"].isin(industry_list)]

            # Apply sorting
            if sort_col and sort_col in df.columns:
                try:
                    df = df.sort_values(sort_col, ascending=not sort_reverse, na_position='last')
                except Exception as e:
                    log.warning(f"Sort failed for column {sort_col}: {e}")

            # Format for display
            result = []
            for _, row in df.iterrows():
                result.append({
                    "Ticker": _fmt(row.get("Ticker", None), "Ticker"),
                    "Company Name": _fmt(row.get("Company Name", None), "Company Name"),
                    "Sector": _fmt(row.get("Sector", None), "Sector"),
                    "Industry": _fmt(row.get("Industry", None), "Industry"),
                    "Price": _fmt(row.get("Price", None), "Price"),
                    "Beta": _fmt(row.get("Beta", None), "Beta"),
                    "Market Cap": _fmt(row.get("Market Cap", None), "Market Cap"),
                    "Price_Book_Ratio": _fmt(row.get("Price_Book_Ratio", None), "Price_Book_Ratio"),
                    "Price_NCAV_Ratio": _fmt(row.get("Price_NCAV_Ratio", None), "Price_NCAV_Ratio"),
                    "Z_Score": _fmt(row.get("Z_Score", None), "Z_Score"),
                    "F_Score": _fmt(row.get("F_Score", None), "F_Score"),
                    "ROE": _fmt(row.get("ROE", None), "ROE"),
                    "Net_Debt_EBITDA": _fmt(row.get("Net_Debt_EBITDA", None), "Net_Debt_EBITDA"),
                    "Dividend_Yield": _fmt(row.get("Dividend_Yield", None), "Dividend_Yield"),
                    "Cash_Pct": _fmt(row.get("Cash_Pct", None), "Cash_Pct"),
                    "Receivables_Pct": _fmt(row.get("Receivables_Pct", None), "Receivables_Pct"),
                    "Inventory_Pct": _fmt(row.get("Inventory_Pct", None), "Inventory_Pct"),
                    "PPE_Pct": _fmt(row.get("PPE_Pct", None), "PPE_Pct"),
                    "Other_Assets_Pct": _fmt(row.get("Other_Assets_Pct", None), "Other_Assets_Pct"),
                })

            return {
                "data": result,
                "count": len(result),
                "total": len(self.all_data.drop_duplicates("Ticker")),
            }

        @self.app.get("/api/filters")
        async def get_filters():
            """Get available filter options."""
            if self.all_data is None or self.all_data.empty:
                return {"sectors": [], "industries": []}

            latest_df = self.all_data.sort_values("Year", ascending=False).drop_duplicates("Ticker")
            sectors = sorted(latest_df["Sector"].dropna().unique().tolist())
            industries = sorted(latest_df["Industry"].dropna().unique().tolist())

            return {
                "sectors": sectors,
                "industries": industries,
                "selected_sectors": list(self.active_regions) if self.active_regions else sectors,
                "selected_industries": list(self.active_industries) if self.active_industries else industries,
            }

        @self.app.post("/api/filters")
        async def set_filters(request: Request):
            """Set active filters."""
            data = await request.json()
            self.active_regions = set(data.get("sectors", []))
            self.active_industries = set(data.get("industries", []))
            return {"success": True}

        @self.app.get("/api/details/{ticker}")
        async def get_details(ticker: str):
            """Get historical details for a ticker."""
            if self.all_data is None or self.all_data.empty:
                raise HTTPException(status_code=404, detail="No data available")

            ticker_df = self.all_data[self.all_data["Ticker"] == ticker].sort_values("Year", ascending=False)

            if ticker_df.empty:
                raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

            # Format for display
            result = []
            for _, row in ticker_df.iterrows():
                result.append({
                    "Year": _fmt(row.get("Year", None), "Year"),
                    "Report Date": _fmt(row.get("Report Date", None), "Report Date"),
                    "Market Cap": _fmt(row.get("Market Cap", None), "Market Cap"),
                    "Book_Value": _fmt(row.get("Book_Value", None), "Book_Value"),
                    "Tangible_Book_Value": _fmt(row.get("Tangible_Book_Value", None), "Tangible_Book_Value"),
                    "NCAV": _fmt(row.get("NCAV", None), "NCAV"),
                    "NCAV_Inv": _fmt(row.get("NCAV_Inv", None), "NCAV_Inv"),
                    "Total Assets": _fmt(row.get("Total Assets", None), "Total Assets"),
                    "Total Liabilities": _fmt(row.get("Total Liabilities", None), "Total Liabilities"),
                    "Total Equity": _fmt(row.get("Total Equity", None), "Total Equity"),
                    "Latest FY Net Income": _fmt(row.get("Latest FY Net Income", None), "Latest FY Net Income"),
                    "Price_Book_Ratio": _fmt(row.get("Price_Book_Ratio", None), "Price_Book_Ratio"),
                    "Price_Tangible_Book_Ratio": _fmt(row.get("Price_Tangible_Book_Ratio", None), "Price_Tangible_Book_Ratio"),
                    "Price_NCAV_Ratio": _fmt(row.get("Price_NCAV_Ratio", None), "Price_NCAV_Ratio"),
                    "PE_Ratio": _fmt(row.get("PE_Ratio", None), "PE_Ratio"),
                    "ROE": _fmt(row.get("ROE", None), "ROE"),
                    "Z_Score": _fmt(row.get("Z_Score", None), "Z_Score"),
                    "F_Score": _fmt(row.get("F_Score", None), "F_Score"),
                })

            return {
                "ticker": ticker,
                "price": _fmt(ticker_df.iloc[0].get("Price", None), "Price") if not ticker_df.empty else "N/A",
                "data": result,
                "count": len(result),
            }

    def _render_html(self) -> str:
        """Render main HTML page."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GrahamQuant - Deep Value Screener</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root {
            --bg: #0f1117;
            --surface: #1a1d27;
            --border: #070707;
            --accent: #f0f2fa;
            --neg: #e05c5c;
            --neutral: #8b8fa8;
            --body: #d4d7e3;
            --white: #f0f2fa;
            --highlight: #252838;
        }

        * {
            color-scheme: dark;
        }

        body {
            background-color: var(--bg);
            color: var(--body);
            font-family: 'Courier New', monospace;
            margin: 0;
            padding: 0;
        }

        .title-bar {
            background-color: var(--bg);
            padding: 1.5rem 1.5rem;
            border-bottom: 1px solid var(--border);
        }

        .title-bar h1 {
            color: var(--accent);
            font-size: 1.5rem;
            font-weight: bold;
            margin: 0;
            display: inline;
        }

        .title-bar .subtitle {
            color: var(--neutral);
            font-size: 0.9rem;
            margin-left: 0.5rem;
            display: inline;
        }

        .toolbar {
            background-color: var(--surface);
            padding: 0.75rem 1.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .nav-buttons {
            display: flex;
            gap: 0.5rem;
        }

        .nav-btn {
            background-color: var(--border);
            color: var(--neutral);
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            transition: all 0.2s;
        }

        .nav-btn:hover {
            background-color: var(--surface);
            color: var(--body);
        }

        .nav-btn.active {
            background-color: var(--accent);
            color: var(--bg);
        }

        .status-label {
            color: var(--neutral);
            font-size: 0.9rem;
            margin-left: auto;
        }

        .accent-line {
            height: 1px;
            background-color: var(--accent);
            border: none;
        }

        .content {
            padding: 1.5rem;
            min-height: calc(100vh - 200px);
        }

        .section-title {
            color: var(--accent);
            font-size: 1.1rem;
            font-weight: bold;
            margin-bottom: 1rem;
        }

        .filter-panel {
            background-color: var(--surface);
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
            border: 1px solid var(--border);
        }

        .filter-group {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .filter-label {
            color: var(--accent);
            font-weight: bold;
            font-size: 0.9rem;
        }

        .filter-btn {
            background-color: var(--border);
            color: var(--body);
            border: 1px solid var(--neutral);
            padding: 0.4rem 0.8rem;
            border-radius: 4px;
            cursor: pointer;
            font-family: 'Courier New', monospace;
            font-size: 0.85rem;
            transition: all 0.2s;
        }

        .filter-btn:hover {
            background-color: var(--surface);
            border-color: var(--accent);
        }

        .filter-count {
            color: var(--neutral);
            font-size: 0.8rem;
            margin-left: 0.5rem;
        }

        table {
            background-color: var(--surface);
            border-collapse: collapse;
            width: 100%;
            font-size: 0.9rem;
        }

        thead {
            background-color: var(--border);
            border-bottom: 1px solid var(--neutral);
        }

        th {
            color: var(--accent);
            padding: 0.8rem;
            text-align: left;
            font-weight: bold;
            cursor: pointer;
            user-select: none;
            border-right: 1px solid var(--border);
        }

        th:hover {
            background-color: var(--highlight);
        }

        td {
            padding: 0.8rem;
            border-bottom: 1px solid var(--border);
        }

        tbody tr:nth-child(odd) {
            background-color: var(--surface);
        }

        tbody tr:nth-child(even) {
            background-color: var(--bg);
        }

        tbody tr:hover {
            background-color: var(--highlight);
            cursor: pointer;
        }

        .table-container {
            overflow-x: auto;
            border: 1px solid var(--border);
            border-radius: 4px;
        }

        .text-col {
            text-align: left;
        }

        .num-col {
            text-align: right;
        }

        .cell-green {
            background-color: rgba(76, 175, 80, 0.2) !important;
            color: #4cb050;
            font-weight: 500;
        }

        .loading {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 300px;
            color: var(--neutral);
        }

        .spinner {
            border: 2px solid var(--border);
            border-top: 2px solid var(--accent);
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin-right: 1rem;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .modal-dialog {
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 4px;
        }

        .modal-header {
            background-color: var(--border);
            border-bottom: 1px solid var(--neutral);
        }

        .modal-header .btn-close {
            filter: brightness(0.8);
        }

        .modal-body {
            background-color: var(--surface);
        }

        .modal-footer {
            background-color: var(--border);
            border-top: 1px solid var(--neutral);
        }

        .form-check-input {
            background-color: var(--border);
            border: 1px solid var(--neutral);
        }

        .form-check-input:checked {
            background-color: var(--accent);
            border-color: var(--accent);
        }

        .form-check-label {
            color: var(--body);
            font-size: 0.9rem;
        }

        @media (max-width: 768px) {
            .toolbar {
                flex-direction: column;
                align-items: flex-start;
            }

            .status-label {
                margin-left: 0;
                margin-top: 0.5rem;
            }

            table {
                font-size: 0.8rem;
            }

            th, td {
                padding: 0.5rem;
            }
        }
    </style>
</head>
<body>
    <div class="title-bar">
        <h1>GRAHAMQUANT</h1>
        <span class="subtitle">// Deep Value Screener</span>
    </div>

    <div class="toolbar">
        <div class="nav-buttons">
            <button class="nav-btn active" onclick="switchView('screener')">✓ SCREENER (Population)</button>
            <button class="nav-btn" onclick="switchView('details')">◆ HISTORICAL DETAILS</button>
        </div>
        <div class="status-label" id="statusLabel">Loading all ticker data…</div>
    </div>

    <div class="accent-line"></div>

    <div class="content" id="content">
        <div class="loading">
            <div class="spinner"></div>
            <span>Loading…</span>
        </div>
    </div>

    <!-- Filter Modal -->
    <div class="modal fade" id="filterModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="filterModalTitle">Select Filters</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div id="filterContent"></div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" onclick="selectAllFilters()">Select All</button>
                    <button type="button" class="btn btn-secondary" onclick="deselectAllFilters()">Deselect All</button>
                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal" onclick="applyFilters()">OK</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentView = 'screener';
        let selectedTicker = null;
        let sortCol = null;
        let sortReverse = false;
        let filterType = null;
        let availableFilters = {};

        async function initApp() {
            await checkLoadingStatus();
            await loadScreener();
        }

        async function checkLoadingStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                document.getElementById('statusLabel').textContent = data.status;

                if (!data.loading) {
                    // Data is ready
                    return;
                } else {
                    // Keep checking
                    setTimeout(checkLoadingStatus, 1000);
                }
            } catch (error) {
                console.error('Status check failed:', error);
                setTimeout(checkLoadingStatus, 2000);
            }
        }

        function switchView(view) {
            currentView = view;
            const buttons = document.querySelectorAll('.nav-btn');
            buttons.forEach((btn, i) => {
                btn.classList.toggle('active', (i === 0 && view === 'screener') || (i === 1 && view === 'details'));
            });

            if (view === 'screener') {
                loadScreener();
            } else {
                if (selectedTicker) {
                    loadDetails(selectedTicker);
                } else {
                    document.getElementById('content').innerHTML = '<p style="padding: 2rem; color: #8b8fa8;">Please select a ticker from the screener view.</p>';
                }
            }
        }

        async function loadScreener() {
            try {
                // Get filters
                const filterResponse = await fetch('/api/filters');
                const filterData = await filterResponse.json();
                availableFilters = filterData;

                // Get screener data
                const sectors = availableFilters.selected_sectors || [];
                const industries = availableFilters.selected_industries || [];
                
                const params = new URLSearchParams();
                if (sortCol) params.append('sort_col', sortCol);
                if (sortReverse) params.append('sort_reverse', sortReverse);
                params.append('sectors', JSON.stringify(sectors));
                params.append('industries', JSON.stringify(industries));

                const response = await fetch(`/api/screener?${params}`);
                const data = await response.json();

                renderScreener(data, filterData);
                updateStatus(`Displayed ${data.count} of ${data.total} tickers.`);
            } catch (error) {
                console.error('Failed to load screener:', error);
                document.getElementById('content').innerHTML = '<p style="padding: 2rem; color: #e05c5c;">Error loading screener data</p>';
            }
        }

        function renderScreener(data, filterData) {
            const columns = [
                'Ticker', 'Company Name', 'Sector', 'Industry', 'Price', 'Beta', 'Market Cap',
                'Price_Book_Ratio', 'Price_NCAV_Ratio', 'Z_Score', 'F_Score', 'ROE',
                'Net_Debt_EBITDA', 'Dividend_Yield', 'Cash_Pct', 'Receivables_Pct',
                'Inventory_Pct', 'PPE_Pct', 'Other_Assets_Pct'
            ];

            const headers = {
                'Ticker': 'Ticker',
                'Company Name': 'Name',
                'Sector': 'Sector',
                'Industry': 'Industry',
                'Price': 'Price',
                'Beta': 'Beta',
                'Market Cap': 'Mkt Cap',
                'Price_Book_Ratio': 'P/B',
                'Price_NCAV_Ratio': 'P/NCAV',
                'Z_Score': 'Z-Score',
                'F_Score': 'F-Score',
                'ROE': 'ROE %',
                'Net_Debt_EBITDA': 'ND/EBITDA',
                'Dividend_Yield': 'Div Yield',
                'Cash_Pct': 'Cash %',
                'Receivables_Pct': 'AR %',
                'Inventory_Pct': 'Inv %',
                'PPE_Pct': 'PPE %',
                'Other_Assets_Pct': 'Other %'
            };

            let html = '<div class="filter-panel"><div class="filter-group">';
            html += '<label class="filter-label">SECTORS:</label>';
            html += `<button class="filter-btn" onclick="showFilterModal('sectors')">Select Sectors <span class="filter-count">(${filterData.selected_sectors.length}/${filterData.sectors.length})</span></button>`;
            html += '<label class="filter-label" style="margin-left: 2rem;">INDUSTRIES:</label>';
            html += `<button class="filter-btn" onclick="showFilterModal('industries')">Select Industries <span class="filter-count">(${filterData.selected_industries.length}/${filterData.industries.length})</span></button>`;
            html += '</div></div>';

            html += '<div class="table-container"><table><thead><tr>';

            columns.forEach(col => {
                const headerText = headers[col] || col;
                html += `<th onclick="setSortColumn('${col}')">${headerText}</th>`;
            });

            html += '</tr></thead><tbody>';

            data.data.forEach(row => {
                html += `<tr onclick="selectTicker('${row.Ticker}')">`;
                columns.forEach(col => {
                    const isTextCol = ['Ticker', 'Company Name', 'Sector', 'Industry'].includes(col);
                    let cellClass = isTextCol ? 'text-col' : 'num-col';
                    let bgClass = '';
                    
                    // Color coding logic
                    const val = row[col];
                    if (val !== 'N/A') {
                        if ((col === 'Price_NCAV_Ratio' || col === 'Price_Book_Ratio') && parseFloat(val) < 1) {
                            bgClass = 'cell-green';
                        } else if (col === 'ROE' && parseFloat(val) > 10) {
                            bgClass = 'cell-green';
                        } else if (col === 'Z_Score' && parseFloat(val) > 3) {
                            bgClass = 'cell-green';
                        } else if (col === 'F_Score' && parseFloat(val) >= 7) {
                            bgClass = 'cell-green';
                        }
                    }
                    
                    html += `<td class="${cellClass} ${bgClass}">${val}</td>`;
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';
            document.getElementById('content').innerHTML = html;
        }

        async function loadDetails(ticker) {
            try {
                const response = await fetch(`/api/details/${ticker}`);
                if (!response.ok) throw new Error('Ticker not found');
                const data = await response.json();

                renderDetails(data);
                updateStatus(`Showing ${data.count} reporting years for ${ticker}.`);
            } catch (error) {
                console.error('Failed to load details:', error);
                document.getElementById('content').innerHTML = '<p style="padding: 2rem; color: #e05c5c;">Error loading ticker details</p>';
            }
        }

        function renderDetails(data) {
            const columns = [
                'Year', 'Report Date', 'Market Cap', 'Book_Value', 'Tangible_Book_Value',
                'NCAV', 'NCAV_Inv', 'Total Assets', 'Total Liabilities', 'Total Equity',
                'Latest FY Net Income', 'Price_Book_Ratio', 'Price_Tangible_Book_Ratio',
                'Price_NCAV_Ratio', 'PE_Ratio', 'ROE', 'Z_Score', 'F_Score'
            ];

            const headers = {
                'Year': 'Year',
                'Report Date': 'Report Date',
                'Market Cap': 'Mkt Cap',
                'Book_Value': 'Book Val',
                'Tangible_Book_Value': 'Tang BV',
                'NCAV': 'NCAV',
                'NCAV_Inv': 'NCAV+Inv',
                'Total Assets': 'Assets',
                'Total Liabilities': 'Liabilities',
                'Total Equity': 'Equity',
                'Latest FY Net Income': 'Net Inc (FY)',
                'Price_Book_Ratio': 'P/B',
                'Price_Tangible_Book_Ratio': 'P/TBV',
                'Price_NCAV_Ratio': 'P/NCAV',
                'PE_Ratio': 'PE',
                'ROE': 'ROE',
                'Z_Score': 'Z-Score',
                'F_Score': 'F-Score'
            };

            let html = `<div class="section-title">HISTORICAL · ${data.ticker} @ ${data.price}</div>`;
            html += '<div class="table-container"><table><thead><tr>';

            columns.forEach(col => {
                const headerText = headers[col] || col;
                html += `<th>${headerText}</th>`;
            });

            html += '</tr></thead><tbody>';

            data.data.forEach(row => {
                html += '<tr>';
                columns.forEach(col => {
                    const isTextCol = ['Year', 'Report Date'].includes(col);
                    html += `<td class="${isTextCol ? 'text-col' : 'num-col'}">${row[col]}</td>`;
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';
            document.getElementById('content').innerHTML = html;
        }

        function setSortColumn(col) {
            if (sortCol === col) {
                sortReverse = !sortReverse;
            } else {
                sortCol = col;
                sortReverse = false;
            }
            loadScreener();
        }

        function selectTicker(ticker) {
            selectedTicker = ticker;
            switchView('details');
        }

        async function showFilterModal(type) {
            filterType = type;
            const items = availableFilters[type === 'sectors' ? 'sectors' : 'industries'];
            const selected = availableFilters[type === 'sectors' ? 'selected_sectors' : 'selected_industries'];

            let content = '';
            items.forEach(item => {
                const isChecked = selected.includes(item);
                content += `
                    <div class="form-check">
                        <input class="form-check-input filter-item" type="checkbox" id="filter_${item}" 
                               value="${item}" ${isChecked ? 'checked' : ''}>
                        <label class="form-check-label" for="filter_${item}">
                            ${item || '(Other)'}
                        </label>
                    </div>
                `;
            });

            document.getElementById('filterModalTitle').textContent = `Select ${type.charAt(0).toUpperCase() + type.slice(1)}`;
            document.getElementById('filterContent').innerHTML = content;

            new bootstrap.Modal(document.getElementById('filterModal')).show();
        }

        function selectAllFilters() {
            document.querySelectorAll('.filter-item').forEach(cb => cb.checked = true);
        }

        function deselectAllFilters() {
            document.querySelectorAll('.filter-item').forEach(cb => cb.checked = false);
        }

        async function applyFilters() {
            const selected = Array.from(document.querySelectorAll('.filter-item:checked')).map(cb => cb.value);

            const payload = filterType === 'sectors'
                ? { sectors: selected, industries: availableFilters.selected_industries }
                : { sectors: availableFilters.selected_sectors, industries: selected };

            await fetch('/api/filters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            loadScreener();
        }

        function updateStatus(msg) {
            document.getElementById('statusLabel').textContent = msg;
        }

        // Initialize on page load
        window.addEventListener('load', initApp);
    </script>
</body>
</html>
        """

    def load_data(self):
        """Load all data in background thread."""
        def _worker():
            try:
                self.loading_status = "Loading all ticker data…"

                if self.cache is not None:
                    try:
                        all_tickers_data = []
                        for ticker in self.ticker_list:
                            df = self.cache.read_ticker(ticker)
                            if not df.empty:
                                all_tickers_data.append(df)

                        if all_tickers_data:
                            self.all_data = pd.concat(all_tickers_data, ignore_index=True)
                            self.all_data = apply_formatting(self.all_data)
                            self.loading_status = "Screener loaded from cache."
                            self.loading_complete = True
                            return
                    except Exception as e:
                        log.warning(f"Cache load failed: {e}")

                # Fall back: load first ticker as demo
                if self.ticker_list:
                    raw = self.pull_fn([self.ticker_list[0]])
                    self.all_data = self.calc_fn(df_=raw)
                    self.loading_status = "Demo data loaded (cache not available)."
                    self.loading_complete = True

            except Exception as e:
                log.error(f"Error loading data: {e}")
                self.loading_status = f"Error loading data: {str(e)}"
                self.loading_complete = True

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def run(self):
        """Start the FastAPI server."""
        import uvicorn

        self.load_data()

        log.info(f"\n{'='*70}")
        log.info(f"  GrahamQuant Web UI starting…")
        log.info(f"  Open your browser: http://{self.host}:{self.port}")
        log.info(f"{'='*70}\n")

        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )


# ── Formatting helpers ────────────────────────────────────────────────────────
def _is_na(val) -> bool:
    """Check if a value is N/A."""
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    if str(val).strip() in ("N/A", "nan", "", "<NA>"):
        return True
    return False


def _fmt(val, col: str) -> str:
    """Format a value for display."""
    if _is_na(val):
        return "N/A"

    if isinstance(val, str):
        return val

    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)

    if pd.isna(v):
        return "N/A"

    passthrough_cols = {"Year", "Report Date", "Ticker", "Region", "Company Name", "Sector", "Industry",
                        "Trading Currency", "Financial Currency"}
    if col in passthrough_cols:
        return str(int(v)) if v == int(v) else str(v)

    # Ratio columns
    ratio_cols = {
        "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
        "Price_NCAV_Ratio", "Price_NCAV_Inv_Ratio",
        "PE_Ratio", "PE_Ratio_TTM", "Z_Score"
    }
    pct_cols = {"ROE", "ROE_5YR", "ROA"}
    score_cols = {"F_Score"}

    if col in ratio_cols:
        if v < 0 or v != v:
            return "N/A"
        return f"{v:.2f}x"

    if col in pct_cols:
        return f"{v:.2%}"

    if col in score_cols:
        return str(int(round(v)))

    # Currency / large numbers
    if v < 0:
        sign, av = "-", abs(v)
    else:
        sign, av = "", v

    if av >= 1_000_000_000_000:
        return f"{sign}{av / 1_000_000_000_000:.1f}t"
    elif av >= 1_000_000_000:
        return f"{sign}{av / 1_000_000_000:.1f}b"
    elif av >= 1_000_000:
        return f"{sign}{av / 1_000_000:.1f}m"
    elif av >= 1_000:
        return f"{sign}{av / 1_000:.1f}k"
    return f"{sign}{v:.1f}"


# ──────────────────────────────────────────────────────────────────────────────
def launch(ticker_list: list, pull_fn, calc_fn, cache=None, host: str = "127.0.0.1", port: int = 8000):
    """Entry point — called from main.py."""
    app = GrahamQuantWebApp(
        ticker_list=ticker_list,
        pull_fn=pull_fn,
        calc_fn=calc_fn,
        cache=cache,
        host=host,
        port=port,
    )
    app.run()
