# AI Smart Visitor Dashboard — Setup Guide

## File structure

```
dashboard/
├── app.py                  ← Streamlit entry point
├── data_source.py          ← ALL mock data lives here (swap to real data here)
├── requirements.txt
└── pages_src/
    ├── __init__.py
    ├── page1_realtime.py   ← Page 1: real-time monitoring + door block
    ├── page2_analytics.py  ← Page 2: visitor analytics + stranger gallery
    └── page3_logs.py       ← Page 3: audit logs + export
```

## Run locally (for RAM testing)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Run on Raspberry Pi

```bash
# Keep backend (face recognition) separate from dashboard:
python3 security_backend.py &   # your main Pi detection script
streamlit run app.py --server.port 8501 --server.headless true
```

Then open http://<pi-ip>:8501 on any device on the same network.

## How to swap mock data → real data

All swap points are in **data_source.py**.
Search for the comment `# ── REAL DATA SWAP ──` to find every location.

| Function              | What to replace with                              |
|-----------------------|---------------------------------------------------|
| `get_system_state()`  | MQTT subscriber reading Pi JSON payload           |
| `get_ram_usage()`     | psutil readings published via MQTT from Pi        |
| `get_today_summary()` | pandas groupby on `security_logs.csv`             |
| `get_activity_timeline()` | pandas read of last N rows in CSV           |
| `get_stranger_gallery()` | glob scan of `images/stranger_*.jpg`         |
| `get_full_logs()`     | `pd.read_csv("security_logs.csv")`                |

## RAM budget (Streamlit side only)

| Component             | Approx RAM  |
|-----------------------|-------------|
| Streamlit + OS        | ~600 MB     |
| plotly charts         | ~50 MB      |
| pandas + data         | ~20 MB      |
| **Total dashboard**   | **~670 MB** |

The face recognition model and OpenCV run in your separate backend process,
not inside Streamlit — this keeps the dashboard well within 1 GB.

## Auto-refresh for live data

Add this to page1_realtime.py `render()` function:

```python
import time
st_autorefresh = st.empty()
# Refresh every 5 seconds
st.markdown('<meta http-equiv="refresh" content="5">', unsafe_allow_html=True)
```

Or use the `streamlit-autorefresh` package:
```bash
pip install streamlit-autorefresh
```
```python
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=5000, key="live_refresh")
```
