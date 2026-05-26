# FastAPI Web UI Requirements

## Installation

To use the new FastAPI web UI, install these additional packages:

```bash
pip install fastapi uvicorn
```

## Complete Requirements

If you want to install all dependencies at once, here's the full list for the web UI:

```bash
pip install fastapi uvicorn pandas numpy yfinance
```

### Breaking Down the Requirements:

- **fastapi** - Modern Python web framework
- **uvicorn** - ASGI server to run the FastAPI app
- **pandas** - Data manipulation (already in your project)
- **numpy** - Numerical operations (already in your project)
- **yfinance** - Financial data (already in your project)

## Quick Install

For just the new dependencies needed for the web UI:

```bash
pip install fastapi uvicorn
```

## Verification

To verify the installation:

```bash
python -c "import fastapi; print(f'FastAPI {fastapi.__version__} installed')"
python -c "import uvicorn; print(f'Uvicorn {uvicorn.__version__} installed')"
```

## Using Virtual Environment (Recommended)

If you use a virtual environment:

```bash
# Create a new environment (optional)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install fastapi uvicorn
```

## Troubleshooting Installation

### ImportError: No module named 'fastapi'

Install it:
```bash
pip install fastapi
```

### ImportError: No module named 'uvicorn'

Install it:
```bash
pip install uvicorn
```

### Both missing?

Install both together:
```bash
pip install fastapi uvicorn
```

## Version Compatibility

The web UI works with:
- **fastapi** >= 0.95.0
- **uvicorn** >= 0.21.0

## Optional: Create requirements-web.txt

If you want to track web UI dependencies separately:

Create a file `requirements-web.txt`:
```
fastapi>=0.95.0
uvicorn>=0.21.0
```

Then install with:
```bash
pip install -r requirements-web.txt
```

## Next Steps

Once installed, launch the web UI:

```bash
python main.py --web
```

The UI will open in your browser at `http://127.0.0.1:8000`

## Support

- FastAPI docs: https://fastapi.tiangolo.com/
- Uvicorn docs: https://www.uvicorn.org/
- FastAPI community: https://discuss.encode.io/
