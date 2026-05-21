"""
src/grahamquant/ui.py

Tkinter proof-of-concept front end for GrahamQuant.

Layout
------
  Top bar    : app title + version tag
  Toolbar    : ticker dropdown, Load button, status label
  Mid panel  : Current-year statistical summary (metric tiles)
  Bot panel  : Full historical table (all reporting years, scrollable)

Aesthetic: dark terminal / Bloomberg-style.
  Background  : #0f1117  (near-black)
  Surface     : #1a1d27  (card / panel)
  Border      : #2a2d3a
  Accent      : #c9a84c  (gold)
  Negative    : #e05c5c  (muted red)
  Neutral txt : #8b8fa8
  Body txt    : #d4d7e3
  Mono font   : Courier New (cross-platform, ideal for numeric alignment)
"""

import threading
import tkinter as tk
from tkinter import ttk

import pandas as pd
from src.grahamquant.formulas_calcs import apply_formatting

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#0f1117"
SURFACE   = "#1a1d27"
BORDER    = "#2a2d3a"
ACCENT    = "#c9a84c"
NEG       = "#e05c5c"
NEUTRAL   = "#8b8fa8"
BODY      = "#d4d7e3"
WHITE     = "#f0f2fa"
HIGHLIGHT = "#252838"

# ── Metric tile config ────────────────────────────────────────────────────────
SUMMARY_METRICS = [
    ("Market Cap",        "Market Cap"),
    ("Book Value",        "Book_Value"),
    ("Tangible BV",       "Tangible_Book_Value"),
    ("NCAV",              "NCAV"),
    ("NCAV + Inv",        "NCAV_Inv"),
    ("Total Assets",      "Total Assets"),
    ("Total Liabilities", "Total Liabilities"),
    ("Total Equity",      "Total Equity"),
    ("FY Net Income",     "Latest FY Net Income"),
    ("TTM Net Income",    "TTM Net Income"),
    ("P/Book",            "Price_Book_Ratio"),
    ("P/Tang BV",         "Price_Tangible_Book_Ratio"),
    ("P/NCAV",            "Price_NCAV_Ratio"),
    ("PE (FY)",           "PE_Ratio"),
    ("PE (TTM)",          "PE_Ratio_TTM"),
    ("ROE",               "ROE"),
]

HISTORY_COLUMNS = [
    "Year", "Report Date",
    "Market Cap", "Book_Value", "Tangible_Book_Value",
    "NCAV", "NCAV_Inv",
    "Total Assets", "Total Liabilities", "Total Equity",
    "Latest FY Net Income",
    "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
    "Price_NCAV_Ratio", "PE_Ratio", "ROE",
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
}

COL_WIDTHS = {
    "Year": 50, "Report Date": 100,
}
DEFAULT_COL_WIDTH = 95


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
    """
    Format a value for display. Handles both:
      - Raw numerics from cache (floats)
      - Pre-formatted strings from create_calcs ("1.5b", "N/A", "1.23x")
    """
    if _is_na(val):
        return "N/A"

    # Already a formatted string — pass through
    if isinstance(val, str):
        return val

    # Raw numeric — format based on column type
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)

    if pd.isna(v):
        return "N/A"

    # Columns that should never be magnitude-formatted
    passthrough_cols = {"Year", "Report Date", "Ticker", "Region",
                        "Trading Currency", "Financial Currency"}
    if col in passthrough_cols:
        # Return as clean integer string if it's a whole number
        return str(int(v)) if v == int(v) else str(v)

    # Ratio / percentage columns
    ratio_cols = {
        "Price_Book_Ratio", "Price_Tangible_Book_Ratio",
        "Price_NCAV_Ratio", "Price_NCAV_Inv_Ratio",
        "PE_Ratio", "PE_Ratio_TTM",
    }
    pct_cols = {"ROE", "ROE_5YR"}

    if col in ratio_cols:
        if v < 0 or v != v:   # negative or NaN
            return "N/A"
        return f"{v:.2f}x"

    if col in pct_cols:
        return f"{v:.2%}"

    # Currency / large number columns
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
        self._cache       = cache   # CacheManager instance (optional for now)

        self.title("GrahamQuant")
        self.configure(bg=BG)
        self.geometry("1280x860")
        self.minsize(960, 640)

        self._build_styles()
        self._build_ui()

    # ── Styles ────────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".", background=BG, foreground=BODY, font=("Courier New", 10))

        s.configure("Toolbar.TFrame",  background=SURFACE)
        s.configure("Toolbar.TLabel",  background=SURFACE, foreground=NEUTRAL, font=("Courier New", 10))
        s.configure("Title.TLabel",    background=BG,      foreground=ACCENT,  font=("Courier New", 16, "bold"))
        s.configure("Sub.TLabel",      background=BG,      foreground=NEUTRAL, font=("Courier New", 9))
        s.configure("Section.TLabel",  background=BG,      foreground=ACCENT,  font=("Courier New", 11, "bold"))

        s.configure("TCombobox",
            fieldbackground=SURFACE, background=SURFACE,
            foreground=WHITE, selectbackground=HIGHLIGHT,
            selectforeground=WHITE, arrowcolor=ACCENT)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("readonly", WHITE)])

        s.configure("Accent.TButton",
            background=ACCENT, foreground="#0f1117",
            font=("Courier New", 10, "bold"), padding=(16, 6), relief="flat")
        s.map("Accent.TButton",
            background=[("active", "#e0be6a"), ("pressed", "#a88930"), ("disabled", BORDER)])

        s.configure("Hist.Treeview",
            background=SURFACE, foreground=BODY,
            fieldbackground=SURFACE, rowheight=24,
            font=("Courier New", 9))
        s.configure("Hist.Treeview.Heading",
            background=BORDER, foreground=ACCENT,
            font=("Courier New", 9, "bold"), relief="flat")
        s.map("Hist.Treeview",
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
        ttk.Label(title_bar, text="  //  deep value screen",
                  style="Sub.TLabel").pack(side="left", padx=(6, 0))

        # ---- Toolbar ----
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(24, 10))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="TICKER :", style="Toolbar.TLabel").pack(side="left")

        self._ticker_var = tk.StringVar()
        self._combo = ttk.Combobox(
            toolbar,
            textvariable=self._ticker_var,
            values=self._ticker_list,
            state="readonly",
            width=15,
        )
        self._combo.pack(side="left", padx=(8, 14))
        if self._ticker_list:
            self._combo.current(0)

        self._load_btn = ttk.Button(
            toolbar, text="▶  LOAD",
            style="Accent.TButton",
            command=self._on_load,
        )
        self._load_btn.pack(side="left")

        self._status_var = tk.StringVar(value="Select a ticker and press LOAD.")
        self._status_label = tk.Label(
            toolbar,
            textvariable=self._status_var,
            bg=SURFACE, fg=NEUTRAL,
            font=("Courier New", 9),
        )
        self._status_label.pack(side="left", padx=20)

        # ---- Gold accent line ----
        tk.Frame(self, bg=ACCENT, height=1).pack(fill="x")

        # ---- Scrollable body ----
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        v_scroll = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._body = tk.Frame(self._canvas, bg=BG)
        self._body_id = self._canvas.create_window((0, 0), window=self._body, anchor="nw")

        self._body.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._body_id, width=e.width))
        self._canvas.bind_all("<MouseWheel>", lambda e: self._canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))

        # ---- Summary section ----
        sum_outer = tk.Frame(self._body, bg=BG, padx=24, pady=18)
        sum_outer.pack(fill="x")

        ttk.Label(sum_outer,
                  text="CURRENT YEAR  ·  STATISTICAL SUMMARY",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 10))

        self._tiles_frame = tk.Frame(sum_outer, bg=BG)
        self._tiles_frame.pack(fill="x")

        self._placeholder_lbl = tk.Label(
            self._tiles_frame,
            text="No data loaded. Select a ticker above.",
            bg=BG, fg=NEUTRAL, font=("Courier New", 10),
        )
        self._placeholder_lbl.grid(row=0, column=0, sticky="w", pady=4)

        # ---- Divider ----
        tk.Frame(self._body, bg=BORDER, height=1).pack(fill="x", padx=24, pady=2)

        # ---- History section ----
        hist_outer = tk.Frame(self._body, bg=BG, padx=24, pady=18)
        hist_outer.pack(fill="x")

        ttk.Label(hist_outer,
                  text="HISTORICAL  ·  ALL REPORTING YEARS",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 10))

        self._tree_frame = tk.Frame(hist_outer, bg=BG)
        self._tree_frame.pack(fill="x")
        self._build_tree()

    # ── Treeview ─────────────────────────────────────────────────────────────
    def _build_tree(self):
        self._tree = ttk.Treeview(
            self._tree_frame,
            columns=HISTORY_COLUMNS,
            show="headings",
            style="Hist.Treeview",
            height=14,
        )
        for col in HISTORY_COLUMNS:
            w = COL_WIDTHS.get(col, DEFAULT_COL_WIDTH)
            self._tree.heading(col, text=HISTORY_HEADERS.get(col, col), anchor="e")
            self._tree.column(col, width=w, anchor="e", minwidth=45, stretch=False)

        h_scroll = ttk.Scrollbar(self._tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(xscrollcommand=h_scroll.set)
        self._tree.pack(fill="x")
        h_scroll.pack(fill="x")

        self._tree.tag_configure("odd",  background=SURFACE)
        self._tree.tag_configure("even", background=BG)

    # ── Load ──────────────────────────────────────────────────────────────────
    def _on_load(self):
        ticker = self._ticker_var.get().strip()
        if not ticker:
            self._set_status("Please select a ticker.", NEG)
            return

        self._load_btn.config(state="disabled")
        self._clear_panels()

        def _worker():
            try:
                df, source = self._load_ticker(ticker)
                self.after(0, lambda: self._render(ticker, df, source))
            except Exception as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _load_ticker(self, ticker: str) -> tuple:
        """
        Load data for a ticker. Priority:
          1. Cache (raw floats) — format for display then return
          2. Live pull from yfinance (fallback) — calc + format then return
        Returns (df, source_label) where source_label is "cache" or "live".
        """
        # Try cache first
        if self._cache is not None:
            try:
                self._set_status_threadsafe(f"Checking cache for {ticker}…", NEUTRAL)
                df = self._cache.read_ticker(ticker)
                if not df.empty:
                    # Cache holds raw floats — format for display before rendering
                    df = apply_formatting(df)
                    return df, "cache"
            except Exception:
                pass  # fall through to live pull

        # Fall back to live pull
        self._set_status_threadsafe(f"Fetching {ticker} from Yahoo Finance…", NEUTRAL)
        raw = self._pull_fn(ticker_list=[ticker])
        df  = self._calc_fn(df_=raw)   # create_calcs = apply_calcs + apply_formatting
        return df, "live"

    def _set_status_threadsafe(self, msg: str, color: str = NEUTRAL):
        """Schedule a status update from a background thread."""
        self.after(0, lambda: self._set_status(msg, color))

    def _on_error(self, msg: str):
        self._set_status(f"Error: {msg}", NEG)
        self._load_btn.config(state="normal")

    # ── Render ────────────────────────────────────────────────────────────────
    def _render(self, ticker: str, df: pd.DataFrame, source: str = "live"):
        sub = df[df["Ticker"] == ticker] if "Ticker" in df.columns else df
        if sub.empty:
            self._set_status(f"No data returned for {ticker}.", NEG)
            self._load_btn.config(state="normal")
            return

        latest = sub.iloc[0]   # most recent year (sorted desc by create_calcs)
        self._render_summary(ticker, latest)
        self._render_history(sub)

        curr     = latest.get("Trading Currency", latest.get("Financial Currency", ""))
        n        = len(sub)
        src_tag  = "● CACHE" if source == "cache" else "○ LIVE"
        src_col  = ACCENT if source == "cache" else NEUTRAL
        self._set_status(
            f"{src_tag}  ·  {ticker}  ·  {n} reporting year{'s' if n != 1 else ''}  ·  {curr}",
            src_col,
        )
        self._load_btn.config(state="normal")

    def _render_summary(self, ticker: str, row: pd.Series):
        for w in self._tiles_frame.winfo_children():
            w.destroy()

        # Ticker badge row
        badge_frame = tk.Frame(self._tiles_frame, bg=BG)
        badge_frame.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 12))

        badge = tk.Frame(badge_frame, bg=ACCENT, padx=10, pady=4)
        badge.pack(side="left")
        raw_year = row.get("Year", None)
        year_str = str(int(float(raw_year))) if raw_year is not None and str(raw_year) not in ("", "N/A", "nan") else "—"
        tk.Label(
            badge,
            text=f" {ticker}  ·  FY {year_str}  ·  {row.get('Report Date', '—')} ",
            bg=ACCENT, fg="#0f1117",
            font=("Courier New", 10, "bold"),
        ).pack()

        # Currency note
        curr = row.get("Financial Currency", row.get("Trading Currency", ""))
        if curr:
            tk.Label(
                badge_frame,
                text=f"  reported in {curr}",
                bg=BG, fg=NEUTRAL,
                font=("Courier New", 9),
            ).pack(side="left", padx=8)

        # Metric tiles — 8 per row
        COLS = 8
        for idx, (label, col) in enumerate(SUMMARY_METRICS):
            r = (idx // COLS) + 1
            c = idx % COLS

            raw   = row.get(col, None) if col in row.index else None
            val   = _fmt(raw, col)
            color = _value_color(val)

            tile = tk.Frame(
                self._tiles_frame, bg=SURFACE,
                highlightbackground=BORDER, highlightthickness=1,
                padx=12, pady=9,
            )
            tile.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")

            tk.Label(tile, text=label.upper(),
                     bg=SURFACE, fg=NEUTRAL,
                     font=("Courier New", 7)).pack(anchor="w")
            tk.Label(tile, text=val,
                     bg=SURFACE, fg=color,
                     font=("Courier New", 13, "bold")).pack(anchor="w", pady=(3, 0))

        for c in range(COLS):
            self._tiles_frame.columnconfigure(c, weight=1)

    def _render_history(self, df: pd.DataFrame):
        for row in self._tree.get_children():
            self._tree.delete(row)

        for i, (_, row) in enumerate(df.iterrows()):
            values = [
                _fmt(row.get(col, None), col) if col in df.columns else "N/A"
                for col in HISTORY_COLUMNS
            ]
            tag = "odd" if i % 2 else "even"
            self._tree.insert("", "end", values=values, tags=(tag,))

    # ── Utilities ─────────────────────────────────────────────────────────────
    def _clear_panels(self):
        for w in self._tiles_frame.winfo_children():
            w.destroy()
        tk.Label(
            self._tiles_frame,
            text="Loading…",
            bg=BG, fg=NEUTRAL, font=("Courier New", 10),
        ).grid(row=0, column=0, sticky="w")

        for row in self._tree.get_children():
            self._tree.delete(row)

    def _set_status(self, msg: str, color: str = NEUTRAL):
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
