# Quick Start: FastAPI Web UI vs Tkinter UI

## Installation

First, install FastAPI and Uvicorn if you haven't already:

```bash
pip install fastapi uvicorn
```

## Quick Reference

### Desktop UI (Tkinter) - Original
```bash
python main.py                    # Default UI (tkinter)
python main.py --refresh          # Refresh data + launch tkinter UI
```

### Web UI (FastAPI + HTML) - New
```bash
python main.py --web              # Launch web UI on localhost:8000
python main.py --web --port 9000  # Launch on custom port
python main.py --refresh --web    # Refresh data + launch web UI
```

### Advanced Web UI Options
```bash
# Make accessible from other machines on your network
python main.py --web --host 0.0.0.0

# Custom host and port
python main.py --web --host 0.0.0.0 --port 9000

# Full command with all options
python main.py --refresh --web --host 0.0.0.0 --port 8080
```

## Where to Access

| Command | URL |
|---------|-----|
| `python main.py --web` | `http://127.0.0.1:8000` |
| `python main.py --web --port 8001` | `http://127.0.0.1:8001` |
| `python main.py --web --host 0.0.0.0` | `http://YOUR_IP:8000` |

## Usage Comparison

| Task | Tkinter | Web UI |
|------|---------|--------|
| Sort by column | Click column header | Click column header |
| Filter by sector | "Select Regions" button | "Select Sectors" button |
| Filter by industry | "Select Industry" button | "Select Industries" button |
| View ticker history | Double-click row | Click row |
| Switch views | Click tab button | Click navigation button |
| Refresh data | Must restart | Automatic background reload |

## What Each UI Does

### Both UIs Include:
✓ Screener view with all ticker metrics  
✓ Details view with historical data  
✓ Dynamic filtering by sector/industry  
✓ Column-based sorting  
✓ Dark Bloomberg theme  
✓ Real-time status updates  

### Web UI Advantages:
✓ Modern responsive design  
✓ Access from any browser  
✓ Network-accessible (with --host 0.0.0.0)  
✓ Mobile-friendly interface  
✓ No desktop dependencies  

### Tkinter UI Advantages:
✓ Lighter weight  
✓ More traditional desktop feel  
✓ Direct system integration  

## Data Caching

Both UIs use the same cache:
- Cache location: `data/cache/`
- To refresh: `python main.py --refresh` (before launching either UI)
- To refresh specific region: `python main.py --refresh-region JP` then `--web`

## Troubleshooting

### "Port already in use"
Try a different port:
```bash
python main.py --web --port 8001
```

### Data loading slow
The first load reads all cached data. Subsequent operations are instant.

### Cannot see from other machine
Use `--host 0.0.0.0` to make it accessible network-wide:
```bash
python main.py --web --host 0.0.0.0
```

### Browser won't open automatically
Manual access:
- Web UI: `http://localhost:8000` (or your custom port)
- Check console for the URL if it doesn't display

## Example Workflows

### Workflow 1: Quick Check with Web UI
```bash
python main.py --web
# Browser opens → Explore screener → Done
```

### Workflow 2: Full Refresh + Web UI
```bash
python main.py --refresh --web
# Refreshes all regions → Web UI launches → Explore data
```

### Workflow 3: Share with Colleagues
```bash
python main.py --refresh --web --host 0.0.0.0 --port 8000
# Share your IP and port with teammates
# They access: http://YOUR_IP:8000
```

### Workflow 4: Generate Report
```bash
python main.py --screen           # Print net-net stocks
python main.py --refresh-only     # Silent refresh
```

## Browser Support

Web UI works on:
- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Next Steps

- Read `WEB_UI_GUIDE.md` for comprehensive documentation
- Try both UIs to see which you prefer
- Customize colors by editing `ui_fastapi.py`
- Set bookmarks for easy access
