"""
pages_src/page2_analytics.py
Page 2 — Visitor analytics & stranger gallery
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_source import get_today_summary, get_activity_timeline, get_stranger_gallery


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(text: str, style: str) -> str:
    return f'<span class="badge badge-{style}">{text}</span>'


def _timeline_dot(result: str, threat: str) -> str:
    if threat == "Suspicious":
        color = "#ef4444"
    elif result == "Authorized":
        color = "#10b981"
    else:
        color = "#f59e0b"
    return f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:8px;flex-shrink:0;margin-top:4px"></span>'


def _result_badge(result: str) -> str:
    style = "green" if result == "Authorized" else "red"
    return _badge(result, style)


def _threat_badge(level: str) -> str:
    m = {"None": "gray", "Warning": "amber", "Suspicious": "red"}
    return _badge(level, m.get(level, "gray"))


# ── Charts ────────────────────────────────────────────────────────────────────

def _auth_bar_chart(summary: dict) -> go.Figure:
    """
    Horizontal bar chart: authorized vs unknown vs suspicious.

    # ── REAL DATA SWAP ──
    This chart reads from get_today_summary(). Once you have real CSV data,
    update get_today_summary() in data_source.py — this chart needs no changes.
    For a time-series chart (hourly visitor counts), change to:
        df = pd.read_csv("security_logs.csv", parse_dates=["timestamp"])
        df["hour"] = df["timestamp"].dt.hour
        hourly = df.groupby(["hour","auth_result"]).size().unstack(fill_value=0)
    """
    categories = ["Authorized", "Unknown", "Suspicious"]
    values     = [summary["authorized"], summary["unknown"], summary["suspicious"]]
    colors     = ["#10b981", "#f59e0b", "#ef4444"]

    fig = go.Figure(go.Bar(
        x=values, y=categories,
        orientation="h",
        marker_color=colors,
        text=values, textposition="outside",
    ))
    fig.update_layout(
        margin=dict(l=0, r=20, t=10, b=10),
        height=180,
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(tickfont=dict(size=12)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def _door_bar_chart(summary: dict) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[summary["door_normal"], summary["door_unauth"]],
        y=["Normal open", "Unauth. open"],
        orientation="h",
        marker_color=["#3b82f6", "#ef4444"],
        text=[summary["door_normal"], summary["door_unauth"]],
        textposition="outside",
    ))
    fig.update_layout(
        margin=dict(l=0, r=20, t=10, b=10),
        height=130,
        xaxis=dict(showgrid=False, showticklabels=False),
        yaxis=dict(tickfont=dict(size=12)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


# ── Stranger gallery ──────────────────────────────────────────────────────────

def _stranger_card(item: dict):
    border = "border: 1.5px solid #fca5a5;" if item["is_suspicious"] else "border: 1px dashed #d1d5db;"
    bg     = "#fff5f5" if item["is_suspicious"] else "#f9fafb"
    label_color = "#991b1b" if item["is_suspicious"] else "#6b7280"

    # ── REAL DATA SWAP ──────────────────────────────────────────────────────
    # Replace the placeholder <div> below with:
    #   if item["img_path"] and os.path.exists(item["img_path"]):
    #       st.image(item["img_path"], use_column_width=True)
    # The img_path is set in get_stranger_gallery() in data_source.py
    # ────────────────────────────────────────────────────────────────────────
    icon = "⚠️" if item["is_suspicious"] else "👤"
    st.markdown(f"""
    <div style="{border} background:{bg}; border-radius:8px;
                 padding:14px; text-align:center; min-height:130px;
                 display:flex;flex-direction:column;align-items:center;justify-content:center">
      <div style="font-size:2rem;margin-bottom:6px">{icon}</div>
      <div style="font-size:0.78rem;font-weight:600;color:{label_color}">{item['label']}</div>
      <div style="font-size:0.72rem;color:#9ca3af;margin-top:2px">
        {item['time']} &bull; {item['visits']} visit(s)
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    summary  = get_today_summary()
    timeline = get_activity_timeline()
    gallery  = get_stranger_gallery()

    # ── Summary metrics ───────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Today's visitors",  summary["total"])
    m2.metric("Authorized",        summary["authorized"],
              delta=f'{summary["authorized"]/max(summary["total"],1)*100:.0f}%',
              delta_color="normal")
    m3.metric("Unknown",           summary["unknown"])
    m4.metric("Suspicious",        summary["suspicious"],
              delta="flagged" if summary["suspicious"] > 0 else None,
              delta_color="inverse")

    st.markdown("")

    # ── Row 2: Auth chart + Timeline ──────────────────────────────────────────
    col_chart, col_timeline = st.columns([2, 3], gap="medium")

    with col_chart:
        st.markdown("##### Authentication breakdown")
        st.plotly_chart(_auth_bar_chart(summary),
                        use_container_width=True, config={"displayModeBar": False})

        st.markdown("##### Door events today")
        st.plotly_chart(_door_bar_chart(summary),
                        use_container_width=True, config={"displayModeBar": False})

    with col_timeline:
        st.markdown("##### Visitor activity timeline")

        for item in timeline:
            dot = _timeline_dot(item["result"], item["threat"])
            result_b = _result_badge(item["result"])
            threat_b = _threat_badge(item["threat"])

            st.markdown(f"""
            <div style="display:flex;gap:10px;align-items:flex-start;
                        padding:8px 0;border-bottom:1px solid #f3f4f6">
              <span style="font-size:0.75rem;color:#9ca3af;min-width:62px;padding-top:3px">
                {item['time']}
              </span>
              {dot}
              <div>
                <div style="font-size:0.83rem;font-weight:500">
                  {item['visitor']} &nbsp; {result_b} &nbsp; {threat_b}
                </div>
                <div style="font-size:0.75rem;color:#9ca3af;margin-top:2px">
                  {item['note']}
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Stranger gallery ──────────────────────────────────────────────────────
    st.markdown("")
    st.markdown("##### Stranger gallery")

    if not gallery:
        st.info("No unknown visitors recorded today.")
    else:
        cols = st.columns(min(len(gallery), 4))
        for col, item in zip(cols, gallery):
            with col:
                _stranger_card(item)

    st.caption(
        "Images loaded from `images/` on Raspberry Pi. "
        "Future improvement: add to authorized database for model retraining."
    )
