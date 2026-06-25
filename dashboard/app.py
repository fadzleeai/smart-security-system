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

# ── Theme detection ────────────────────────────────────────────────────────────
# st.context.theme.type reports the person's CURRENTLY ACTIVE theme choice
# ("light" or "dark") made via Settings → Theme. Wrapped in try/except
# since this is a relatively recent API — older Streamlit versions (or any
# future API change) fall back to "light" rather than crash the whole app.
try:
    _active_theme = st.context.theme.type
except Exception:
    _active_theme = "light"

# ── Palette tokens ─────────────────────────────────────────────────────────────
# Exact hex values from the design brief. Defined once here as CSS custom
# properties (variables) rather than duplicating every rule twice for
# light/dark — each rule below references var(--xxx), and only the
# variable definitions differ between the two themes.
if _active_theme == "dark":
    _palette_css = """
    :root {
        --bg-page:        #344364;  /* deepest navy — base background */
        --bg-card:        #4f6783;  /* mid blue-gray — card surface */
        --bg-card-alt:    #6a8ba0;  /* lighter blue-gray — secondary card layer */
        --accent-bright:  #aee3eb;  /* brightest cyan — "glowing" buttons, key numbers */
        --accent-mid:     #9bcbd7;  /* secondary bright accent */
        --heading-color:  #aee3eb;  /* CONTRAST FIX: --accent-mid (#9bcbd7) measured
            only 3.31:1 against --bg-card (#4f6783) — borderline, fails
            for normal-weight text even though headings are now bold.
            Using --accent-bright instead: 4.16:1, comfortably passes. */
        --text-primary:   #aee3eb; /* key data / headline numbers, on the page bg */
        --text-secondary: #9bcbd7; /* muted labels on the PAGE bg — 5.59:1, passes WCAG AA */
        --text-secondary-on-card: #E8F4F7; /* CONTRAST FIX: secondary text
            specifically ON CARDS. The brief's --text-secondary (#81a8b9)
            measured only 2.29:1 against --bg-card (#4f6783) — calculated
            directly, confirmed unreadable. None of the 6 approved dark
            colors reach 4.5:1 against the card background; this reuses
            the theme's own near-white textColor (already defined in
            config.toml, not a new color) which measures 5.2:1 here. */
        --text-on-accent: #1F2D2A; /* dark text ON TOP of bright accent buttons */
        --alert-bg:       #ED8D5A; /* most saturated warm color — still stands out on navy */
        --alert-text:     #FFFFFF;
        --badge-ok-bg:    #aee3eb; --badge-ok-text:    #1F2D2A; /* CONTRAST FIX: was #6a8ba0 bg/#aee3eb text at 2.58:1 (fail). Swapped to bright bg + dark text — 10.22:1, also reads as a stronger "positive/good" signal. */
        --badge-warn-bg:  #81a8b9; --badge-warn-text:  #344364;
        --badge-bad-bg:   #ED8D5A; --badge-bad-text:   #FFFFFF;
        --badge-gray-bg:  #4f6783; --badge-gray-text:  #E8F4F7; /* CONTRAST FIX: was #81a8b9 text at 2.29:1 (fail) — now 5.20:1 */
        --card-shadow:    0 4px 16px rgba(0,0,0,0.35);
    }
    """
else:
    _palette_css = """
    :root {
        --bg-page:        #F4F9F6;  /* soft near-white sage — base background */
        --bg-card:        #FFFFFF;  /* card surface, floats above the sage bg */
        --bg-card-alt:    #BFDFD2; /* softest palette color — secondary card layer */
        --accent-bright:  #51999F; /* deep teal — core action buttons */
        --accent-mid:     #4198AC; /* second deep teal — card titles/icons */
        --heading-color:  #4198AC; /* same as accent-mid — light mode headings
            weren't flagged as a contrast problem (measured fine on
            white cards), kept as-is for visual consistency with buttons */
        --text-primary:   #1F2D2A;
        --text-secondary: #1F2D2A; /* CONTRAST FIX: see --text-secondary-on-card
            below — none of the 8 approved light-palette colors reach
            4.5:1 against white (measured directly; best was 3.33:1),
            since they're saturated accent colors, not designed for
            body-text use. Using the same dark neutral as primary text,
            just lower font-weight, instead of introducing an unreadable
            "secondary" color from the palette. */
        --text-secondary-on-card: #4A5C57; /* muted dark green-gray,
            derived from --text-primary — 7.1:1 contrast on white cards */
        --text-on-accent: #FFFFFF; /* light text on top of the deep teal buttons */
        --alert-bg:       #ED8D5A; /* most saturated color in the palette, per brief */
        --alert-text:     #FFFFFF;
        --badge-ok-bg:    #BFDFD2; --badge-ok-text:    #1F2D2A;
        --badge-warn-bg:  #DBCB92; --badge-warn-text:  #1F2D2A;
        --badge-bad-bg:   #ED8D5A; --badge-bad-text:   #FFFFFF;
        --badge-gray-bg:  #7BC0CD; --badge-gray-text:  #1F2D2A;
        --card-shadow:    0 2px 10px rgba(81,153,159,0.12);
    }
    """

# ── Global CSS ────────────────────────────────────────────────────────────────
# BUGFIX: _palette_css's :root{...} block must be INSIDE the <style> tag.
# Previously the <style> tag was only opened in the second string below,
# AFTER _palette_css was concatenated in front of it — meaning :root{...}
# sat outside any <style> tag entirely and rendered as literal visible
# page text (confirmed from a live screenshot showing the raw CSS as
# text content at the top of the page, not applied as styling at all).
st.markdown("<style>" + _palette_css + """
    /* Main content padding — top increased from 1rem to clear Streamlit
       Cloud's platform bar (Share/Star/Edit/GitHub/⋮), which sits in a
       fixed strip above the app and isn't controlled by this app's code. */
    .block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; }

    /* Hide the hyperlink/anchor icon Streamlit auto-adds to EVERY markdown
       header (#, ##, ###, ####, #####) on hover. st.header/st.subheader
       calls use their own anchor=False parameter instead (see app.py and
       page1/2/3_*.py) — this CSS rule is the global fallback covering
       every st.markdown("##### ...") card sub-title across all three
       pages, since those don't have an anchor parameter to set directly.
       data-testid is a stable Streamlit contract, unlike auto-generated
       class names (e.g. old .css-XXXXX selectors), so this should keep
       working across Streamlit version upgrades. */
    [data-testid="stHeaderActionElements"] { display: none; }

    /* Card-based design: every MAJOR panel gets a soft rounded card
       surface — per brief's "card-based, soft layering, generous
       rounding". Deliberately conservative: only OUTER-level columns
       get the card treatment, not every nested label/value column pair
       inside them (e.g. the "System status: Monitoring" rows in the
       Smart Event Panel) — those would fragment into a dozen tiny
       cards instead of reading as one cohesive panel if styled the
       same way. The :not() clause excludes any stColumn whose nearest
       stColumn ancestor IS itself a stColumn — i.e. nested columns are
       deliberately skipped, achieved purely in CSS rather than
       restructuring any of the already-tested page Python code. */
    div[data-testid="stColumn"]:not(div[data-testid="stColumn"] div[data-testid="stColumn"]) > div {
        background: var(--bg-card);
        border-radius: 18px;
        box-shadow: var(--card-shadow);
        padding: 16px;
    }
    div[data-testid="stExpander"] {
        background: var(--bg-card);
        border-radius: 18px;
        box-shadow: var(--card-shadow);
    }

    /* Card titles & section headers — deep accent color throughout, per
       brief's "card titles and main icons unified in deep teal/cyan so
       the interface's skeleton is clear". BOLD added per explicit
       feedback so section titles ("Smart event panel", "Door status",
       etc.) are immediately distinguishable from the regular-weight
       body content/data underneath them, at a glance. */
    h1, h2, h3, h4, h5, h6 {
        color: var(--heading-color) !important;
        font-weight: 700 !important;
    }

    /* Big page titles (st.header — "Real-time monitoring & device
       status") AND the sidebar title (st.subheader — "Security
       Dashboard") get the same card-surface + rounded-border treatment
       as the rest of the dashboard's cards, per explicit feedback.
       stHeadingWithActionElements is the real, current Streamlit
       wrapper testid for st.header/st.subheader/st.title text — NOT
       stHeader, which is a different element (the top app chrome bar). */
    [data-testid="stHeadingWithActionElements"] {
        background: var(--bg-card);
        border-radius: 18px;
        box-shadow: var(--card-shadow);
        padding: 14px 20px;
    }

    /* CONTRAST FIX: --text-secondary as originally assigned (#81a8b9 on
       dark mode's --bg-card #4f6783) measures only 2.29:1 contrast —
       calculated directly, well below WCAG's 4.5:1 minimum for body
       text. None of the 6 approved dark-palette colors reach 4.5:1
       against the mid-toned card background — a genuine constraint of
       this exact palette, not a styling oversight. Fixed by using the
       dark theme's own near-white base text color (already defined as
       theme.dark.textColor in config.toml, not a new color) specifically
       for secondary text ON CARDS, which measures 5.2:1 — comfortably
       readable regardless of which theme is active. */
    .muted, [data-testid="stCaptionContainer"] {
        color: var(--text-secondary-on-card) !important;
    }

    /* Sidebar width */
    [data-testid="stSidebar"] {
        min-width: 230px; max-width: 230px;
        background: var(--bg-card-alt) !important;
    }
        background: var(--bg-card-alt) !important;
    }
    [data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

    /* All sidebar buttons — left-aligned, no border, full width, fully
       rounded per brief's pill-shaped, friendly nav style */
    div[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        text-align: left !important;
        justify-content: flex-start !important;
        background: transparent;
        border: none !important;
        border-radius: 999px;
        padding: 9px 16px;
        font-size: 0.87rem;
        color: var(--text-primary);
        margin-bottom: 2px;
        box-shadow: none !important;
    }
    div[data-testid="stSidebar"] .stButton > button:hover {
        background: var(--bg-card) !important;
        color: var(--accent-mid) !important;
    }

    /* Active nav item — deep accent highlight, matching brief's "make it
       obvious where to click" emphasis */
    div[data-testid="stSidebar"] .nav-active .stButton > button {
        background: var(--accent-bright) !important;
        color: var(--text-on-accent) !important;
        font-weight: 600 !important;
        border-radius: 999px !important;
        padding-left: 16px !important;
    }

    /* Back / Next buttons — smaller */
    div[data-testid="stSidebar"] .nav-arrow .stButton > button {
        font-size: 0.78rem;
        padding: 6px 10px;
        color: var(--text-secondary);
    }

    /* Core action buttons (Stop Alert, Refresh, Retry, popup actions) —
       brief: "unified deep teal/glowing cyan background so users know
       exactly what's clickable". Targets Streamlit's real button
       element directly, not just sidebar nav buttons, so this covers
       every st.button() across all three pages and the alert popup. */
    div[data-testid="stMainBlockContainer"] .stButton > button,
    div[data-testid="stDialog"] .stButton > button {
        background: var(--accent-bright) !important;
        color: var(--text-on-accent) !important;
        border: none !important;
        border-radius: 14px !important;
        font-weight: 600 !important;
        box-shadow: var(--card-shadow);
    }
    div[data-testid="stMainBlockContainer"] .stButton > button:hover,
    div[data-testid="stDialog"] .stButton > button:hover {
        filter: brightness(1.08);
    }
    div[data-testid="stMainBlockContainer"] .stButton > button:disabled {
        opacity: 0.5;
        filter: none;
    }

    /* Badges — fully rounded pills throughout, per brief, using the
       softer palette tones so status tags read as layered information,
       not competing alarms (only the main alert banner below is allowed
       to be the loudest element on the page, per brief's hierarchy rule). */
    .badge {
        display: inline-block;
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-green { background: var(--badge-ok-bg);   color: var(--badge-ok-text); }
    .badge-red   { background: var(--badge-bad-bg);  color: var(--badge-bad-text); }
    .badge-amber { background: var(--badge-warn-bg); color: var(--badge-warn-text); }
    .badge-blue  { background: var(--bg-card-alt);   color: var(--accent-mid); }
    .badge-gray  { background: var(--badge-gray-bg); color: var(--badge-gray-text); }

    /* Main alert banner — brief: "the MOST attention-grabbing color,
       white text, must be impossible to miss at first glance". This is
       deliberately the ONLY place --alert-bg appears as a full-width
       background (not just a badge accent), so it stays unmistakably
       the loudest thing on the page, matching the brief's visual
       hierarchy rule precisely. */
    .alert-danger, .alert-warning {
        background: var(--alert-bg);
        color: var(--alert-text);
        border: none;
        border-radius: 14px;
        padding: 12px 18px;
        font-size: 0.9rem;
        font-weight: 700;
        margin-bottom: 12px;
        box-shadow: var(--card-shadow);
    }

    /* Image placeholder */
    .img-placeholder {
        background: var(--bg-card-alt);
        border: 1px dashed var(--text-secondary);
        border-radius: 14px; height: 140px;
        display:flex; align-items:center; justify-content:center;
        color: var(--text-secondary); font-size:0.8rem; text-align:center;
    }

    /* Misc */
    .muted { color: var(--text-secondary); font-size:0.78rem; }
    .section-divider { border:none; border-top:1px solid var(--bg-card-alt); margin:10px 0; }
</style>
""", unsafe_allow_html=True)

# ── Page imports ──────────────────────────────────────────────────────────────
from pages_src.page1_realtime  import render as render_page1
from pages_src.page2_analytics import render as render_page2
from pages_src.page3_logs      import render as render_page3
from pages_src.alert_popup     import render_alert_popup

# ── Session state ─────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state["page"] = "realtime"

# ── Sidebar ───────────────────────────────────────────────────────────────────
# The ">" chevron icon (top-left of screen) is built into Streamlit automatically.
# It collapses/reopens this sidebar — no extra code needed.

with st.sidebar:
    st.subheader("🔒 Security Dashboard", anchor=False)
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
st.header(titles[st.session_state["page"]], anchor=False)
st.markdown("---")

# ── Global alert popup ────────────────────────────────────────────────────────
# Checked before EVERY page render, regardless of which page is active —
# this is what makes the popup appear "no matter which page" per the
# requirement, rather than being tied to Page 1's render() specifically.
render_alert_popup()

# ── Render active page ────────────────────────────────────────────────────────
if st.session_state["page"] == "realtime":
    render_page1()
elif st.session_state["page"] == "analytics":
    render_page2()
else:
    render_page3()
