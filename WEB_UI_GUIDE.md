# FastAPI Web UI for GrahamQuant

## Overview

The GrahamQuant screener now includes a modern **FastAPI + HTML web interface** as an alternative to the tkinter desktop UI. This web-based UI runs locally in your browser and provides the same functionality as the desktop version with a responsive, Bloomberg-style dark theme.

## Installation

### Prerequisites

Ensure you have FastAPI and Uvicorn installed:

```bash
pip install fastapi uvicorn
```

If these aren't already in your environment, install them:

```bash
pip install fastapi uvicorn pandas
```

## Launching the Web UI

### Basic Usage

To launch the web UI:

```bash
python main.py --web
```

This starts the server on `http://127.0.0.1:8000` and automatically opens in your browser.

### Advanced Options

#### Host on a Different Port
```bash
python main.py --web --port 9000
```
Access at: `http://127.0.0.1:9000`

#### Make the UI Accessible from Other Machines
```bash
python main.py --web --host 0.0.0.0
```
Then access from another machine at: `http://<your-machine-ip>:8000`

#### Combine with Data Refresh
```bash
python main.py --refresh --web
```
Refreshes data, then launches the web UI.

## Features

### Screener View
- **Population Table**: View all tickers with the latest year metrics
- **Column Headers**: Click headers to sort by any column (ascending/descending)
- **Dynamic Filtering**: 
  - Filter by Sectors/Regions
  - Filter by Industries
  - Real-time row count display
- **Metrics Displayed**:
  - Ticker, Company Name, Sector, Industry, Market Cap
  - P/B Ratio, P/NCAV Ratio, Z-Score, F-Score, ROE
  - Net Debt/EBITDA, Dividend Yield

### Details View
- **Historical Data**: Click any ticker to see its full history
- **Time Series Metrics**: View year-over-year changes for:
  - Market Cap, Book Value, NCAV
  - Asset/Liability/Equity figures
  - All valuation ratios and scores

## Default UI (Tkinter)

To use the original tkinter UI, simply run without the `--web` flag:

```bash
python main.py
```

## How It Works

### Backend (FastAPI)
- **`ui_fastapi.py`**: Main FastAPI application
- **Data Loading**: Loads ticker data from cache in background thread
- **API Endpoints**:
  - `GET /` - Serve main HTML page
  - `GET /api/status` - Get loading status
  - `GET /api/screener` - Get filtered/sorted screener data
  - `GET /api/filters` - Get available filter options
  - `POST /api/filters` - Update selected filters
  - `GET /api/details/{ticker}` - Get historical details for a ticker

### Frontend (HTML/JavaScript)
- **Single-page application** with no external dependencies (except Bootstrap for styling)
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Dark Theme**: Bloomberg-style dark color scheme matching the tkinter UI
- **Real-time Updates**: Filter and sort without page reload

## Keyboard Shortcuts & Navigation

- **Sort Columns**: Click any column header to sort ascending/descending
- **Filter Dialog**: Click "Select Sectors" or "Select Industries" buttons
- **View Details**: Double-click a row to view historical details
- **Quick Filters**: Use Select All/Deselect All in filter dialogs

## Browser Compatibility

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Troubleshooting

### Port Already in Use
If port 8000 is already in use:
```bash
python main.py --web --port 8001
```

### Cannot Connect from Another Machine
Make sure to use:
```bash
python main.py --web --host 0.0.0.0
```
Then access from: `http://<your-ip>:8000`

### Data Not Loading
- Check that cache is available: `python main.py --screen`
- Refresh data if needed: `python main.py --refresh --web`
- Check server logs for errors

### Slow Performance
- The initial data load happens in the background and may take 10-30 seconds depending on your cache size
- All subsequent operations (filtering, sorting, selection) are instant

## Customization

To modify the UI appearance or layout, edit the HTML/CSS/JavaScript within `ui_fastapi.py`. The entire UI is embedded as a single string for easy deployment.

### Themes
To change colors, modify these CSS variables in the `<style>` section:
```css
--bg: #0f1117;           /* Background */
--surface: #1a1d27;      /* Surface/panels */
--accent: #f0f2fa;       /* Accent color (gold) */
--neg: #e05c5c;          /* Negative values */
--neutral: #8b8fa8;      /* Neutral text */
--body: #d4d7e3;         /* Body text */
```

## Performance Notes

- **Initial Load**: Data loads asynchronously in background
- **Filtering/Sorting**: All operations performed server-side for accuracy
- **Memory**: Holds all cached data in memory (typical ~10-50MB for large screens)
- **Concurrent Users**: Designed for single user (local development use)

## Comparison: Web UI vs Tkinter UI

| Feature | Web UI | Tkinter UI |
|---------|--------|-----------|
| Modern Interface | ✓ | Limited |
| Responsive Design | ✓ | Fixed |
| Browser-based | ✓ | Desktop |
| Remote Access | ✓ | ✗ |
| Lightweight | ✓ | ✓ |
| Offline Use | ✓ | ✓ |
| No Installation | ✓ | ✗ |
| Cross-platform | ✓ | ✓ |

## Future Enhancements

Potential additions:
- Export data to CSV
- Custom column selection
- Advanced filtering rules
- Portfolio tracking
- Price alerts
- Dark/Light theme toggle
- Mobile app version

## Support

For issues or feature requests, refer to the main GrahamQuant documentation or submit an issue to the project repository.
