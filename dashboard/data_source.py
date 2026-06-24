"""
data_source.py — REAL DATA VERSION (Pi over Cloudflare Tunnel)

ARCHITECTURE
    This file runs on STREAMLIT COMMUNITY CLOUD (the public dashboard).
    It does NOT read local files — there are no local files on the cloud
    server. Instead it makes small HTTP requests to your Raspberry Pi's
    pi_server.py, reached through the Cloudflare Tunnel public URL.

    Pi (security_logs.csv, images/, state.json)
        → pi_server.py (FastAPI, runs on Pi)
        → Cloudflare Tunnel (public HTTPS URL)
        → THIS FILE fetches over HTTP
        → page1/2/3 render() functions (UNCHANGED — same shapes as before)

SETUP REQUIRED
    1. Set PI_API_URL below to your tunnel URL, e.g.
       "https://utmiotsecurityg4.dpdns.org"

    2. On Streamlit Community Cloud, add this to your app's Secrets
       (Settings → Secrets) instead of hardcoding it, so you don't have
       to redeploy every time the URL changes:

           PI_API_URL = "https://utmiotsecurityg4.dpdns.org"

        Then this file reads st.secrets["PI_API_URL"] automatically if
        present, falling back to the hardcoded value below for local testing.

    3. requirements.txt needs one new line:  requests>=2.31.0
"""

import io
import requests
import pandas as pd
import streamlit as st
from datetime import datetime

# ── CONFIG ─────────────────────────────────────────────────────────────────
# Prefer Streamlit Secrets (set in Streamlit Cloud dashboard) over hardcoding.
# Falls back to this default so local testing still works without secrets.
try:
    PI_API_URL = st.secrets["PI_API_URL"]
except Exception:
    PI_API_URL = "https://utmiotsecurityg4.dpdns.org"  

REQUEST_TIMEOUT = 5  # seconds — fail fast rather than freezing the dashboard


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_get(path: str):
    """
    Makes a GET request to the Pi API. Returns the requests.Response on
    success, or None on any failure (timeout, connection error, 404, etc).
    Centralising this means every public function below has the same
    one-line failure handling.
    """
    try:
        resp = requests.get(f"{PI_API_URL}{path}", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.exceptions.RequestException:
        return None


@st.cache_data(ttl=5)
def _fetch_logs_df() -> pd.DataFrame:
    """
    Fetches and parses security_logs.csv from the Pi.
    Cached for 5 seconds so rapid page switches / reruns don't hammer
    the Pi with repeat requests — matches the "every few seconds is fine"
    real-time requirement you chose.
    """
    resp = _safe_get("/logs")
    if resp is None:
        return pd.DataFrame(columns=[
            "timestamp", "visitor_name", "motion", "auth_result",
            "threat_level", "door_status", "confidence", "img_file",
        ])
    try:
        df = pd.read_csv(io.StringIO(resp.text), parse_dates=["timestamp"])
        return df.sort_values("timestamp", ascending=False)
    except Exception:
        # CSV exists but is malformed/empty — fail safe rather than crash
        return pd.DataFrame(columns=[
            "timestamp", "visitor_name", "motion", "auth_result",
            "threat_level", "door_status", "confidence", "img_file",
        ])


@st.cache_data(ttl=5)
def _fetch_state() -> dict:
    """Fetches the latest state.json snapshot from the Pi (door/motion/RAM)."""
    resp = _safe_get("/state")
    if resp is None:
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


def _pi_image_url(filename: str) -> str:
    """Builds the full URL for a single image served by pi_server.py."""
    return f"{PI_API_URL}/images/{filename}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — System / device state  (used by page1_realtime.py)
# ─────────────────────────────────────────────────────────────────────────────

def get_system_state() -> dict:
    """
    Same return shape as the original mock version, so page1_realtime.py
    needs ZERO changes. Values now come from the Pi's /state endpoint
    (refreshed every 5 seconds via the cache above).
    """
    state = _fetch_state()

    last_img = state.get("last_visitor_img")
    # Turn "stranger_004.jpg" into a full URL st.image() can load directly.
    last_img_url = _pi_image_url(last_img) if last_img else None

    return {
        "motion_detected":  state.get("motion_detected", False),
        "camera_status":    state.get("camera_status", "Standby"),
        "last_visitor":      state.get("last_visitor", "—"),
        "auth_result":       state.get("auth_result", "—"),
        "threat_level":      state.get("threat_level", "None"),
        "suspicious_count": state.get("suspicious_count", 0),
        "door_status":       state.get("door_status", "Closed"),
        "door_alert":        state.get("door_alert", False),
        "pir_ok":            state.get("pir_ok", True),
        "camera_ok":         state.get("camera_ok", True),
        "door_sensor_ok":    state.get("door_sensor_ok", True),
        "speaker_ok":        state.get("speaker_ok", True),
        "last_visitor_img": last_img_url,
        "last_event_time":   state.get("last_event_time", "—"),
        "access_count":      state.get("access_count", 0),
    }


def stop_alarm() -> dict:
    """
    Calls the Pi's /alarm/stop endpoint when the dashboard's "Stop alarm"
    button is clicked.
    """
    try:
        resp = requests.post(f"{PI_API_URL}/alarm/stop", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return {"success": True, "message": "Stop command sent to Raspberry Pi."}
    except requests.exceptions.RequestException:
        return {"success": False,
                "message": "Could not reach the Pi — check it's online and the tunnel is up."}


def get_alarm_status() -> dict:
    """
    Optional: lets page1_realtime.py check whether a dismiss is already
    in effect (e.g. after a page refresh).
    """
    resp = _safe_get("/alarm/status")
    if resp is None:
        return {"dismissed": False, "dismissed_at": None}
    try:
        return resp.json()
    except Exception:
        return {"dismissed": False, "dismissed_at": None}


def get_ram_usage() -> dict:
    """
    Pulled from the "ram" key inside state.json.
    """
    state = _fetch_state()
    ram = state.get("ram", {})
    return {
        "os_streamlit_mb":     ram.get("os_streamlit_mb", 0),
        "face_recognition_mb": ram.get("face_recognition_mb", 0),
        "opencv_camera_mb":    ram.get("opencv_camera_mb", 0),
        "mqtt_sensors_mb":     ram.get("mqtt_sensors_mb", 0),
        "total_pi_ram_mb":     ram.get("total_pi_ram_mb", 4096),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Visitor analytics (today's counts)  (used by page2_analytics.py)
# ─────────────────────────────────────────────────────────────────────────────

def get_today_summary() -> dict:
    """Same shape as before. Computed live from the fetched CSV."""
    df = _fetch_logs_df()
    if df.empty:
        return {"total": 0, "authorized": 0, "unknown": 0,
                 "suspicious": 0, "door_normal": 0, "door_unauth": 0}

    today = df[df["timestamp"].dt.date == datetime.today().date()]
    return {
        "total":       len(today),
        "authorized":  int((today["auth_result"] == "Authorized").sum()),
        "unknown":     int((today["auth_result"] == "Denied").sum()),
        "suspicious":  int((today["threat_level"] == "Suspicious").sum()),
        "door_normal": int((today["door_status"] == "Closed").sum()),
        "door_unauth": int((today["door_status"] == "Attempted open").sum()),
    }


def get_activity_timeline() -> list[dict]:
    """Same shape as before — last 10 events, most recent first."""
    df = _fetch_logs_df()
    if df.empty:
        return []

    recent = df.sort_values("timestamp", ascending=False).head(10)
    out = []
    for _, row in recent.iterrows():
        out.append({
            "time":    row["timestamp"].strftime("%I:%M %p"),
            "visitor": row.get("visitor_name", "Unknown"),
            "result":  row.get("auth_result", "Denied"),
            "threat":  row.get("threat_level", "None"),
            "note":    f"Confidence {row.get('confidence', 0):.2f}",
            "img":     row.get("img_file") or None,
        })
    return out


def get_stranger_gallery() -> list[dict]:
    """
    Lists denied/unknown visitors from the CSV and matches each to a real image URL.
    """
    resp = _safe_get("/images-list")
    image_files = resp.json().get("images", []) if resp else []

    df = _fetch_logs_df()
    if df.empty or not image_files:
        return []

    denied = df[df["auth_result"] == "Denied"].copy()
    counts = denied["img_file"].value_counts().to_dict()

    result = []
    for fname in image_files:
        visits = counts.get(fname, 1)
        match = denied[denied["img_file"] == fname]
        time_str = (match.iloc[0]["timestamp"].strftime("%I:%M %p")
                    if not match.empty else "")
        result.append({
            "label":         f"Unknown — {fname}",
            "time":          time_str,
            "visits":        int(visits),
            "img_path":      _pi_image_url(fname),
            "is_suspicious": visits >= 3,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Audit logs  (used by page3_logs.py)
# ─────────────────────────────────────────────────────────────────────────────

def get_full_logs() -> pd.DataFrame:
    """
    Same shape/column names as the original mock version, so page3_logs.py needs ZERO changes.
    """
    df = _fetch_logs_df()
    if df.empty:
        return pd.DataFrame(columns=[
            "Timestamp", "Visitor", "Motion", "Auth result",
            "Threat", "Door", "Confidence",
        ])

    out = pd.DataFrame({
        "Timestamp":   df["timestamp"].dt.strftime("%I:%M:%S %p"),
        "Visitor":     df["visitor_name"],
        "Motion":      df["motion"],
        "Auth result": df["auth_result"],
        "Threat":      df["threat_level"],
        "Door":        df["door_status"],
        "Confidence":  df["confidence"],
    })
    return out
