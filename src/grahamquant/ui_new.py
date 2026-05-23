"""
src/grahamquant/ui_new.py

Enhanced Tkinter UI for GrahamQuant with two views:
  1. SCREENER VIEW: Population table with key metrics (Ticker, Name, Country, Industry, P/B, P/NCAV, Z-Score, F-Score, ROE%)
  2. DETAILS VIEW: Historical data for selected ticker

Aesthetic: dark terminal / Bloomberg-style
"""

import threading
import tkinter as tk
from tkinter import ttk

import pandas as pd
from src.grahamquant.formulas_calcs import apply_formatting

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#0f1117"
SURFACE   = "#1a1d27"
BORDER    = "#070707"
ACCENT    = "#f0f2fa"
NEG       = "#e05c5c"
NEUTRAL   = "#8b8fa8"
BODY      = "#d4d7e3"
WHITE     = "#f0f2fa"
HIGHLIGHT = "#252838"

# ── Screener columns ──────────────────────────────────────────────────────────
# Only latest year, one row per ticker
SCREENER_COLUMNS = [
    "Ticker", "Company Name", "Sector", "Industry", "Market Cap",
    "Price_Book_Ratio", "Price_NCAV_Ratio", "Z_Score", "F_Score", "ROE",
    "Net_Debt_EBITDA", "Dividend_Yield",
    "Cash_Pct_NCAV", "Receivables_Pct_NCAV", "Inventory_Pct_NCAV", "PPE_Pct_NCAV", "Other_Assets_Pct_NCAV"
]

SCREENER_HEADERS = {
    "Ticker": "Ticker",
    "Company Name": "Name",
    "Sector": "Sector",
    "Industry": "Industry",
    "Market Cap": "Mkt Cap",
    "Price_Book_Ratio": "P/B",
    "Price_NCAV_Ratio": "P/NCAV",
    "Z_Score": "Z-Score",
    "F_Score": "F-Score",
    "ROE": "ROE %",
    "Net_Debt_EBITDA": "ND/EBITDA",
    "Dividend_Yield": "Div Yield",
    "Cash_Pct_NCAV": "Cash %",
    "Receivables_Pct_NCAV": "AR %",
    "Inventory_Pct_NCAV": "Inv %",
    "PPE_Pct_NCAV": "PPE %",
    "Other_Assets_Pct_NCAV": "Other %",
}

SCREENER_COL_WIDTHS = {
    "Ticker": 60, "Company Name": 300, "Sector": 200, "Industry": 200, "Market Cap": 100,
    "Net_Debt_EBITDA": 100, "Dividend_Yield": 90,
    "Cash_Pct_NCAV": 75, "Receivables_Pct_NCAV": 75, "Inventory_Pct_NCAV": 75, 
    "PPE_Pct_NCAV": 75, "Other_Assets_Pct_NCAV": 75,
}
SCREENER_DEFAULT_WIDTH = 90

# ── Historical columns ────────────────────────────────────────────────────────
HISTORY_COLUMNS = [
    "Year", "Report Date",
    "Market Cap", "Book_Value", "Tangible_Book_Value",
    "NCAV", "NCAV_Inv",
    "Total Assets", "Total Liabilities", "Total Equity",
    "Latest FY Net Income",
    "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
    "Price_NCAV_Ratio", "PE_Ratio", "ROE", "Z_Score", "F_Score",
]

HISTORY_HEADERS = {
    "Year":                      "Year",
    "Report Date":               "Report Date",
    "Market Cap":                "Mkt Cap",
    "Book_Value":                "Book Val",
    "Tangible_Book_Value":       "Tang BV",
    "NCAV":                      "NCAV",
    "NCAV_Inv":                  "NCAV+Inv",
    "Total Assets":              "Assets",
    "Total Liabilities":         "Liabilities",
    "Total Equity":              "Equity",
    "Latest FY Net Income":      "Net Inc (FY)",
    "Price_Book_Ratio":          "P/B",
    "Price_Tangible_Book_Ratio": "P/TBV",
    "Price_NCAV_Ratio":          "P/NCAV",
    "PE_Ratio":                  "PE",
    "ROE":                       "ROE",
    "Z_Score":                   "Z-Score",
    "F_Score":                   "F-Score",
}

HISTORY_COL_WIDTHS = {
    "Year": 50, "Report Date": 100,
}
HISTORY_DEFAULT_WIDTH = 95


# ── Helpers ───────────────────────────────────────────────────────────────────
def _is_na(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    if str(val).strip() in ("N/A", "nan", "", "<NA>"):
        return True
    return False


def _fmt(val, col: str) -> str:
    """Format a value for display. Handles both raw numerics and pre-formatted strings."""
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


def _value_color(val) -> str:
    s = str(val)
    if _is_na(s):
        return NEUTRAL
    if s.startswith("-"):
        return NEG
    return BODY


# ══════════════════════════════════════════════════════════════════════════════
class GrahamQuantApp(tk.Tk):

    def __init__(self, ticker_list: list, pull_fn, calc_fn, cache=None):
        super().__init__()
        self._ticker_list = ticker_list
        self._pull_fn     = pull_fn
        self._calc_fn     = calc_fn
        self._cache       = cache

        self._all_data = None    # Full dataset for screener
        self._view_mode = "screener"  # "screener" or "details"
        self._selected_ticker = None
        self._sort_col = None
        self._sort_reverse = False
        self._active_regions = set()
        self._active_industries = set()
        self._filter_vars = {}

        self.title("GrahamQuant")
        self.configure(bg=BG)
        self.geometry("1600x900")
        self.minsize(1200, 700)

        self._build_styles()
        self._build_ui()
        self._load_all_data()

    # ── Styles ────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", background=BG, foreground=BODY, font=("Courier New", 10))
        s.configure("Toolbar.TFrame", background=SURFACE)
        s.configure("Toolbar.TLabel", background=SURFACE, foreground=NEUTRAL, font=("Courier New", 10))
        s.configure("Title.TLabel", background=BG, foreground=ACCENT, font=("Courier New", 16, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground=NEUTRAL, font=("Courier New", 9))
        s.configure("Section.TLabel", background=BG, foreground=ACCENT, font=("Courier New", 11, "bold"))

        s.configure("Tab.TButton",
            background=BORDER, foreground=NEUTRAL,
            font=("Courier New", 9), padding=(12, 6), relief="flat")
        s.map("Tab.TButton",
            background=[("active", SURFACE), ("pressed", ACCENT)],
            foreground=[("active", BODY), ("pressed", "#0f1117")])

        s.configure("Accent.TButton",
            background=ACCENT, foreground="#0f1117",
            font=("Courier New", 10, "bold"), padding=(16, 6), relief="flat")
        s.map("Accent.TButton",
            background=[("active", "#e0be6a"), ("pressed", "#a88930")])

        s.configure("Screen.Treeview",
            background=SURFACE, foreground=BODY,
            fieldbackground=SURFACE, rowheight=24,
            font=("Courier New", 9))
        s.configure("Screen.Treeview.Heading",
            background=BORDER, foreground=ACCENT,
            font=("Courier New", 9, "bold"), relief="flat")
        s.map("Screen.Treeview",
            background=[("selected", HIGHLIGHT)],
            foreground=[("selected", WHITE)])

        s.configure("TScrollbar",
            background=SURFACE, troughcolor=BG,
            arrowcolor=NEUTRAL, bordercolor=BORDER)

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # ---- Title bar ----
        title_bar = tk.Frame(self, bg=BG, padx=24, pady=14)
        title_bar.pack(fill="x")
        ttk.Label(title_bar, text="GRAHAMQUANT", style="Title.TLabel").pack(side="left")
        ttk.Label(title_bar, text="  //  Deep Value Screener", style="Sub.TLabel").pack(side="left", padx=(6, 0))

        # ---- Toolbar with view tabs ----
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(24, 10))
        toolbar.pack(fill="x")

        self._screener_btn = ttk.Button(
            toolbar, text="✓  SCREENER (Population)",
            style="Tab.TButton",
            command=lambda: self._switch_view("screener"),
        )
        self._screener_btn.pack(side="left", padx=4)

        self._details_btn = ttk.Button(
            toolbar, text="◆  HISTORICAL DETAILS",
            style="Tab.TButton",
            command=lambda: self._switch_view("details"),
            state="disabled",
        )
        self._details_btn.pack(side="left", padx=4)

        self._status_var = tk.StringVar(value="Loading all ticker data…")
        self._status_label = tk.Label(
            toolbar,
            textvariable=self._status_var,
            bg=SURFACE, fg=NEUTRAL,
            font=("Courier New", 9),
        )
        self._status_label.pack(side="left", padx=20)

        # ---- Gold accent line ----
        tk.Frame(self, bg=ACCENT, height=1).pack(fill="x")

        # ---- Main content area ----
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True)

    def _switch_view(self, mode: str):
        """Switch between screener and details view."""
        self._view_mode = mode
        
        for w in self._content.winfo_children():
            w.destroy()

        if mode == "screener":
            self._screener_btn.config(state="pressed")
            self._details_btn.config(state="normal")
            self._render_screener()
        else:
            self._screener_btn.config(state="normal")
            self._details_btn.config(state="pressed")
            if self._selected_ticker:
                self._render_details()
            else:
                tk.Label(
                    self._content,
                    text="Please select a ticker from the screener view.",
                    bg=BG, fg=NEUTRAL,
                    font=("Courier New", 10),
                ).pack(pady=20)

    def _render_screener(self):
        """Render the population screener table with filters and sorting."""
        outer = tk.Frame(self._content, bg=BG, padx=24, pady=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer,
                  text="SCREENER  ·  ALL TICKERS  ·  LATEST YEAR",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 10))

        # ---- Filter panel ----
        if self._all_data is not None and not self._all_data.empty:
            latest_df = self._all_data.sort_values("Year", ascending=False).drop_duplicates("Ticker")
            
            # Get unique regions and industries
            regions = sorted(latest_df["Sector"].dropna().unique())
            industries = sorted(latest_df["Industry"].dropna().unique())
            
            # Initialize filter vars if not already done
            for region in regions:
                if f"region_{region}" not in self._filter_vars:
                    self._filter_vars[f"region_{region}"] = tk.BooleanVar(value=True)
            for industry in industries:
                if f"industry_{industry}" not in self._filter_vars:
                    self._filter_vars[f"industry_{industry}"] = tk.BooleanVar(value=True)
            
            filter_frame = tk.Frame(outer, bg=SURFACE, padx=12, pady=10)
            filter_frame.pack(fill="x", pady=(0, 12))
            
            # Region filter button
            tk.Label(filter_frame, text="REGIONS:", bg=SURFACE, fg=ACCENT, font=("Calibri", 9, "bold")).pack(side="left", padx=(0, 10))
            self._region_btn = ttk.Button(
                filter_frame,
                text="Select Regions",
                command=lambda: self._show_filter_dialog("region", regions)
            )
            self._region_btn.pack(side="left", padx=(0, 20))
            self._region_btn_label = tk.Label(filter_frame, text="", bg=SURFACE, fg=ACCENT, font=("Calibri", 8))
            self._region_btn_label.pack(side="left", padx=(0, 20))
            
            # Industry filter button
            tk.Label(filter_frame, text="INDUSTRY:", bg=SURFACE, fg=ACCENT, font=("Calibri", 9, "bold")).pack(side="left", padx=(0, 10))
            self._industry_btn = ttk.Button(
                filter_frame,
                text="Select Industry",
                command=lambda: self._show_filter_dialog("industry", industries)
            )
            self._industry_btn.pack(side="left", padx=(0, 20))
            self._industry_btn_label = tk.Label(filter_frame, text="", bg=SURFACE, fg=ACCENT, font=("Calibri", 8))
            self._industry_btn_label.pack(side="left")
            
            # Update labels with selection counts
            self._update_filter_labels(regions, industries)

        # ---- Treeview ----
        tree_frame = tk.Frame(outer, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        self._screener_tree = ttk.Treeview(
            tree_frame,
            columns=SCREENER_COLUMNS,
            show="headings",
            style="Screen.Treeview",
            height=20,
        )

        for col in SCREENER_COLUMNS:
            w = SCREENER_COL_WIDTHS.get(col, SCREENER_DEFAULT_WIDTH)
            self._screener_tree.heading(col, text=SCREENER_HEADERS.get(col, col), anchor="w", command=lambda c=col: self._on_sort(c))
            # Left-align text columns (Ticker, Name, Sector, Industry), right-align numeric columns
            if col in ("Ticker", "Company Name", "Sector", "Industry"):
                col_anchor = "w"
            else:
                col_anchor = "e"
            self._screener_tree.column(col, width=w, anchor=col_anchor, minwidth=45, stretch=False)

        # Populate with filtered/sorted data
        self._populate_screener()

        h_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._screener_tree.xview)
        self._screener_tree.configure(xscrollcommand=h_scroll.set)
        self._screener_tree.pack(fill="both", expand=True)
        h_scroll.pack(fill="x")

        self._screener_tree.tag_configure("odd", background=SURFACE)
        self._screener_tree.tag_configure("even", background=BG)

        # Double-click to view details
        def on_tree_double_click(event):
            if not self._screener_tree.selection():
                return
            item = self._screener_tree.selection()[0]
            ticker_val = self._screener_tree.item(item)["values"][0]
            self._selected_ticker = ticker_val
            self._details_btn.config(state="normal")
            self._switch_view("details")

        self._screener_tree.bind("<Double-1>", on_tree_double_click)

    def _populate_screener(self):
        """Populate screener with filtered and sorted data."""
        # Clear existing rows
        for item in self._screener_tree.get_children():
            self._screener_tree.delete(item)

        if self._all_data is None or self._all_data.empty:
            return

        # Get latest year for each ticker
        latest_df = self._all_data.sort_values("Year", ascending=False).drop_duplicates("Ticker").copy()

        # Apply filters
        active_regions = {k.replace("region_", ""): v.get() for k, v in self._filter_vars.items() if k.startswith("region_")}
        active_industries = {k.replace("industry_", ""): v.get() for k, v in self._filter_vars.items() if k.startswith("industry_")}

        if active_regions:
            latest_df = latest_df[latest_df["Sector"].isin([r for r, v in active_regions.items() if v])]
        if active_industries:
            latest_df = latest_df[latest_df["Industry"].isin([i for i, v in active_industries.items() if v])]

        # Apply sorting
        if self._sort_col:
            # Convert formatted values back to numeric for proper sorting
            try:
                latest_df = latest_df.sort_values(self._sort_col, ascending=not self._sort_reverse, na_position='last')
            except Exception:
                pass

        # Populate rows
        for i, (_, row) in enumerate(latest_df.iterrows()):
            values = []
            for col in SCREENER_COLUMNS:
                raw = row.get(col, None) if col in row.index else None
                val = _fmt(raw, col)
                values.append(val)

            tag = "odd" if i % 2 else "even"
            self._screener_tree.insert("", "end", values=values, tags=(tag,))

        self._status_var.set(f"Displayed {len(latest_df)} of {len(self._all_data.drop_duplicates('Ticker'))} tickers. Click headers to sort.")

    def _show_filter_dialog(self, filter_type: str, items: list):
        """Show a popup dialog for selecting filter items."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Select {filter_type.capitalize()}")
        dialog.geometry("1200x600")
        dialog.configure(bg=BG)
        
        # Create frame for checkboxes with scrollbar
        canvas = tk.Canvas(dialog, bg=SURFACE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=SURFACE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Add checkboxes
        checkbox_vars = []
        for item in items:
            var_key = f"{filter_type}_{item}"
            var = self._filter_vars.get(var_key, tk.BooleanVar(value=True))
            self._filter_vars[var_key] = var
            checkbox_vars.append((item, var))
            
            cb = tk.Checkbutton(
                scrollable_frame,
                text=item if item else "Other",
                variable=var,
                bg=SURFACE, fg=BODY,
                selectcolor=SURFACE,
                activebackground=SURFACE,
                activeforeground=ACCENT,
                font=("Calibri", 9),
            )
            cb.pack(anchor="w", padx=10, pady=4)
        
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        
        # Buttons
        button_frame = tk.Frame(dialog, bg=BG, pady=10)
        button_frame.pack(fill="x")
        
        def on_ok():
            self._on_filter_change()
            dialog.destroy()
        
        def select_all():
            for _, var in checkbox_vars:
                var.set(True)
        
        def deselect_all():
            for _, var in checkbox_vars:
                var.set(False)
        
        ttk.Button(button_frame, text="Select All", command=select_all).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Deselect All", command=deselect_all).pack(side="left", padx=5)
        ttk.Button(button_frame, text="OK", command=on_ok).pack(side="right", padx=5)

    def _update_filter_labels(self, regions: list, industries: list):
        """Update the filter button labels with selection counts."""
        if hasattr(self, '_region_btn_label'):
            selected_regions = [r for r in regions if self._filter_vars.get(f"region_{r}", tk.BooleanVar(value=True)).get()]
            self._region_btn_label.config(text=f"({len(selected_regions)}/{len(regions)})")
        
        if hasattr(self, '_industry_btn_label'):
            selected_industries = [i for i in industries if self._filter_vars.get(f"industry_{i}", tk.BooleanVar(value=True)).get()]
            self._industry_btn_label.config(text=f"({len(selected_industries)}/{len(industries)})")

    def _on_filter_change(self):
        """Refresh screener when filter changes."""
        # Update filter labels if screener is active
        if self._view_mode == "screener" and self._all_data is not None and not self._all_data.empty:
            latest_df = self._all_data.sort_values("Year", ascending=False).drop_duplicates("Ticker")
            regions = sorted(latest_df["Sector"].dropna().unique())
            industries = sorted(latest_df["Industry"].dropna().unique())
            self._update_filter_labels(regions, industries)
        
        self._populate_screener()

    def _on_sort(self, col: str):
        """Handle column header click for sorting."""
        if self._sort_col == col:
            # Toggle sort direction
            self._sort_reverse = not self._sort_reverse
        else:
            # New column selected
            self._sort_col = col
            self._sort_reverse = False
        
        self._populate_screener()

    def _render_details(self):
        """Render historical details for selected ticker."""
        if not self._selected_ticker or self._all_data is None or self._all_data.empty:
            tk.Label(
                self._content,
                text="No data available.",
                bg=BG, fg=NEUTRAL,
                font=("Calibri", 10),
            ).pack(pady=20)
            return

        outer = tk.Frame(self._content, bg=BG, padx=24, pady=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer,
                  text=f"HISTORICAL  ·  {self._selected_ticker}",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 10))

        # Build treeview
        tree_frame = tk.Frame(outer, bg=BG)
        tree_frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            tree_frame,
            columns=HISTORY_COLUMNS,
            show="headings",
            style="Screen.Treeview",
            height=20,
        )

        for col in HISTORY_COLUMNS:
            w = HISTORY_COL_WIDTHS.get(col, HISTORY_DEFAULT_WIDTH)
            tree.heading(col, text=HISTORY_HEADERS.get(col, col), anchor="w")
            tree.column(col, width=w, anchor="e", minwidth=45, stretch=False)

        # Get all years for selected ticker
        ticker_df = self._all_data[self._all_data["Ticker"] == self._selected_ticker].sort_values("Year", ascending=False)

        for i, (_, row) in enumerate(ticker_df.iterrows()):
            values = []
            for col in HISTORY_COLUMNS:
                raw = row.get(col, None) if col in row.index else None
                val = _fmt(raw, col)
                values.append(val)

            tag = "odd" if i % 2 else "even"
            tree.insert("", "end", values=values, tags=(tag,))

        h_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=h_scroll.set)
        tree.pack(fill="both", expand=True)
        h_scroll.pack(fill="x")

        tree.tag_configure("odd", background=SURFACE)
        tree.tag_configure("even", background=BG)

        self._status_var.set(f"Showing {len(ticker_df)} reporting years for {self._selected_ticker}.")

    def _load_all_data(self):
        """Load all data in background and switch to screener view."""
        def _worker():
            try:
                self._set_status_threadsafe("Loading all ticker data…", NEUTRAL)
                
                if self._cache is not None:
                    # Try to load all cached data
                    try:
                        all_tickers_data = []
                        for ticker in self._ticker_list:
                            df = self._cache.read_ticker(ticker)
                            if not df.empty:
                                all_tickers_data.append(df)
                        
                        if all_tickers_data:
                            self._all_data = pd.concat(all_tickers_data, ignore_index=True)
                            self._all_data = apply_formatting(self._all_data)
                            self.after(0, lambda: self._switch_view("screener"))
                            self._set_status_threadsafe("Screener loaded from cache.", ACCENT)
                            return
                    except Exception:
                        pass

                # Fall back: load first ticker as demo
                if self._ticker_list:
                    raw = self._pull_fn([self._ticker_list[0]])
                    self._all_data = self._calc_fn(df_=raw)
                    self.after(0, lambda: self._switch_view("screener"))
                    self._set_status_threadsafe("Demo data loaded (cache not available).", NEUTRAL)

            except Exception as e:
                self._set_status_threadsafe(f"Error loading data: {str(e)}", NEG)

        threading.Thread(target=_worker, daemon=True).start()

    def _set_status_threadsafe(self, msg: str, color: str = NEUTRAL):
        """Schedule status update from background thread."""
        self.after(0, lambda: self._set_status(msg, color))

    def _set_status(self, msg: str, color: str = NEUTRAL):
        """Update status label."""
        self._status_var.set(msg)
        self._status_label.configure(fg=color)


# ══════════════════════════════════════════════════════════════════════════════
def launch(ticker_list: list, pull_fn, calc_fn, cache=None):
    """Entry point — called from main.py."""
    app = GrahamQuantApp(
        ticker_list=ticker_list,
        pull_fn=pull_fn,
        calc_fn=calc_fn,
        cache=cache,
    )
    app.mainloop()
