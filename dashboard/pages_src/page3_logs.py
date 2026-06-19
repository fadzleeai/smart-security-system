"""
pages_src/page3_logs.py
Page 3 — Historical audit logs
"""

import io
import streamlit as st
import pandas as pd
from data_source import get_full_logs


# ── Helpers ───────────────────────────────────────────────────────────────────

def _colour_result(val: str) -> str:
    if val == "Authorized":
        return "background-color:#d1fae5; color:#065f46; font-weight:600"
    if val == "Denied":
        return "background-color:#fee2e2; color:#991b1b; font-weight:600"
    return ""


def _colour_threat(val: str) -> str:
    if val == "Suspicious":
        return "background-color:#fee2e2; color:#991b1b; font-weight:600"
    if val == "Warning":
        return "background-color:#fef3c7; color:#92400e; font-weight:600"
    return "color:#6b7280"


def _style_df(df: pd.DataFrame):
    return (
        df.style
        .applymap(_colour_result,  subset=["Auth result"])
        .applymap(_colour_threat,  subset=["Threat"])
        .set_table_styles([
            {"selector": "th",
             "props": [("font-size","0.78rem"),
                       ("color","#6b7280"),
                       ("font-weight","500"),
                       ("border-bottom","1px solid #e5e7eb")]},
            {"selector": "td",
             "props": [("font-size","0.8rem"),
                       ("padding","6px 10px")]},
        ])
    )


# ── Flow diagram ──────────────────────────────────────────────────────────────

FLOW_STEPS = [
    "PIR detects motion",
    "Camera activated",
    "Face recognition",
    "Decision logic",
    "Save visitor image",
    "Write security_logs.csv",
    "Publish MQTT JSON",
    "Streamlit updates",
]

def _render_flow():
    cols = st.columns(len(FLOW_STEPS))
    for i, (col, step) in enumerate(zip(cols, FLOW_STEPS)):
        is_last = i == len(FLOW_STEPS) - 1
        bg      = "#dbeafe" if is_last else "#f3f4f6"
        color   = "#1e40af" if is_last else "#374151"
        with col:
            st.markdown(
                f'<div style="background:{bg};color:{color};border-radius:20px;'
                f'padding:4px 8px;font-size:0.7rem;font-weight:500;text-align:center;'
                f'line-height:1.3">{step}</div>',
                unsafe_allow_html=True,
            )


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    # ── REAL DATA SWAP ──────────────────────────────────────────────────────
    # get_full_logs() returns a DataFrame. When you have real data, update
    # that function in data_source.py to read security_logs.csv. No changes
    # needed in this file.
    # ────────────────────────────────────────────────────────────────────────
    df = get_full_logs()

    # ── Filters ───────────────────────────────────────────────────────────────
    st.markdown("##### Full security logs")

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
        # ── REAL DATA SWAP ──────────────────────────────────────────────────
        # Add a date picker here once you have real timestamps:
        #   date_filter = st.date_input("Date", value=datetime.today().date())
        #   df = df[df["timestamp"].dt.date == date_filter]
        st.markdown('<span class="muted">Date filter: add when using real CSV</span>',
                    unsafe_allow_html=True)

    # Apply filters
    filtered = df.copy()
    if type_filter != "All":
        filtered = filtered[filtered["Auth result"] == type_filter]
    if threat_filter != "All threats":
        filtered = filtered[filtered["Threat"] == threat_filter]

    # ── Table ─────────────────────────────────────────────────────────────────
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
        "Logs are read from `security_logs.csv` on the Pi. "
        "Search and filter run client-side in Streamlit — no extra API calls needed."
    )

    # ── Quick stats from logs ─────────────────────────────────────────────────
    if not df.empty:
        st.markdown("")
        st.markdown("##### Quick stats from log data")
        s1, s2, s3 = st.columns(3)

        auth_rate = (df["Auth result"] == "Authorized").mean() * 100
        s1.metric("Auth success rate",  f"{auth_rate:.0f}%")

        # ── REAL DATA SWAP ──────────────────────────────────────────────────
        # avg_confidence needs a "Confidence" column in your CSV.
        # Your Pi backend should write the face_recognition confidence score
        # (0.0 to 1.0) for every event.
        # ────────────────────────────────────────────────────────────────────
        if "Confidence" in df.columns:
            avg_conf = df[df["Auth result"] == "Authorized"]["Confidence"].mean()
            s2.metric("Avg auth confidence", f"{avg_conf:.2f}")

        suspicious_n = (df["Threat"] == "Suspicious").sum()
        s3.metric("Suspicious events",  int(suspicious_n))
