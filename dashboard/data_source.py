"""
data_source.py — Mock data for dashboard testing

HOW TO SWAP TO REAL DATA:
    Every section marked  # ── REAL DATA SWAP ──  shows exactly what
    variable to replace and where it comes from in your Pi pipeline.
    Search this file for "REAL DATA SWAP" to find all swap points.
"""

import pandas as pd
import random
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — System / device state
# ─────────────────────────────────────────────────────────────────────────────

def get_system_state() -> dict:
    """
    Returns the current live state of the Pi security system.

    # ── REAL DATA SWAP ──
    Replace this entire function body with an MQTT subscriber.
    Your Pi backend publishes a JSON payload to the topic:
        favoriot/<device_id>/latest
    or you can use a local broker:
        mqtt_topic = "security/state"
    
    Example real swap:
        import paho.mqtt.client as mqtt, json
        latest = {}
        def on_message(client, userdata, msg):
            global latest
            latest = json.loads(msg.payload)
        # Then return latest from this function.

    Expected keys from your Pi JSON:
        motion_detected  : bool
        camera_status    : str  ("Active" | "Standby")
        last_visitor     : str  ("John" | "Unknown")
        auth_result      : str  ("Authorized" | "Denied")
        threat_level     : str  ("None" | "Warning" | "Suspicious")
        suspicious_count : int
        door_status      : str  ("Closed" | "Open")
        door_alert       : bool
        pir_ok           : bool
        camera_ok        : bool
        door_sensor_ok   : bool
        speaker_ok       : bool
        last_visitor_img : str  (file path e.g. "images/stranger_003.jpg")
        last_event_time  : str  ("09:14 AM")
        access_count     : int
    """
    return {
        "motion_detected":  True,
        "camera_status":    "Active",
        "last_visitor":     "Unknown",
        "auth_result":      "Denied",
        "threat_level":     "Suspicious",
        "suspicious_count": 1,
        "door_status":      "Closed",
        "door_alert":       False,
        "pir_ok":           True,
        "camera_ok":        True,
        "door_sensor_ok":   True,
        "speaker_ok":       True,
        "last_visitor_img": None,          # replace with real path string
        "last_event_time":  "09:14 AM",
        "access_count":     12,
    }


def get_ram_usage() -> dict:
    """
    Estimated RAM usage breakdown for the Pi 4.

    # ── REAL DATA SWAP ──
    Read actual process memory from /proc on the Pi and publish via MQTT.
    Quick Pi-side snippet:
        import psutil, os
        proc = psutil.Process(os.getpid())
        mem_mb = proc.memory_info().rss / 1024 / 1024
    Or parse /proc/meminfo for system-wide free/used.
    Replace the values below with those live readings.
    """
    return {
        "os_streamlit_mb":      600,   # replace: read from Pi MQTT payload key "ram_os_mb"
        "face_recognition_mb":  350,   # replace: read from Pi MQTT payload key "ram_facerec_mb"
        "opencv_camera_mb":     150,   # replace: read from Pi MQTT payload key "ram_opencv_mb"
        "mqtt_sensors_mb":       40,   # replace: read from Pi MQTT payload key "ram_mqtt_mb"
        "total_pi_ram_mb":     4096,   # Pi 4 — change to 2048 if you have the 2 GB model
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Visitor analytics (today's counts)
# ─────────────────────────────────────────────────────────────────────────────

def get_today_summary() -> dict:
    """
    # ── REAL DATA SWAP ──
    Replace with a pandas groupby on your real security_logs.csv:

        df = pd.read_csv("security_logs.csv", parse_dates=["timestamp"])
        today = df[df["timestamp"].dt.date == datetime.today().date()]
        return {
            "total":       len(today),
            "authorized":  (today["auth_result"] == "Authorized").sum(),
            "unknown":     (today["auth_result"] == "Denied").sum(),
            "suspicious":  (today["threat_level"] == "Suspicious").sum(),
            "door_normal": (today["door_event"] == "Normal").sum(),
            "door_unauth": (today["door_event"] == "Unauthorized").sum(),
        }
    """
    return {
        "total":       14,
        "authorized":   9,
        "unknown":      4,
        "suspicious":   1,
        "door_normal": 11,
        "door_unauth":  2,
    }


def get_activity_timeline() -> list[dict]:
    """
    Returns last N visitor events for the timeline display.

    # ── REAL DATA SWAP ──
    Replace with:
        df = pd.read_csv("security_logs.csv", parse_dates=["timestamp"])
        df = df.sort_values("timestamp", ascending=False).head(10)
        return df[["timestamp","visitor_name","auth_result","threat_level","notes"]].to_dict("records")

    Expected columns in your CSV:
        timestamp, visitor_name, auth_result, threat_level, notes
    """
    return [
        {"time": "09:00 AM", "visitor": "John",        "result": "Authorized",  "threat": "None",      "note": "Face matched. Access granted.",         "img": None},
        {"time": "11:20 AM", "visitor": "Unknown",     "result": "Denied",      "threat": "Warning",   "note": "Access denied. Image saved.",           "img": None},
        {"time": "01:45 PM", "visitor": "Sarah",       "result": "Authorized",  "threat": "None",      "note": "Face matched. Access granted.",         "img": None},
        {"time": "02:30 PM", "visitor": "Unknown",     "result": "Denied",      "threat": "Warning",   "note": "Access denied. Image saved.",           "img": None},
        {"time": "04:10 PM", "visitor": "Unknown #3",  "result": "Denied",      "threat": "Suspicious","note": "3rd appearance. Alert triggered.",      "img": None},
    ]


def get_stranger_gallery() -> list[dict]:
    """
    Returns list of saved stranger images.

    # ── REAL DATA SWAP ──
    Scan the images/ folder on the Pi for stranger images:
        import glob
        files = sorted(glob.glob("images/stranger_*.jpg"))
        # For each file, also read its metadata from security_logs.csv
        # to get the timestamp and visit count.
    
    Expected keys: label, time, visits, img_path, is_suspicious
    img_path should be a valid file path; use st.image(img_path) to display.
    """
    return [
        {"label": "Unknown #1",   "time": "11:20 AM", "visits": 1, "img_path": None, "is_suspicious": False},
        {"label": "Unknown #2",   "time": "02:30 PM", "visits": 1, "img_path": None, "is_suspicious": False},
        {"label": "Suspicious #1","time": "04:10 PM", "visits": 3, "img_path": None, "is_suspicious": True },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Audit logs
# ─────────────────────────────────────────────────────────────────────────────

def get_full_logs() -> pd.DataFrame:
    """
    Returns all security log entries as a DataFrame.

    # ── REAL DATA SWAP ──
    Replace entire function body with:
        df = pd.read_csv("security_logs.csv", parse_dates=["timestamp"])
        df = df.sort_values("timestamp", ascending=False)
        return df

    Your security_logs.csv should have these columns
    (written by your Pi backend after each detection event):
        timestamp     : datetime string  e.g. "2025-06-10 09:00:12"
        visitor_name  : str              "John" | "Unknown" | "Unknown #3"
        motion        : bool/str         True | False
        auth_result   : str              "Authorized" | "Denied"
        threat_level  : str              "None" | "Warning" | "Suspicious"
        door_status   : str              "Closed" | "Open" | "Attempted open"
        confidence    : float            face recognition confidence 0.0–1.0
        img_file      : str              "images/stranger_003.jpg" or ""
    """
    rows = [
        {"Timestamp": "09:00:12 AM", "Visitor": "John",       "Motion": True,  "Auth result": "Authorized", "Threat":     "None",      "Door": "Closed",          "Confidence": 0.97},
        {"Timestamp": "11:20:33 AM", "Visitor": "Unknown",    "Motion": True,  "Auth result": "Denied",     "Threat":     "Warning",   "Door": "Closed",          "Confidence": 0.21},
        {"Timestamp": "01:45:09 PM", "Visitor": "Sarah",      "Motion": True,  "Auth result": "Authorized", "Threat":     "None",      "Door": "Open → Closed",   "Confidence": 0.95},
        {"Timestamp": "02:30:47 PM", "Visitor": "Unknown",    "Motion": True,  "Auth result": "Denied",     "Threat":     "Warning",   "Door": "Closed",          "Confidence": 0.18},
        {"Timestamp": "04:10:22 PM", "Visitor": "Unknown #3", "Motion": True,  "Auth result": "Denied",     "Threat":     "Suspicious","Door": "Attempted open",  "Confidence": 0.14},
    ]
    return pd.DataFrame(rows)
