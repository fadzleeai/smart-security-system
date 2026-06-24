"""
AI Smart Visitor Authentication & Threat Monitoring System
Streamlit Dashboard — Main Entry Point

Run with:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="AI Visitor Security Dashboard",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",  # sidebar open by default
                                       # ">" chevron top-left reopens it if closed
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main content padding */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; }

    /* Sidebar width */
    [data-testid="stSidebar"] { min-width: 230px; max-width: 230px; }
    [data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

    /* All sidebar buttons — left-aligned, no border, full width */
    div[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        text-align: left !important;
        justify-content: flex-start !important;
        background: transparent;
        border: none !important;
        border-radius: 8px;
        padding: 9px 14px;
        font-size: 0.87rem;
        color: #374151;
        margin-bottom: 2px;
        box-shadow: none !important;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        background: #f3f4f6 !important;
        color: #111827 !important;
    }

    /* Active nav item — blue highlight */
    div[data-testid="stSidebar"] .nav-active .stButton > button {
        background: #eff6ff !important;
        color: #1d4ed8 !important;
        font-weight: 600 !important;
        border-left: 3px solid #1d4ed8 !important;
        border-radius: 0 8px 8px 0 !important;
        padding-left: 11px !important;
    }

    /* Back / Next buttons — smaller */
    div[data-testid="stSidebar"] .nav-arrow .stButton > button {
        font-size: 0.78rem;
        padding: 6px 10px;
        color: #6b7280;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-green { background:#d1fae5; color:#065f46; }
    .badge-red   { background:#fee2e2; color:#991b1b; }
    .badge-amber { background:#fef3c7; color:#92400e; }
    .badge-blue  { background:#dbeafe; color:#1e40af; }
    .badge-gray  { background:#f3f4f6; color:#374151; }

    /* Alert banners */
    .alert-danger {
        background:#fee2e2; color:#991b1b;
        border:1px solid #fca5a5; border-radius:8px;
        padding:10px 16px; font-size:0.85rem; font-weight:600;
        margin-bottom:12px;
    }
    .alert-warning {
        background:#fef3c7; color:#92400e;
        border:1px solid #fcd34d; border-radius:8px;
        padding:10px 16px; font-size:0.85rem; font-weight:600;
        margin-bottom:12px;
    }

    /* Image placeholder */
    .img-placeholder {
        background:#f9fafb; border:1px dashed #d1d5db;
        border-radius:8px; height:140px;
        display:flex; align-items:center; justify-content:center;
        color:#9ca3af; font-size:0.8rem; text-align:center;
    }

    /* Misc */
    .muted { color:#6b7280; font-size:0.78rem; }
    .section-divider { border:none; border-top:1px solid #f3f4f6; margin:10px 0; }
</style>
""", unsafe_allow_html=True)

# ── Page imports ──────────────────────────────────────────────────────────────
from pages_src.page1_realtime  import render as render_page1
from pages_src.page2_analytics import render as render_page2
from pages_src.page3_logs      import render as render_page3

# ── Session state ─────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state["page"] = "realtime"

# ── Sidebar ───────────────────────────────────────────────────────────────────
# The ">" chevron icon (top-left of screen) is built into Streamlit automatically.
# It collapses/reopens this sidebar — no extra code needed.

with st.sidebar:
    st.markdown("### 🔒 Security Dashboard")
    st.markdown("---")

    pages = [
        ("realtime",  "🔴  Real-time monitoring"),
        ("analytics", "📊  Visitor analytics"),
        ("logs",      "📋  Audit logs"),
    ]

    for key, label in pages:
        is_active = st.session_state["page"] == key
        # Wrap active item in a div with class nav-active for CSS highlight
        if is_active:
            st.markdown('<div class="nav-active">', unsafe_allow_html=True)
        if st.button(label, key=f"nav_{key}", use_container_width=True):
            st.session_state["page"] = key
            st.rerun()
        if is_active:
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Back / Next buttons ───────────────────────────────────────────────────
    page_keys = [p[0] for p in pages]
    cur_idx   = page_keys.index(st.session_state["page"])

    col_back, col_next = st.columns(2)
    with col_back:
        st.markdown('<div class="nav-arrow">', unsafe_allow_html=True)
        if cur_idx > 0:
            if st.button("← Back", key="nav_back", use_container_width=True):
                st.session_state["page"] = page_keys[cur_idx - 1]
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_next:
        st.markdown('<div class="nav-arrow">', unsafe_allow_html=True)
        if cur_idx < len(page_keys) - 1:
            if st.button("Next →", key="nav_next", use_container_width=True):
                st.session_state["page"] = page_keys[cur_idx + 1]
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.caption("💡 Closed the menu? Click the **>** chevron top-left to reopen.")

# ── Page title ────────────────────────────────────────────────────────────────
titles = {
    "realtime":  "🔴 Real-time monitoring & device status",
    "analytics": "📊 Visitor analytics & stranger gallery",
    "logs":      "📋 Historical audit logs",
}
st.markdown(f"## {titles[st.session_state['page']]}")
st.markdown("---")

# ── Render active page ────────────────────────────────────────────────────────
if st.session_state["page"] == "realtime":
    render_page1()
elif st.session_state["page"] == "analytics":
    render_page2()
else:
    render_page3()
