"""
pages_src/page1_realtime.py
Page 1 — Real-time monitoring & device status

SVG FIX: Streamlit strips <svg> tags from st.markdown() even with
unsafe_allow_html=True. Door illustration uses pure CSS divs instead.
"""

import streamlit as st
from data_source import get_system_state, get_ram_usage, get_alarm_status, is_pi_reachable


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(text: str, style: str) -> str:
    return f'<span class="badge badge-{style}">{text}</span>'

def _dot(style: str) -> str:
    colors = {"green": "#10b981", "red": "#ef4444", "amber": "#f59e0b", "gray": "#9ca3af"}
    c = colors.get(style, "#9ca3af")
    return (f'<span style="display:inline-block;width:8px;height:8px;'
            f'border-radius:50%;background:{c};margin-right:6px"></span>')

def _result_badge(result: str) -> str:
    if result == "Authorized":
        return _badge("✓ Authorized", "green")
    return _badge("✗ Denied", "red")

def _threat_badge(level: str) -> str:
    m = {"None": "gray", "Warning": "amber", "Suspicious": "red"}
    return _badge(level, m.get(level, "gray"))

def _sensor_badge(ok: bool, offline: bool = False) -> str:
    """
    offline=True overrides ok entirely — when the Pi itself is unreachable,
    we genuinely don't know if a sensor is "Working" or "Fault", so showing
    either would be a guess. "Offline" (gray) is the honest answer.
    """
    if offline:
        return _badge("Offline", "gray")
    return _badge("Working", "green") if ok else _badge("⚠ Fault", "red")

def _door_status_badge(door_sensor_ok: bool, is_open: bool) -> str:
    """
    Requirement 1 — strictly hardware-driven, three distinct states:
      sensor offline/unreachable -> "Offline"  (gray, regardless of door_status)
      sensor online + door open  -> "OPEN"     (amber/warning)
      sensor online + door closed -> "CLOSED"  (green/success)
    Offline takes priority: an unreliable sensor reading OPEN/CLOSED is not
    trustworthy, so we say so rather than show a possibly-false state.
    """
    if not door_sensor_ok:
        return _badge("⚠ Offline", "gray")
    return _badge("OPEN", "amber") if is_open else _badge("✓ CLOSED", "green")


# ── Door illustration ─────────────────────────────────────────────────────────
# Uses st.components.v1.html() which renders full HTML without Streamlit's
# sanitizer stripping nested tags. Do NOT use st.markdown() for nested divs.

def _render_door(is_open: bool, offline: bool = False):
    import streamlit.components.v1 as components

    if offline:
        # Sensor unreachable — gray/dashed door, "?" rather than claiming a
        # state we can't actually verify from hardware right now.
        panel_style = ("position:absolute;top:4px;left:4px;right:4px;bottom:0;"
                       "background:#f3f4f6;border-radius:2px 2px 0 0;"
                       "border:1px dashed #9ca3af;")
        knob_style  = ("position:absolute;right:7px;top:50%;width:6px;height:6px;"
                       "background:#d1d5db;border-radius:50%;transform:translateY(-50%);")
        label_style = "color:#6b7280;font-size:12px;font-weight:700;margin-top:6px;"
        label_text  = "&#9888; OFFLINE"
    elif is_open:
        panel_style = ("position:absolute;top:4px;left:4px;bottom:0;width:14px;"
                       "background:#e5e7eb;border-radius:2px 0 0 0;"
                       "border:1px solid #d1d5db;"
                       "transform:perspective(60px) rotateY(-70deg);"
                       "transform-origin:left center;")
        knob_style  = ("position:absolute;right:3px;top:50%;width:5px;height:5px;"
                       "background:#9ca3af;border-radius:50%;transform:translateY(-50%);")
        label_style = "color:#ef4444;font-size:12px;font-weight:700;margin-top:6px;"
        label_text  = "&#9888; OPEN"
    else:
        panel_style = ("position:absolute;top:4px;left:4px;right:4px;bottom:0;"
                       "background:#e5e7eb;border-radius:2px 2px 0 0;"
                       "border:1px solid #d1d5db;")
        knob_style  = ("position:absolute;right:7px;top:50%;width:6px;height:6px;"
                       "background:#9ca3af;border-radius:50%;transform:translateY(-50%);")
        label_style = "color:#10b981;font-size:12px;font-weight:700;margin-top:6px;"
        label_text  = "&#10003; CLOSED"

    html = (
        "<div style='display:flex;flex-direction:column;align-items:center;"
        "margin:6px 0;font-family:sans-serif;'>"
        "<div style='width:64px;height:86px;border:3px solid #6b7280;"
        "border-bottom:none;border-radius:4px 4px 0 0;position:relative;"
        "background:transparent;'>"
        f"<div style='{panel_style}'>"
        f"<div style='{knob_style}'></div>"
        "</div>"
        "</div>"
        "<div style='width:84px;height:3px;background:#6b7280;border-radius:2px;'></div>"
        f"<div style='{label_style}'>{label_text}</div>"
        "</div>"
    )
    components.html(html, height=140)


# ── RAM progress bar ──────────────────────────────────────────────────────────

def _ram_bar(label: str, used_mb: int, total_mb: int, color: str = "#3b82f6"):
    pct = min(used_mb / total_mb * 100, 100)
    bar_color = "#ef4444" if pct > 80 else color
    st.markdown(f"""
    <div style="margin-bottom:7px">
      <div style="display:flex;justify-content:space-between;
                  font-size:0.74rem;color:#6b7280;margin-bottom:2px">
        <span>{label}</span><span>{used_mb} MB</span>
      </div>
      <div style="background:#f3f4f6;border-radius:4px;height:7px;overflow:hidden">
        <div style="width:{pct:.0f}%;height:100%;background:{bar_color};
                    border-radius:4px;"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    # ── REAL DATA SWAP ──────────────────────────────────────────────────────
    # For live auto-refresh every 5 seconds, add these two lines at the top:
    #   from streamlit_autorefresh import st_autorefresh
    #   st_autorefresh(interval=5000, key="rt_refresh")
    # Then install: pip install streamlit-autorefresh
    # ────────────────────────────────────────────────────────────────────────
    state = get_system_state()
    ram   = get_ram_usage()

    # ── Pi connection status (Issue 1 fix) ────────────────────────────────────
    # state["pi_reachable"] comes from data_source.is_pi_reachable(), checked
    # independently of any individual sensor field — so this is true "can we
    # reach the Pi at all" status, not inferred from possibly-stale defaults.
    if not state["pi_reachable"]:
        col_msg, col_retry = st.columns([5, 1])
        with col_msg:
            st.error(
                "🔌 Connection to Raspberry Pi lost. Sensor readings below are "
                "unknown, not necessarily faulty. Check the tunnel or retry.",
                icon="🚨",
            )
        with col_retry:
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
            if st.button("🔄 Retry", key="pi_retry", use_container_width=True):
                is_pi_reachable.clear()  # drop the cached "unreachable" result
                st.rerun()

    # ── Alarm dismiss tracking ────────────────────────────────────────────────
    # session_state gives an immediate UI response (banner hides the moment
    # you click). get_alarm_status() also checks the Pi directly, so the
    # dismissal survives a page refresh too — not just this browser tab.
    if "alarm_dismissed_locally" not in st.session_state:
        st.session_state["alarm_dismissed_locally"] = False

    pi_alarm_status = get_alarm_status()
    is_dismissed = st.session_state["alarm_dismissed_locally"] or pi_alarm_status.get("dismissed", False)

    # A NEW alert (different from the one last dismissed) should show again —
    # otherwise a real second intruder would get silently hidden forever.
    if "last_seen_threat" not in st.session_state:
        st.session_state["last_seen_threat"] = None
    if state["threat_level"] in ("Suspicious", "Warning") and state["threat_level"] != st.session_state["last_seen_threat"]:
        is_dismissed = False
        st.session_state["alarm_dismissed_locally"] = False
    st.session_state["last_seen_threat"] = state["threat_level"]

    # ── Alert banner ──────────────────────────────────────────────────────────
    if not is_dismissed and state["threat_level"] == "Suspicious":
        st.markdown(
            '<div class="alert-danger">🚨 Security alert — repeated unknown visitor detected</div>',
            unsafe_allow_html=True)
    elif not is_dismissed and state["threat_level"] == "Warning":
        st.markdown(
            '<div class="alert-warning">⚠ Unknown visitor detected — monitoring</div>',
            unsafe_allow_html=True)


    # ── Row 1: Smart event panel + Door status ────────────────────────────────
    col_event, col_door = st.columns([3, 2], gap="medium")

    with col_event:
        st.markdown("##### Smart event panel")

        rows = [
            ("System status",    _dot("green") + "Monitoring" if state["pi_reachable"]
                                 else _dot("red") + "Disconnected"),
            ("Camera",           _dot("green" if state["camera_status"] == "Active" else "gray")
                                 + state["camera_status"]),
            ("Motion",           _dot("amber" if state["motion_detected"] else "gray")
                                 + ("Detected" if state["motion_detected"] else "No motion")),
            ("Last visitor",     state["last_visitor"]),
            ("Auth result",      _result_badge(state["auth_result"])),
            ("Threat level",     _threat_badge(state["threat_level"])),
            ("Suspicious count", str(state["suspicious_count"]) + " visitor(s) flagged"),
        ]

        for key, val in rows:
            c1, c2 = st.columns([2, 3])
            c1.markdown(f'<span style="font-size:0.82rem;color:#6b7280">{key}</span>',
                        unsafe_allow_html=True)
            c2.markdown(f'<span style="font-size:0.82rem;font-weight:500">{val}</span>',
                        unsafe_allow_html=True)
            st.divider()

    with col_door:
        st.markdown("##### Door status")

        # Requirement 1 — strictly read-only, hardware-driven. No simulation
        # toggles, no session_state mock. door_sensor_ok gates everything:
        # if the sensor itself is unreachable, we show "Offline" rather than
        # trust a door_status value that might be stale or wrong.
        door_sensor_ok = state["door_sensor_ok"]
        door_is_open   = (state["door_status"] == "Open")

        _render_door(door_is_open, offline=not door_sensor_ok)

        # Door detail rows
        c1, c2 = st.columns(2)
        c1.markdown('<span class="muted">Magnetic sensor</span>', unsafe_allow_html=True)
        c2.markdown(_door_status_badge(door_sensor_ok, door_is_open), unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        c1.markdown('<span class="muted">Last event</span>', unsafe_allow_html=True)
        c2.markdown(f'<span class="muted">{state["last_event_time"]}</span>',
                    unsafe_allow_html=True)

        st.markdown("")

        if not door_sensor_ok:
            st.warning("⚠ Door sensor unreachable — status unknown until it reconnects", icon="📡")
        elif door_is_open:
            st.warning("⚠ Door is open", icon="🚪")

    # ── Row 2: Latest visitor capture + Sensor health & RAM ──────────────────

    st.markdown("")
    col_img, col_health = st.columns([2, 3], gap="medium")

    with col_img:
        st.markdown("##### Latest visitor capture")

        # Shows the latest visitor capture regardless of Authorized/Denied —
        # state["last_visitor_img"] is already a full URL (built by
        # _pi_image_url() in data_source.py), not a local file path, so no
        # os.path.exists() check applies here — that was leftover from the
        # old Samba-share era. st.image() can still fail at render time if
        # the URL 404s (e.g. file genuinely missing on the Pi), so that's
        # caught explicitly rather than crashing the page.
        if state["last_visitor_img"]:
            try:
                st.image(state["last_visitor_img"], use_container_width=True)
            except Exception:
                st.markdown("""
                <div class="img-placeholder">
                  ⚠️<br>
                  <span style="font-size:0.74rem;margin-top:4px;display:block">
                    Image could not be loaded
                  </span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="img-placeholder">
              👤<br>
              <span style="font-size:0.74rem;margin-top:4px;display:block">
                No visitor image available yet
              </span>
            </div>
            """, unsafe_allow_html=True)

        result_style = "green" if state["auth_result"] == "Authorized" else "red"
        st.markdown(
            f'{_badge(state["auth_result"], result_style)}'
            f'&nbsp;&nbsp;<span class="muted">Image stored locally on Pi</span>',
            unsafe_allow_html=True)

    with col_health:
        st.markdown("##### Sensor health")

        sensors = [
            ("📡  PIR motion sensor", state["pir_ok"]),
            ("📷  Camera",            state["camera_ok"]),
            ("🚪  Door sensor",        state["door_sensor_ok"]),
            ("🔊  Speaker",            state["speaker_ok"]),
        ]
        for name, ok in sensors:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f'<span style="font-size:0.82rem">{name}</span>',
                        unsafe_allow_html=True)
            c2.markdown(_sensor_badge(ok, offline=not state["pi_reachable"]),
                        unsafe_allow_html=True)

        st.markdown("")
        st.markdown("##### Pi RAM usage")

        total = ram["total_pi_ram_mb"]
        _ram_bar("OS + Streamlit",   ram["os_streamlit_mb"],     total)
        _ram_bar("Face recognition", ram["face_recognition_mb"], total)
        _ram_bar("OpenCV / camera",  ram["opencv_camera_mb"],    total)
        # Originally labeled "MQTT + sensors" — leftover from the mock
        # dashboard era; MQTT was never implemented (HTTP/Cloudflare
        # Tunnel is used instead throughout). Relabeled honestly rather
        # than guessing a replacement category — this slot is wired but
        # genuinely unmeasured until pi_server.py's /state endpoint
        # actually reports a real number here (currently hardcoded 0).
        _ram_bar("Other / unmeasured", ram["mqtt_sensors_mb"],   total)

        total_used = sum([
            ram["os_streamlit_mb"],
            ram["face_recognition_mb"],
            ram["opencv_camera_mb"],
            ram["mqtt_sensors_mb"],
        ])
        pct = total_used / total * 100
        color = "#ef4444" if pct > 80 else "#10b981"
        st.markdown(
            f'<p class="muted" style="margin-top:4px">'
            f'Total used: <strong style="color:{color}">{total_used} MB '
            f'({pct:.0f}%)</strong> of {total} MB</p>',
            unsafe_allow_html=True)

        if pct > 80:
            st.error("⚠ RAM above 80% — optimise the face recognition model.")
        elif pct <= 50:
            st.success("✓ RAM healthy — within ≤1 GB Streamlit target")

    # NOTE: The Stop Alarm button that used to live here was removed —
    # that action now lives in the global alert popup (alert_popup.py),
    # which appears automatically regardless of which page is open,
    # rather than requiring a visit to Page 1 specifically. The Suspicious/
    # Warning banner near the top of this page still reflects dismissal
    # state via is_dismissed (set above), so that part is unchanged.
