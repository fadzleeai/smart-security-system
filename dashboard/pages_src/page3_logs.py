"""
pages_src/page3_logs.py
Page 3 — Historical audit logs
"""

import io
from datetime import datetime

import streamlit as st
import pandas as pd
from data_source import get_full_logs, refresh_logs, PI_TIMEZONE

# CORRECTED finding: st.dataframe() has a transparent background by
# default and follows the app's actual theme (confirmed: a Streamlit
# forum post explicitly notes "the standard st.dataframes have a
# transparent background" — not an independently-fixed light background
# as initially assumed). So the table header's hardcoded #6b7280 text
# and #e5e7eb border genuinely do need theme-aware values, same as every
# other hardcoded-gray fix elsewhere in this app.
try:
    _table_theme = st.context.theme.type
except Exception:
    _table_theme = "light"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _colour_result(val: str) -> str:
    if val == "Authorized":
        return "background-color:#d1fae5; color:#065f46; font-weight:600"
    if val == "Denied":
        return "background-color:#fee2e2; color:#991b1b; font-weight:600"
    if val == "Pending Authorization":
        return "background-color:#dbeafe; color:#1e40af; font-weight:600"
    if val == "Reviewed — Unknown":
        return "background-color:#f3f4f6; color:#374151; font-weight:600"
    return ""


def _colour_threat(val: str) -> str:
    if val == "Suspicious":
        return "background-color:#fee2e2; color:#991b1b; font-weight:600"
    if val == "Warning":
        return "background-color:#fef3c7; color:#92400e; font-weight:600"
    # NOTE: "None" threat level falls through to here with no background
    # pairing at all — genuinely a gap, in the same category as the other
    # hardcoded-gray fixes elsewhere. CORRECTED from an earlier assumption:
    # st.dataframe() is confirmed to have a transparent background by
    # default (not an independent fixed-light background) — it follows
    # the app's actual theme. So a plain "color:#6b7280" genuinely would
    # look wrong specifically in dark mode. Returning "" (inherit) avoids
    # guessing a fixed text color that might clash with either theme.
    return ""


def _style_df(df: pd.DataFrame):
    """
    Applies per-cell colour styling to the logs table.

    NOTE: pandas deprecated Styler.applymap() in 2.1 and removed it in
    later releases — .map() is the replacement for elementwise styling.
    We try .map() first (current pandas on Streamlit Cloud) and fall back
    to .applymap() for anyone still on an older pandas locally, so this
    keeps working either way without crashing.
    """
    styler = df.style
    try:
        styler = (
            styler
            .map(_colour_result, subset=["Auth result"])
            .map(_colour_threat, subset=["Threat"])
        )
    except AttributeError:
        styler = (
            styler
            .applymap(_colour_result, subset=["Auth result"])
            .applymap(_colour_threat, subset=["Threat"])
        )

    header_text_color = "#9bcbd7" if _table_theme == "dark" else "#6b7280"
    header_border     = "#81a8b9" if _table_theme == "dark" else "#e5e7eb"

    return styler.set_table_styles([
        {"selector": "th",
         "props": [("font-size", "0.78rem"),
                   ("color", header_text_color),
                   ("font-weight", "500"),
                   ("border-bottom", f"1px solid {header_border}")]},
        {"selector": "td",
         "props": [("font-size", "0.8rem"),
                   ("padding", "6px 10px")]},
    ])


def _parse_log_date(timestamp_str: str):
    """
    Timestamp column from get_full_logs() is formatted as
    '%Y-%m-%d %I:%M:%S %p' (e.g. '2026-06-24 01:31:15 PM').
    Pull just the date portion back out for filtering.
    Returns None if the string can't be parsed (e.g. '—' placeholder rows).
    """
    try:
        return datetime.strptime(str(timestamp_str)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ── Flow diagram ──────────────────────────────────────────────────────────────

FLOW_STEPS = [
    "PIR detects motion",
    "Camera activated",
    "Face recognition",
    "Decision logic",
    "Save stranger image",
    "Write security_logs.csv",
    "Pi API serves logs",  # shortened from "Pi API serves /logs" — the
                            # slash made this phrase wrap to 2 lines in a
                            # pill sized the same as the others; dropping
                            # it keeps the meaning intact while fitting
                            # on one line, per explicit feedback
    "Streamlit fetches via tunnel",
]

def _render_flow():
    # Per explicit feedback (screenshot annotation): the first 7 steps
    # need a visible boundary that hugs THEIR combined width, separate
    # from the 8th ("Streamlit fetches via tunnel"), which gets its own
    # independently-sized boundary, both sitting side by side on one row.
    #
    # Both the OUTER row (flow_main_steps vs flow_last_step) and the
    # INNER row (the 7 individual pills) now use st.container(horizontal
    # =True) rather than st.columns() — confirmed via Streamlit's own
    # docs that horizontal containers size themselves based on content,
    # while st.columns() always divides 100% of the PARENT's width into
    # fixed proportions regardless of actual content size. Mixing the
    # two (content-sized outer wrapper + percentage-based inner columns)
    # would fight against itself — the inner columns would still try to
    # claim however much width the now-shrunk parent happens to have,
    # which isn't the same thing as sizing to each pill's own text.
    # Using horizontal=True consistently at both levels keeps every pill
    # sized to its own label, and the whole 7-pill group then naturally
    # hugs the sum of those individual pill widths.
    main_steps = FLOW_STEPS[:-1]
    last_step  = FLOW_STEPS[-1]

    with st.container(horizontal=True):
        with st.container(key="flow_main_steps", horizontal=True):
            for step in main_steps:
                st.markdown(
                    f'<div style="background:var(--bg-card-alt);color:var(--text-primary);'
                    f'border-radius:20px;padding:8px 10px;font-size:0.7rem;font-weight:600;'
                    f'text-align:center;line-height:1.3;min-height:48px;'
                    f'display:flex;align-items:center;justify-content:center;'
                    f'white-space:normal;word-break:keep-all;overflow-wrap:break-word;'
                    f'width:fit-content;">'
                    f'{step}</div>',
                    unsafe_allow_html=True,
                )

        with st.container(key="flow_last_step"):
            st.markdown(
                f'<div style="background:var(--accent-bright);color:var(--text-on-accent);'
                f'border-radius:20px;padding:8px 10px;font-size:0.7rem;font-weight:600;'
                f'text-align:center;line-height:1.3;min-height:48px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'white-space:normal;word-break:keep-all;overflow-wrap:break-word;">'
                f'{last_step}</div>',
                unsafe_allow_html=True,
            )


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    # ── Filters ───────────────────────────────────────────────────────────────
    # ISSUE 3 FIX — Page 3 stagnation. get_full_logs() is backed by a 5s
    # @st.cache_data, so it only goes stale *between* reruns — but Streamlit
    # never reruns on its own without user interaction. This button gives
    # an explicit, low-cost way to force a fresh fetch right now, instead
    # of clicking elsewhere in the sidebar as a workaround.
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.markdown("##### Full security logs")
    with col_refresh:
        if st.button("🔄 Refresh Logs", key="refresh_logs_btn", use_container_width=True):
            refresh_logs()
            st.rerun()

    # get_full_logs() pulls real rows from the Pi via /logs over the
    # Cloudflare tunnel (see data_source.py). No mock data here.
    df = get_full_logs()

    fc1, fc2, fc3 = st.columns([2, 2, 2])

    with fc1:
        type_filter = st.selectbox(
            "Filter by result",
            ["All", "Authorized", "Denied"],
            label_visibility="collapsed",
        )
    with fc2:
        threat_filter = st.selectbox(
            "Filter by threat",
            ["All threats", "None", "Warning", "Suspicious"],
            label_visibility="collapsed",
        )
    with fc3:
        # Real date filter — wired to the actual Timestamp column returned
        # by get_full_logs(). "All dates" skips filtering entirely.
        use_date_filter = st.checkbox("Filter by date", value=False)
        date_filter = None
        if use_date_filter:
            # Default to "today" in Malaysia time (matching the Pi's clock,
            # which is what every CSV timestamp actually represents) — not
            # datetime.today(), which would be wrong for hours each day
            # since Streamlit Cloud's servers run in UTC.
            date_filter = st.date_input("Date", value=datetime.now(PI_TIMEZONE).date())

    # Apply filters
    filtered = df.copy()
    if type_filter != "All":
        filtered = filtered[filtered["Auth result"] == type_filter]
    if threat_filter != "All threats":
        filtered = filtered[filtered["Threat"] == threat_filter]
    if date_filter is not None and not filtered.empty:
        row_dates = filtered["Timestamp"].apply(_parse_log_date)
        filtered = filtered[row_dates == date_filter]

    # ── Table ─────────────────────────────────────────────────────────────────
    if filtered.empty:
        st.info("No log rows match the current filters.")
    else:
        st.dataframe(
            _style_df(filtered),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(f"Showing {len(filtered)} of {len(df)} records")

    # ── Export CSV ────────────────────────────────────────────────────────────
    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇  Export filtered logs as CSV",
        data=csv_bytes,
        file_name="security_logs_export.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # ── Data flow pipeline ────────────────────────────────────────────────────
    st.markdown("")
    st.markdown("##### Data flow — how logs are written")
    _render_flow()
    st.caption(
        "Logs are read live from `security_logs.csv` on the Pi via the "
        "Cloudflare tunnel. Search and filter run client-side in Streamlit "
        "— no extra API calls needed."
    )

    # ── Quick stats from logs ─────────────────────────────────────────────────
    if not df.empty:
        st.markdown("")
        st.markdown("##### Quick stats from log data")
        s1, s2, s3 = st.columns(3)

        auth_rate = (df["Auth result"] == "Authorized").mean() * 100
        s1.metric("Auth success rate", f"{auth_rate:.0f}%")

        # avg_confidence reads the real "Confidence" column written by
        # your Pi's face_recognition pipeline (main.py write_log_row()).
        if "Confidence" in df.columns:
            auth_conf = df[df["Auth result"] == "Authorized"]["Confidence"]
            if not auth_conf.dropna().empty:
                s2.metric("Avg auth confidence", f"{auth_conf.mean():.2f}")
            else:
                s2.metric("Avg auth confidence", "—")

        suspicious_n = (df["Threat"] == "Suspicious").sum()
        s3.metric("Suspicious events", int(suspicious_n))
