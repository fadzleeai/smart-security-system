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

import time
import streamlit as st
from data_source import get_active_alert, tag_stranger, stop_alarm

try:
    from streamlit_autorefresh import st_autorefresh
    _AUTOREFRESH_AVAILABLE = True
except ImportError:
    _AUTOREFRESH_AVAILABLE = False

# How many filenames to remember at once for session-dismiss and
# in-progress tracking. Previously each distinct stranger filename
# created a brand new, never-removed st.session_state key (one for
# dismissed, one for in-progress) — over a long-running session this
# grows forever. A genuinely "infinite" stranger count was never
# realistic, so capping at a generous number and evicting the oldest
# entry once full bounds memory growth without affecting normal use —
# you'd need more than this many DISTINCT, never-finally-reviewed
# strangers in a single browser session before anything is evicted,
# and an evicted entry just means the popup might very briefly
# reappear for that one old filename before the server-side
# /stranger/pending check (which is authoritative regardless) catches
# up — never a correctness issue, only a possible few-second flicker
# for something that old.
_MAX_TRACKED_FILENAMES = 200


def _get_tracked_set(state_key: str) -> dict:
    """
    Returns the single dict backing either the dismissed-set or the
    in-progress-set, creating it empty on first use. Using one dict per
    concern (not one key per filename) is what makes capping possible —
    there's exactly one st.session_state entry per concern, ever,
    regardless of how many strangers appear over the session's lifetime.
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = {}
    return st.session_state[state_key]


def _mark_tracked(state_key: str, filename: str, value: bool):
    tracked = _get_tracked_set(state_key)
    tracked[filename] = value
    if not value:
        # False entries (e.g. action_in_progress cleared after a failed
        # attempt) don't need to stick around at all — drop immediately
        # rather than waiting for eviction, since keeping a False entry
        # serves no purpose once the action is no longer in progress.
        tracked.pop(filename, None)
        return
    if len(tracked) > _MAX_TRACKED_FILENAMES:
        # Evict the oldest entry. Dicts preserve insertion order in
        # Python 3.7+, so the first key IS the oldest — no extra
        # bookkeeping (timestamps, etc) needed for this.
        oldest_key = next(iter(tracked))
        tracked.pop(oldest_key, None)


def _is_tracked(state_key: str, filename: str) -> bool:
    return _get_tracked_set(state_key).get(filename, False)


def _dismiss_for_session(key: str):
    """
    Marks an alert as dismissed for THIS browser session only (not
    server-side) — used so clicking any action button closes the popup
    immediately without waiting for the next 3s refresh cycle to catch up.
    """
    _mark_tracked("_dismissed_strangers", key, True)


def _is_dismissed_this_session(key: str) -> bool:
    return _is_tracked("_dismissed_strangers", key)


@st.dialog("🚨 Stranger Detected", width="large")
def _stranger_dialog(filename: str, img_url: str):
    if img_url:
        st.image(img_url, use_container_width=True)
    else:
        st.warning("Image unavailable.")

    st.markdown(f"**File:** `{filename}`")
    st.markdown("This person was not recognized. What would you like to do?")

    # Double-click guard: disables all three buttons the instant ANY of
    # them is clicked, until the rerun completes. Without this, a fast
    # double-click (or a slow network making someone click again,
    # thinking it didn't register) could call tag_stranger() twice for
    # the same decision — harmless to the photo itself (just overwrites
    # with identical content) but writes a duplicate CSV row, which
    # would confuse anyone reviewing the audit log later.
    action_in_progress = _is_tracked("_in_progress_strangers", filename)

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ Authorize", use_container_width=True, disabled=action_in_progress,
                      help="Saves this photo to pending_authorize/ for manual review — does NOT auto-register their face"):
            _mark_tracked("_in_progress_strangers", filename, True)
            result = tag_stranger(filename, "authorize_pending")
            if result.get("success"):
                st.success("Tagged for authorization review.")
                _dismiss_for_session(filename)
                st.rerun()
            else:
                _mark_tracked("_in_progress_strangers", filename, False)
                st.error(result.get("message", "Failed to tag."))

    with col2:
        if st.button("❌ Label Unknown", use_container_width=True, disabled=action_in_progress,
                      help="Confirms this as an unknown visitor needing further review"):
            _mark_tracked("_in_progress_strangers", filename, True)
            result = tag_stranger(filename, "unknown_reviewed")
            if result.get("success"):
                st.success("Tagged as unknown.")
                _dismiss_for_session(filename)
                st.rerun()
            else:
                _mark_tracked("_in_progress_strangers", filename, False)
                st.error(result.get("message", "Failed to tag."))

    with col3:
        if st.button("🔕 Stop Alert", use_container_width=True, disabled=action_in_progress,
                      help="Silences the alarm and tags as unknown, pending further review"):
            _mark_tracked("_in_progress_strangers", filename, True)
            alarm_result = stop_alarm()
            tag_result = tag_stranger(filename, "unknown_reviewed")

            if alarm_result.get("success") and tag_result.get("success"):
                # Both succeeded — close immediately, nothing to show.
                _dismiss_for_session(filename)
                st.rerun()
            else:
                # At least one failed — show what happened and let the
                # owner read it before deciding to close manually (an
                # immediate st.rerun() here would flash the message and
                # close the dialog before it could be read). Re-enable
                # the buttons so they can actually retry.
                _mark_tracked("_in_progress_strangers", filename, False)
                if not alarm_result.get("success"):
                    st.error(alarm_result.get("message", "Could not reach Pi to stop alarm."))
                if not tag_result.get("success"):
                    st.warning(
                        f"Tagging failed: {tag_result.get('message', 'unknown error')}. "
                        f"You can re-tag this from the stranger gallery later."
                    )
                st.caption("Click Stop Alert again to retry, or close this dialog to leave it for now.")


DOOR_POPUP_COOLDOWN_SECONDS = 10 * 60  # 10 minutes, per explicit feedback


@st.dialog("🚪 Door Left Open", width="medium", dismissible=False)
def _door_dialog():
    """
    dismissible=False per explicit feedback: previously the X in the
    corner was a second, unintended way to close this dialog alongside
    the Stop Alert button — now Stop Alert is the ONLY way out, the X
    is hidden, and click-outside/ESC are disabled too (confirmed via
    the official st.dialog docs: dismissible=False hides the X AND
    disables those other dismiss paths together, not just the X alone).
    """
    st.warning("The door has been open for longer than expected.")
    st.markdown(
        f"If the door is still open, this will reappear in "
        f"{DOOR_POPUP_COOLDOWN_SECONDS // 60} minutes."
    )

    if st.button("🔕 Stop Alert", use_container_width=True, type="primary"):
        result = stop_alarm()
        if result.get("success"):
            # BUGFIX, confirmed via real hardware testing: previously
            # NOT marking any cooldown meant get_active_alert() would
            # see door_alert still True on the VERY NEXT 3-second poll
            # (since the physical door hadn't had time to actually
            # close yet) and reopen this exact dialog instantly — from
            # the person's perspective, clicking Stop Alert looked like
            # it "did nothing", when really it correctly closed and
            # then immediately reopened, faster than visibly perceptible.
            # Recording a real timestamp here, checked in
            # render_alert_popup() below, creates an actual cooldown
            # window before the door popup can show again — separate
            # from main.py's own 30s alarm-SOUND suppression, which
            # only gates the speaker, not this dashboard popup's
            # visibility at all.
            st.session_state["_door_popup_dismissed_at"] = time.time()
            st.rerun()
        else:
            st.error(result.get("message", "Could not reach Pi to stop alarm."))
            st.caption("Click Stop Alert again to retry.")


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
        # Cooldown check, per explicit feedback: only show this dialog
        # again if DOOR_POPUP_COOLDOWN_SECONDS have genuinely passed
        # since the last time Stop Alert was clicked — fixes the
        # instant-reopen bug where clicking the button looked like it
        # "did nothing" (it correctly closed, then immediately reopened
        # on the very next 3s poll, since the physical door hadn't had
        # time to actually close). dismissed_at being unset (first time
        # ever) means no cooldown is active yet — show immediately.
        dismissed_at = st.session_state.get("_door_popup_dismissed_at")
        cooldown_active = (
            dismissed_at is not None
            and (time.time() - dismissed_at) < DOOR_POPUP_COOLDOWN_SECONDS
        )
        if not cooldown_active:
            _door_dialog()
