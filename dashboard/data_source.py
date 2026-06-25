"""
data_source.py — REAL DATA VERSION (Pi over Cloudflare Tunnel)

ARCHITECTURE
    Runs on Streamlit Cloud (UTC server time — see PI_TIMEZONE below for
    why that matters for "today" calculations).
    Fetches data from Raspberry Pi via Cloudflare Tunnel public URL.

    Pi (security_logs.csv, strangers/, state — written in Malaysia local
    time, confirmed via the Pi's system clock)
        → pi_server.py (FastAPI, port 8000) — confirmed live via
          systemctl status pi-api.service; an earlier docstring here
          incorrectly named src/webapp.py (Flask) as the backend, which
          was never actually confirmed running
        → Cloudflare Tunnel
        → THIS FILE fetches over HTTPS
        → page1/2/3 render() functions (unchanged)

SETUP
    Set PI_API_URL below to your tunnel URL.
    Or add to Streamlit Cloud Secrets:
        PI_API_URL = "https://utmiotsecurityg4.dpdns.org"
"""

import io
import os
import glob
import requests
import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

# ── CONFIG ────────────────────────────────────────────────────────────────────
try:
    PI_API_URL = st.secrets["PI_API_URL"]
except Exception:
    PI_API_URL = "https://utmiotsecurityg4.dpdns.org"   # ← your tunnel URL

REQUEST_TIMEOUT = 5   # seconds — fail fast, don't freeze the dashboard

# Confirmed: the Pi's system clock is set to Malaysia time, and every CSV
# timestamp is written via the Pi's local time.strftime() — NOT UTC.
# Streamlit Cloud's servers run in UTC. Without this, "today" in
# get_today_summary() would be wrong for several hours every day (e.g. a
# 1am Malaysia-time event is still "yesterday" in UTC until ~5pm UTC).
PI_TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")

# ── Threat level mapping ──────────────────────────────────────────────────────
# Pi writes: Pending / Low / Medium / High
# Dashboard shows: None / Warning / Suspicious
THREAT_MAP = {
    # CONFIRMED against face_recognition_engine.py's actual _risk_label()
    # and _build_result() — these are the real, exact strings produced,
    # not a guess. Note "HIGH" is genuinely all-caps in the source while
    # "Low"/"Medium" are title-case — an inconsistency in that file
    # itself, not something to "fix" here, just match exactly as-is.
    "":        "None",
    "Pending": "Warning",     # still voting on identity, not yet confirmed
    "Low":     "Warning",     # confirmed unknown, low repeat count
    "Medium":  "Suspicious",  # confirmed unknown, medium repeat count
    "HIGH":    "Suspicious",  # confirmed unknown, high repeat count (all-caps in source)
    "Safe":    "None",        # known/authorized visitor — no threat
}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_get(path: str):
    """
    GET request to Pi API.
    Returns requests.Response on success, None on any failure.

    TEMPORARY DEBUG INSTRUMENTATION:
    print() statements added here on purpose — Streamlit Cloud's log
    viewer captures stdout but does NOT automatically show Python
    `logging` module output or silently-caught exceptions. Without
    these prints, a failure here is completely invisible in the deploy
    logs, which is exactly the blind spot that made the last debugging
    session impossible. Remove these once the connection issue is
    confirmed fixed — they're noisy for day-to-day use.
    """
    url = f"{PI_API_URL}{path}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        print(f"[PI-DEBUG] GET {url} -> {resp.status_code} OK")
        return resp
    except requests.exceptions.Timeout:
        print(f"[PI-DEBUG] GET {url} -> TIMEOUT after {REQUEST_TIMEOUT}s")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"[PI-DEBUG] GET {url} -> CONNECTION ERROR: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"[PI-DEBUG] GET {url} -> HTTP ERROR: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"[PI-DEBUG] GET {url} -> OTHER REQUEST ERROR: {type(e).__name__}: {e}")
        return None


@st.cache_data(ttl=5)
def is_pi_reachable() -> bool:
    """
    Single source of truth for "can we actually talk to the Pi right now."

    ISSUE 1 FIX — Connection Drop Blindness:
    Previously, get_system_state() inferred hardware health purely from
    field values inside the /state response (pir_ok, camera_ok, etc), each
    defaulting to True. When the tunnel is down, _fetch_state() returns {},
    and `state.get("pir_ok", True)` returns True — not because the Pi said
    so, but because the key was simply absent. That made "Pi unreachable"
    indistinguishable from "Pi says everything is fine."

    This function checks reachability directly and explicitly, independent
    of what any individual field says, so callers can tell the two apart.
    Cached 5s alongside the other fetches so a dead tunnel doesn't add a
    fresh multi-second timeout delay on every single rerun.

    NOTE: tries /health first (lightweight, no payload to parse), but
    falls back to /state if /health isn't implemented on your Flask
    backend (src/webapp.py) — confirm with whoever owns that file which
    routes actually exist; this fallback means the check works either way.
    """
    health_resp = _safe_get("/health")
    if health_resp is not None:
        print("[PI-DEBUG] is_pi_reachable() -> True (via /health)")
        return True
    state_resp = _safe_get("/state")
    result = state_resp is not None
    print(f"[PI-DEBUG] is_pi_reachable() -> {result} (via /state fallback)")
    return result


@st.cache_data(ttl=5)
def _fetch_logs_df() -> pd.DataFrame:
    """
    Fetches security_logs.csv from Pi via /logs endpoint.
    Cached 5 seconds — avoids hammering Pi on every rerun.

    CSV columns from your Pi (main.py):
        timestamp, event_type, visitor_name, auth_result,
        threat_level, door_status, confidence, img_file
    """
    empty = pd.DataFrame(columns=[
        "timestamp", "event_type", "visitor_name", "auth_result",
        "threat_level", "door_status", "confidence", "img_file",
    ])

    resp = _safe_get("/logs")
    if resp is None:
        return empty

    try:
        df = pd.read_csv(
            io.StringIO(resp.text),
            parse_dates=["timestamp"],
        )
        # Normalise column names — strip whitespace just in case
        df.columns = df.columns.str.strip()
        # Fill NaN strings
        df = df.fillna("")

        # CONFIRMED MISMATCH FIX: main.py writes result["action"] directly
        # into auth_result, which is "AUTHORIZED" / "DENIED" (all-caps) —
        # but every comparison in page1/2/3_*.py and the functions below
        # checks for "Authorized" / "Denied" (title-case). Without this
        # normalisation, those comparisons silently always evaluate False:
        # auth-rate metrics show 0%, badges always render red, the Page 3
        # filter dropdown returns zero rows for either choice. Fixed once
        # here, at the single chokepoint every other function reads
        # through, rather than patching each comparison site individually.
        if "auth_result" in df.columns:
            df["auth_result"] = df["auth_result"].replace({
                "AUTHORIZED":        "Authorized",
                "DENIED":            "Denied",
                # New as of the alert-popup tagging feature — these are
                # NOT raw detection outcomes, they're follow-up rows
                # appended when an owner reviews a stranger from the
                # popup. Kept as their own distinct values (not folded
                # into "Denied") since "reviewed, pending authorization"
                # is meaningfully different information for the audit
                # log than the original denial event itself.
                "authorize_pending": "Pending Authorization",
                "unknown_reviewed":  "Reviewed — Unknown",
            })

        return df.sort_values("timestamp", ascending=False)
    except Exception:
        return empty


@st.cache_data(ttl=5)
def _fetch_state() -> dict:
    """
    Fetches /state JSON from Pi webapp.
    Returns empty dict if Pi unreachable.

    Reachability itself is NOT tracked here — see is_pi_reachable() above,
    which is the single source of truth for that, used independently by
    get_system_state() below. Keeping that logic in one place avoids two
    different functions disagreeing about whether the Pi is up.
    """
    resp = _safe_get("/state")
    if resp is None:
        return {}
    try:
        return resp.json()
    except Exception:
        return {}


def _pi_image_url(filename: str) -> str:
    """
    Builds full image URL using Pi's actual route: /images/{filename}
    (confirmed against pi_server.py — NOT /stranger/, which doesn't exist
    as a route at all; that was a mismatch that would have 404'd every
    single image request even with the Pi fully online).
    Handles both bare filenames and full paths.
    """
    if not filename:
        return None
    basename = os.path.basename(str(filename))
    if not basename:
        return None
    return f"{PI_API_URL}/images/{basename}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — System / device state  →  page1_realtime.py
# ─────────────────────────────────────────────────────────────────────────────

def get_system_state() -> dict:
    """
    Returns live system state from Pi /state endpoint.
    Same return shape as original mock — page1_realtime.py needs no changes
    EXCEPT it must now also check the "pi_reachable" key before trusting
    any *_ok / status field (see ISSUE 1 FIX note on is_pi_reachable above).

    When pi_reachable is False: sensor *_ok fields are forced to False
    (not left at their optimistic True default — "no answer" must never
    render as "Working"), and display fields fall back to neutral
    placeholders rather than data that looks live but isn't.
    """
    state        = _fetch_state()
    pi_reachable = is_pi_reachable()

    # Build image URL from filename (Pi sends bare filename or full path)
    raw_img      = state.get("last_visitor_img") or ""
    last_img_url = _pi_image_url(raw_img) if raw_img else None

    # Same casing fix as _fetch_logs_df() — main.py writes "AUTHORIZED" /
    # "DENIED" into the CSV, pi_server.py's /state endpoint passes that
    # raw value through unchanged, so this is a SEPARATE occurrence of
    # the same bug, not covered by the CSV-side fix since /state is a
    # different code path entirely.
    AUTH_RESULT_MAP = {"AUTHORIZED": "Authorized", "DENIED": "Denied"}
    raw_auth_result = state.get("auth_result", "—")
    dash_auth_result = AUTH_RESULT_MAP.get(raw_auth_result, raw_auth_result)

    # Map Pi threat level → dashboard level
    raw_threat  = state.get("threat_level", "")
    dash_threat = THREAT_MAP.get(raw_threat, "None")

    return {
        "pi_reachable":     pi_reachable,
        "motion_detected":  bool(state.get("motion_detected", False)) if pi_reachable else False,
        "camera_status":    state.get("camera_status", "Standby") if pi_reachable else "Unknown",
        "last_visitor":     state.get("last_visitor", "—") if pi_reachable else "—",
        "auth_result":      dash_auth_result if pi_reachable else "—",
        "threat_level":     dash_threat if pi_reachable else "None",
        "suspicious_count": int(state.get("suspicious_count", 0)) if pi_reachable else 0,
        "door_status":      state.get("door_status", "Closed") if pi_reachable else "Unknown",
        "door_alert":       bool(state.get("door_alert", False)) if pi_reachable else False,
        # Sensor health — the actual issue-1 fix: False, not True, when offline.
        "pir_ok":           bool(state.get("pir_ok", True)) if pi_reachable else False,
        "camera_ok":        bool(state.get("camera_ok", True)) if pi_reachable else False,
        "door_sensor_ok":   bool(state.get("door_sensor_ok", True)) if pi_reachable else False,
        "speaker_ok":       bool(state.get("speaker_ok", True)) if pi_reachable else False,
        "last_visitor_img": last_img_url if pi_reachable else None,
        "last_event_time":  state.get("last_event_time", "—") if pi_reachable else "—",
        "access_count":     int(state.get("access_count", 0)) if pi_reachable else 0,
    }


def get_ram_usage() -> dict:
    """
    RAM breakdown pulled from /state → ram key.

    When the Pi is unreachable, returns all zeros rather than the old
    estimated placeholder values (600/350/150/40 MB) — those numbers
    looked exactly like real telemetry and were actually more misleading
    than the sensor True/False issue, since a person glancing at the RAM
    bars would have no way to tell "this is a guess" from "this is live."
    page1_realtime.py is responsible for showing the offline banner
    separately; this function's job is just to not lie about RAM.
    """
    if not is_pi_reachable():
        return {
            "os_streamlit_mb":     0,
            "face_recognition_mb": 0,
            "opencv_camera_mb":    0,
            "mqtt_sensors_mb":     0,
            "total_pi_ram_mb":     4096,   # kept non-zero only to avoid a divide-by-zero in the % bar
        }

    state = _fetch_state()
    ram   = state.get("ram", {})
    return {
        "os_streamlit_mb":     int(ram.get("os_streamlit_mb",     0)),
        "face_recognition_mb": int(ram.get("face_recognition_mb", 0)),
        "opencv_camera_mb":    int(ram.get("opencv_camera_mb",    0)),
        "mqtt_sensors_mb":     int(ram.get("mqtt_sensors_mb",      0)),
        "total_pi_ram_mb":     int(ram.get("total_pi_ram_mb",    4096)),
    }


def stop_alarm() -> dict:
    """
    Called when dashboard Stop Alarm button is clicked.
    POSTs to Pi /alarm/stop endpoint over HTTP, through the Cloudflare
    Tunnel — this IS the real, final implementation, not a placeholder.
    MQTT was never built for this project and there's no plan to add it;
    an earlier version of this docstring suggested swapping to MQTT later,
    which was leftover from the original mock-dashboard design and no
    longer applies.
    """
    try:
        resp = requests.post(
            f"{PI_API_URL}/alarm/stop",
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return {"success": True, "message": "Stop command sent to Pi."}
    except requests.exceptions.RequestException:

        return {
            "success": False,
            "message": "Could not reach Pi — check tunnel and webapp are running.",
        }


def get_alarm_status() -> dict:
    """
    Checks whether the alarm is currently dismissed.
    GETs Pi /alarm/status endpoint.
    Falls back to "not dismissed" if Pi is unreachable.
    """
    resp = _safe_get("/alarm/status")
    if resp is None:
        return {"dismissed": False, "dismissed_at": None}
    try:
        return resp.json()
    except Exception:
        return {"dismissed": False, "dismissed_at": None}


def tag_stranger(filename: str, label: str) -> dict:
    """
    Called from the alert popup's three action buttons (alert_popup.py).
    label must be "authorize_pending" or "unknown_reviewed" — see
    pi_server.py's /stranger/tag docstring for exactly what each does.
    """
    try:
        resp = requests.post(
            f"{PI_API_URL}/stranger/tag",
            params={"filename": filename, "label": label},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        # The Pi WAS reached — it just returned an error status (e.g. 404
        # if the photo was already moved/deleted). Surfacing FastAPI's
        # actual detail here, since "Could not reach Pi" would be
        # actively misleading for this case — the connection is fine,
        # something else is wrong (most likely: stale popup referencing
        # a photo that's already been handled or removed).
        try:
            detail = resp.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        return {"success": False, "message": f"Pi rejected the request: {detail}"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "message": f"Could not reach Pi: {e}"}


def get_active_alert() -> dict:
    """
    Single source of truth for "should the popup show right now," used
    by alert_popup.py regardless of which page is currently active.

    Returns one of three shapes:
      {"type": None}                                   — nothing active
      {"type": "stranger", "filename": ..., "img_url": ...}
      {"type": "door"}

    Priority: a never-reviewed stranger takes priority over a stuck-open
    door, since a specific unidentified person is generally the more
    urgent thing for an owner to look at first. If neither condition is
    true, or the Pi is unreachable, returns {"type": None} — the popup
    must never show stale/fake alerts just because we can't reach the Pi.

    BUG FIX: previously checked /state's last_visitor_img, which only
    ever reflects the SINGLE MOST RECENT visitor row. An authorized
    visitor walking in right after an unreviewed stranger would silently
    make that stranger's photo disappear from /state, even though nobody
    had reviewed them — the popup would just stop showing them with no
    indication anything was missed. Now uses /stranger/pending, which
    scans ALL recent Denied rows for the oldest unreviewed one, so a
    stranger can't be skipped just because someone else walked up after.
    """
    if not is_pi_reachable():
        return {"type": None}

    resp = _safe_get("/stranger/pending")
    if resp is not None:
        try:
            pending_filename = resp.json().get("filename")
            if pending_filename:
                return {
                    "type":     "stranger",
                    "filename": pending_filename,
                    "img_url":  _pi_image_url(pending_filename),
                }
        except Exception:
            pass

    state = _fetch_state()

    if state.get("door_alert"):
        return {"type": "door"}

    return {"type": None}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Visitor analytics  →  page2_analytics.py
# ─────────────────────────────────────────────────────────────────────────────

def get_today_summary() -> dict:
    """
    Counts today's visitor and door events from the CSV.
    Filters by event_type: 'visitor' for auth stats, 'door' for door stats.
    """
    empty = {
        "total": 0, "authorized": 0, "unknown": 0,
        "suspicious": 0, "door_normal": 0, "door_unauth": 0,
    }

    df = _fetch_logs_df()
    if df.empty:
        return empty

    # Filter to today — IN MALAYSIA TIME, since that's what every CSV
    # timestamp actually represents (the Pi's local clock), not UTC.
    # datetime.now(PI_TIMEZONE).date() gives "today" as the Pi would
    # understand it; comparing that against the naive (timezone-less)
    # CSV timestamps is correct here specifically because both sides
    # are already in the same local time, just one has tz info attached
    # and one doesn't — attaching tz to the CSV side would be wrong since
    # pandas would otherwise assume those naive timestamps are UTC.
    try:
        today_in_malaysia = datetime.now(PI_TIMEZONE).date()
        today_mask = df["timestamp"].dt.date == today_in_malaysia
        today      = df[today_mask]
    except Exception:
        return empty

    if today.empty:
        return empty

    visitors = today[today["event_type"] == "visitor"]
    doors    = today[today["event_type"] == "door"]

    # Map threat levels for suspicious count
    # Confirmed real value is "HIGH" (all-caps) — see THREAT_MAP comment above.
    suspicious_threats = {"Medium", "HIGH"}

    return {
        "total":       len(visitors),
        "authorized":  int((visitors["auth_result"] == "Authorized").sum()),
        "unknown":     int((visitors["auth_result"] == "Denied").sum()),
        "suspicious":  int(visitors["threat_level"].isin(suspicious_threats).sum()),
        "door_normal": int((doors["door_status"] == "Closed").sum()),
        "door_unauth": int((doors["door_status"] == "Open").sum()),
    }


def get_activity_timeline() -> list:
    """
    Returns last 10 visitor events (event_type='visitor') for the timeline.
    Excludes pure door events — those go to the door chart only.
    """
    df = _fetch_logs_df()
    if df.empty:
        return []

    visitors = df[df["event_type"] == "visitor"].head(10)
    if visitors.empty:
        return []

    result = []
    for _, row in visitors.iterrows():
        raw_threat  = str(row.get("threat_level", ""))
        dash_threat = THREAT_MAP.get(raw_threat, "None")

        # Build image URL if img_file is present
        img_file = str(row.get("img_file", "")).strip()
        img_url  = _pi_image_url(img_file) if img_file else None

        # Format timestamp
        try:
            time_str = row["timestamp"].strftime("%I:%M %p")
        except Exception:
            time_str = str(row.get("timestamp", ""))

        # Confidence display
        try:
            conf = float(row.get("confidence", 0))
            note = f"Confidence: {conf:.2f}"
        except Exception:
            note = ""

        result.append({
            "time":    time_str,
            "visitor": str(row.get("visitor_name", "Unknown")) or "Unknown",
            "result":  str(row.get("auth_result", "Denied")),
            "threat":  dash_threat,
            "note":    note,
            "img":     img_url,
        })

    return result


def get_stranger_gallery() -> list:
    """
    Builds gallery from /images-list endpoint (stranger filenames)
    cross-referenced with CSV denied rows for visit counts and timestamps.

    Threat level is parsed from filename suffix:
        stranger_20260619_150746_Pending.jpg → Pending → Warning
        stranger_20260622_102739_Low.jpg     → Low     → Warning
        stranger_20260619_163418_Medium.jpg  → Medium  → Suspicious
    """
    resp = _safe_get("/images-list")
    if resp is None:
        return []

    try:
        image_files = resp.json().get("images", [])
    except Exception:
        return []

    if not image_files:
        return []

    # /images-list returns filenames sorted alphabetically, which equals
    # chronological order for this naming pattern (stranger_YYYYMMDD_HHMMSS_*)
    # since the date/time portion is zero-padded. Reversed here so the
    # gallery shows NEWEST first — page2_analytics.py then slices to the
    # first 3 for "3 latest stranger images in a row".
    image_files = sorted(image_files, reverse=True)

    df      = _fetch_logs_df()
    denied  = df[df["auth_result"] == "Denied"] if not df.empty else pd.DataFrame()
    counts  = denied["img_file"].apply(
        lambda x: os.path.basename(str(x))
    ).value_counts().to_dict() if not denied.empty else {}

    result = []
    for fname in image_files:
        # Parse threat from filename: stranger_DATE_TIME_Threat.jpg
        try:
            threat_raw = fname.replace(".jpg", "").split("_")[-1]
        except Exception:
            threat_raw = ""

        dash_threat  = THREAT_MAP.get(threat_raw, "None")
        visits       = int(counts.get(fname, 1))

        # Get timestamp from matching CSV row
        time_str = ""
        if not denied.empty:
            match = denied[
                denied["img_file"].apply(
                    lambda x: os.path.basename(str(x))
                ) == fname
            ]
            if not match.empty:
                try:
                    time_str = match.iloc[0]["timestamp"].strftime("%I:%M %p")
                except Exception:
                    pass

        result.append({
            "label":         f"Unknown — {fname}",
            "time":          time_str,
            "visits":        visits,
            "img_path":      _pi_image_url(fname),
            "is_suspicious": dash_threat == "Suspicious",
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Audit logs  →  page3_logs.py
# ─────────────────────────────────────────────────────────────────────────────

def refresh_logs() -> None:
    """
    ISSUE 3 FIX — Page 3 stagnation.

    Clears only the _fetch_logs_df cache entry, not the entire
    st.cache_data store. Clearing everything would also wipe
    is_pi_reachable()'s and _fetch_state()'s 5s cache, causing extra
    unrelated Pi requests on the next rerun just from clicking "refresh
    logs" — this targets exactly the one cache that's actually stale.

    page3_logs.py calls this from a "🔄 Refresh Logs" button, then
    st.rerun() to redraw with the freshly-fetched data immediately,
    rather than waiting for the 5s TTL to lapse naturally.
    """
    _fetch_logs_df.clear()


def get_full_logs() -> pd.DataFrame:
    """
    Returns all log rows as a DataFrame with display-friendly column names.
    page3_logs.py expects these exact column names:
        Timestamp, Visitor, Motion, Auth result, Threat, Door, Confidence

    Includes both event_type='visitor' and event_type='door' rows
    so the full audit trail is visible.
    """
    empty = pd.DataFrame(columns=[
        "Timestamp", "Visitor", "Motion",
        "Auth result", "Threat", "Door", "Confidence",
    ])

    df = _fetch_logs_df()
    if df.empty:
        return empty

    try:
        # Format timestamp for display
        try:
            ts = df["timestamp"].dt.strftime("%Y-%m-%d %I:%M:%S %p")
        except Exception:
            ts = df["timestamp"].astype(str)

        # Map threat levels
        threat_display = df["threat_level"].apply(
            lambda x: THREAT_MAP.get(str(x).strip(), "None")
        )

        # Motion column — door open = motion implied
        motion_display = df["event_type"].apply(
            lambda x: True if str(x) in ("visitor", "door") else False
        )

        out = pd.DataFrame({
            "Timestamp":   ts,
            "Visitor":     df["visitor_name"].replace("", "—"),
            "Motion":      motion_display,
            "Auth result": df["auth_result"].replace("", "—"),
            "Threat":      threat_display,
            "Door":        df["door_status"].replace("", "—"),
            "Confidence":  pd.to_numeric(df["confidence"], errors="coerce").round(2),
        })
        return out

    except Exception:
        return empty
