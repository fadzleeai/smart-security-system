"""
pages_src/alert_popup.py
Global alert popup — stranger detected or door left open.

DESIGN NOTES (so future edits don't accidentally break the intent):

- Triggered from app.py, called once per script run, BEFORE the active
  page renders. This is what makes it appear "regardless of which page
  you're on" — it's not page-specific code, it's checked at the top level.

- True zero-delay push from hardware to browser is NOT possible in
  Streamlit (confirmed, not a missing feature on our end — Streamlit
  only reruns on user interaction or a forced timer). This file uses
  st_autorefresh at a 3-second interval as the closest practical
  approximation. If st_autorefresh isn't installed, the popup still
  works correctly on every normal interaction — it just won't appear
  on its own between clicks, only after the next click.

- Uses st.dialog (stable as of Streamlit 1.37+, NOT st.modal or a
  third-party package) — requirements.txt must specify
  streamlit>=1.37.0 for this to exist at all.

- Stranger popup takes priority over door-open popup if both are active
  at once — see get_active_alert()'s docstring in data_source.py for why.
"""

import streamlit as st
from data_source import get_active_alert, tag_stranger, stop_alarm

try:
    from streamlit_autorefresh import st_autorefresh
    _AUTOREFRESH_AVAILABLE = True
except ImportError:
    _AUTOREFRESH_AVAILABLE = False


def _dismiss_for_session(key: str):
    """
    Marks an alert as dismissed for THIS browser session only (not
    server-side) — used so clicking any action button closes the popup
    immediately without waiting for the next 3s refresh cycle to catch up.
    """
    st.session_state[f"_alert_dismissed_{key}"] = True


def _is_dismissed_this_session(key: str) -> bool:
    return st.session_state.get(f"_alert_dismissed_{key}", False)


@st.dialog("🚨 Stranger Detected", width="large")
def _stranger_dialog(filename: str, img_url: str):
    if img_url:
        st.image(img_url, use_container_width=True)
    else:
        st.warning("Image unavailable.")

    st.markdown(f"**File:** `{filename}`")
    st.markdown("This person was not recognized. What would you like to do?")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ Authorize", use_container_width=True,
                      help="Saves this photo to pending_authorize/ for manual review — does NOT auto-register their face"):
            result = tag_stranger(filename, "authorize_pending")
            if result.get("success"):
                st.success("Tagged for authorization review.")
                _dismiss_for_session(filename)
                st.rerun()
            else:
                st.error(result.get("message", "Failed to tag."))

    with col2:
        if st.button("❌ Label Unknown", use_container_width=True,
                      help="Confirms this as an unknown visitor needing further review"):
            result = tag_stranger(filename, "unknown_reviewed")
            if result.get("success"):
                st.success("Tagged as unknown.")
                _dismiss_for_session(filename)
                st.rerun()
            else:
                st.error(result.get("message", "Failed to tag."))

    with col3:
        if st.button("🔕 Stop Alert", use_container_width=True,
                      help="Silences the alarm and tags as unknown, pending further review"):
            stop_alarm()
            result = tag_stranger(filename, "unknown_reviewed")
            if result.get("success") or True:
                # Per your decision: Stop Alert also tags as
                # unknown_reviewed (same as Label Unknown) — both end up
                # needing further review, the only difference is which
                # button the owner happened to press.
                _dismiss_for_session(filename)
                st.rerun()


@st.dialog("🚪 Door Left Open", width="medium")
def _door_dialog():
    st.warning("The door has been open for longer than expected.")
    st.markdown(
        "If the door is still open after stopping this alert, "
        "the popup will reappear."
    )

    if st.button("🔕 Stop Alert", use_container_width=True, type="primary"):
        stop_alarm()
        # Deliberately NOT marked dismissed-for-session here — per your
        # requirement, this one should keep reappearing if the door is
        # still open on the next check, unlike the stranger popup which
        # is dismissed once tagged. Closing now; get_active_alert() will
        # re-trigger it on the next autorefresh if door_alert is still True.
        st.rerun()


def render_alert_popup():
    """
    Call this once from app.py, before rendering the active page.
    Checks get_active_alert() and opens the matching dialog if needed.
    """
    if _AUTOREFRESH_AVAILABLE:
        st_autorefresh(interval=3000, key="alert_popup_autorefresh")

    alert = get_active_alert()

    if alert["type"] == "stranger":
        filename = alert["filename"]
        if not _is_dismissed_this_session(filename):
            _stranger_dialog(filename, alert.get("img_url"))

    elif alert["type"] == "door":
        # No session-dismiss check here — see _door_dialog()'s comment.
        _door_dialog()
