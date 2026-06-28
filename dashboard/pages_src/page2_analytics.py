"""
pages_src/page2_analytics.py
Page 2 — Visitor analytics & stranger gallery
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_source import get_today_summary, get_activity_timeline, get_stranger_gallery, strip_markdown_indent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(text: str, style: str) -> str:
    """
    Same sibling-shadow structure as page1_realtime.py's _badge() — kept
    consistent across both files since they're duplicate copies of the
    same helper, not shared via import. The outer wrapper (inline-block,
    width:fit-content) determines the real footprint independent of any
    stretched parent — see page1_realtime.py's _badge() docstring for
    the full reasoning on why this is a sibling element, not a
    ::before pseudo-element.
    """
    return (
        f'<span style="display:inline-block;width:fit-content;position:relative;'
        f'margin:2px 8px 2px 2px;">'
        f'<span style="position:absolute;top:3px;left:3px;right:-3px;bottom:-3px;'
        f'background:var(--bg-card-alt);border-radius:999px;z-index:0;"></span>'
        f'<span class="badge badge-{style}" style="position:relative;z-index:1;'
        f'display:inline-block;white-space:nowrap;">{text}</span>'
        f'</span>'
    )


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
    # NOTE: bg above is still hardcoded light-mode colors, same category
    # as the door illustration (page1_realtime.py _render_door) — both
    # need their own dedicated dark-mode redesign pass, flagged but
    # deliberately not done here to avoid scope creep beyond today's
    # specific padding/contrast/font-size feedback.
    #
    # BUGFIX: label_color used to read THEME_COLORS (Python-side
    # st.context.theme.type detection), confirmed unreliable per
    # Streamlit's own docs on first load / theme changes. Suspicious
    # case keeps its own fixed red (not theme-dependent at all); the
    # non-suspicious case now uses a CSS class name instead of an
    # inline hex value, so the actual color is resolved reliably by
    # the browser via var(--text-secondary-on-card).
    label_class = "" if item["is_suspicious"] else "label-secondary"
    label_color_inline = "color:#991b1b;" if item["is_suspicious"] else ""

    # Card wrapper (border/background/label) stays as styled HTML, but the
    # actual photo now renders via st.image() instead of a placeholder
    # emoji icon — that emoji-only version was leftover mock code, never
    # actually replaced despite the comment saying to. img_path comes from
    # get_stranger_gallery() in data_source.py, pointing at the Pi's real
    # /images/<filename> route.
    st.markdown(strip_markdown_indent(f"""
    <div style="{border} background:{bg}; border-radius:8px 8px 0 0;
                 padding:8px; text-align:center;">
    """), unsafe_allow_html=True)

    if item.get("img_path"):
        try:
            st.image(item["img_path"], use_container_width=True)
        except Exception:
            st.markdown('<div style="font-size:2rem;padding:20px">⚠️</div>',
                        unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:2rem;padding:20px">👤</div>',
                    unsafe_allow_html=True)

    st.markdown(strip_markdown_indent(f"""
      <div class="{label_class}" style="font-size:0.78rem;font-weight:600;{label_color_inline}">{item['label']}</div>
      <div class="label-secondary" style="font-size:0.72rem;margin-top:2px;margin-bottom:8px">
        {item['time']} &bull; {item['visits']} visit(s)
      </div>
    </div>
    """), unsafe_allow_html=True)


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

            st.markdown(strip_markdown_indent(f"""
            <div class="divider-border" style="display:flex;gap:10px;align-items:flex-start;
                        padding:8px 0;">
              <span class="label-secondary" style="font-size:0.75rem;min-width:62px;padding-top:3px">
                {item['time']}
              </span>
              {dot}
              <div>
                <div style="font-size:0.83rem;font-weight:500">
                  {item['visitor']} &nbsp; {result_b} &nbsp; {threat_b}
                </div>
                <div class="label-secondary" style="font-size:0.75rem;margin-top:2px">
                  {item['note']}
                </div>
              </div>
            </div>
            """), unsafe_allow_html=True)

    # ── Stranger gallery ──────────────────────────────────────────────────────
    st.markdown("")
    st.markdown("##### Stranger gallery — 3 latest")

    if not gallery:
        st.info("No unknown visitors recorded today.")
    else:
        # Explicit requirement: show the 3 latest stranger images in a row.
        # gallery is already sorted newest-first by get_stranger_gallery(),
        # so [:3] here is genuinely the 3 most recent, not an arbitrary slice.
        latest_three = gallery[:3]
        cols = st.columns(3)
        for i, col in enumerate(cols):
            with col:
                if i < len(latest_three):
                    _stranger_card(latest_three[i])
                else:
                    # Fewer than 3 strangers exist — show an empty slot
                    # rather than stretching 1-2 cards to fill the row.
                    st.markdown(
                        '<div class="divider-border label-secondary" style="border:1px dashed; border-radius:8px; '
                        'padding:20px; text-align:center; min-height:160px; '
                        'display:flex;align-items:center;justify-content:center">'
                        '<span style="font-size:0.78rem">No more strangers</span></div>',
                        unsafe_allow_html=True,
                    )

    st.caption(
        "Images served live from the Pi's `strangers/` folder via "
        "the /images/ route — not cached or stored on Streamlit Cloud."
    )
