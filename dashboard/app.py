"""
AI Smart Visitor Authentication & Threat Monitoring System
Streamlit Dashboard — Main Entry Point

Run with:
    streamlit run app.py
"""

import streamlit as st


def _strip_css_indent(css: str) -> str:
    """
    Strips ALL leading whitespace from every line, individually — NOT
    textwrap.dedent()'s "common shared prefix" approach, which was
    tried first and CONFIRMED (via a real AppTest run inspecting the
    actual generated string) to leave most lines still indented 4+
    spaces. Root issue: this CSS has two real nesting depths baked in
    by Python's own source formatting (e.g. ":root {" at 4 spaces,
    its "--bg-page: ...;" properties at 8 spaces) — dedent() only
    strips the SMALLEST common indentation across the whole string (4,
    matching ":root {"), leaving the deeper 8-space lines with 4
    leftover spaces — still ≥4, still triggering Markdown's "indented
    code block" rule that was the actual root cause of the entire
    "</div> renders as visible text" bug. Stripping every line
    individually sidesteps that entirely, regardless of how many
    nesting depths the original Python source has. Cosmetic-only loss:
    the raw CSS source becomes flush-left instead of nested — CSS
    itself doesn't care about whitespace, so this has zero effect on
    the actual styling, only on how the string looks if printed raw.
    """
    return "\n".join(line.strip() if line.strip() else "" for line in css.split("\n"))

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
#
# CONFIRMED BUG (Streamlit's own docs, st.context.theme page): "the theme
# type may be incorrect... when the app is first loaded within a session,
# [or] when the user changes the theme in the settings menu." This
# directly explains a screenshot showing Smart Event Panel / Sensor
# Health labels still using light-mode colors despite a dark navy
# background actually being rendered (from config.toml, a separate
# mechanism this Python read doesn't control). Per a Streamlit engineer
# on GitHub issue #11870: "any user interaction will lead to the correct
# value being accessible on the backend" — i.e. one extra rerun fixes it.
# This forces exactly ONE corrective rerun per session, immediately,
# rather than waiting for the person to happen to click something —
# session_state guards it so it only ever fires once, not on every
# normal rerun afterward.
try:
    _active_theme = st.context.theme.type
except Exception:
    _active_theme = "light"

# Force up to 2 corrective reruns per session. A value-COMPARISON
# approach (rerun only if the reading changed) was considered and
# rejected: if the very first reading is wrong and STAYS wrong on the
# next rerun too (the docs don't guarantee exactly one rerun fixes it,
# just that "any user interaction" eventually does), comparing against
# that same wrong value would never trigger a second attempt — silently
# stuck wrong for the whole session. A simple bounded retry count avoids
# that failure mode, at the cost of 1-2 invisible extra reruns on every
# session start, which is cheap compared to rendering the wrong theme
# for the user's entire visit.
_rerun_attempts = st.session_state.get("_theme_rerun_attempts", 0)
if _rerun_attempts < 2:
    st.session_state["_theme_rerun_attempts"] = _rerun_attempts + 1
    st.rerun()

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
#
# ROOT CAUSE FINALLY CONFIRMED, via direct browser DOM inspection: every
# line of this CSS block is indented 4+ spaces (inherited from Python's
# own code indentation) — and Markdown's spec treats ANY line indented
# 4+ spaces from a paragraph start as a literal "indented code block",
# rendering it as plain TEXT rather than interpreting it as HTML, even
# with unsafe_allow_html=True set. This is why the entire <style> block
# was visible as literal page text (the "</div>" mystery was just one
# substring inside that wall of text, at whatever scroll position it
# happened to land). Small single-line f-string divs elsewhere in the
# codebase (badges, alert banners) never hit this, since they have zero
# leading whitespace — only this large, Python-indented multi-line
# block did.
#
# textwrap.dedent() was tried first and CONFIRMED, via an actual AppTest
# run inspecting the real generated string, to NOT fully fix this — it
# only strips the smallest COMMON indentation across the whole string,
# but this CSS has two genuine nesting depths (":root {" at 4 spaces,
# its "--xxx: ...;" properties at 8 spaces), so dedent() only removed 4
# of the 8, leaving those property lines still at 4 — still triggering
# the same bug. _strip_css_indent() (defined above) strips every line's
# leading whitespace individually instead, which is robust regardless
# of how many nesting depths exist.
_css_rest = _strip_css_indent("""
    /* Main content padding — top increased from 1rem to clear Streamlit
       Cloud's platform bar (Share/Star/Edit/GitHub/⋮), which sits in a
       fixed strip above the app and isn't controlled by this app's code. */
    .block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; }

    /* BODY TEXT SIZE FIX, per explicit feedback wanting content text at
       least as large as a typical chat interface. Most of the existing
       inline-styled card content across page1/2/3_*.py uses font-size
       values between 0.7rem and 0.83rem (~11-13px) — genuinely smaller
       than a typical chat message (~16px/1rem). Rather than hand-edit
       a dozen individual declarations (error-prone, easy to miss some),
       this increases the document ROOT font-size — since rem units are
       defined relative to the root, every existing rem-based size
       across all three pages scales up proportionally and consistently
       from this one rule, without touching each one individually. 16px
       is the browser default; 18px (1.125x) noticeably closer to chat
       text size without making everything oversized. */
    html { font-size: 18px; }

    /* Main page title, sidebar title, and the document root all need
       the bold treatment to clearly read as titles, not body content —
       see h1-h6 rule further below. */

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
       restructuring any of the already-tested page Python code.

       BUGFIX (asymmetric bottom padding): confirmed via screenshot that
       cards in the same row (e.g. "Smart event panel" next to "Door
       status") had excessive empty space below their content, but tight
       spacing above it — not a padding problem, a STRETCHING one.
       st.columns() generates a flexbox row (stHorizontalBlock), and
       flexbox's default align-items:stretch makes every column in that
       row match the height of its TALLEST sibling — so a shorter
       column's card gets stretched well past its own content, with all
       the extra space landing at the bottom (since content is top-
       aligned by default). align-self:flex-start on the column itself
       (the actual flex item) opts it out of that stretch, letting each
       card size to its own real content height instead. */
    div[data-testid="stColumn"]:not(div[data-testid="stColumn"] div[data-testid="stColumn"]) {
        align-self: flex-start;
    }
    div[data-testid="stColumn"]:not(div[data-testid="stColumn"] div[data-testid="stColumn"]) > div {
        background: var(--bg-card);
        border-radius: 18px;
        padding: 10px;
        box-shadow: var(--card-shadow);
    }
    /* BUGFIX: on Page 1, the "Back" button slot renders an empty column
       (cur_idx == 0 means the button is conditionally skipped, but the
       surrounding st.columns(2) structure still creates the column div
       either way) — confirmed via screenshot showing a visible empty
       card box where Back would be. :empty rolls back the card styling
       for any column with genuinely no rendered content inside it. */
    div[data-testid="stColumn"]:not(div[data-testid="stColumn"] div[data-testid="stColumn"]) > div:empty {
        background: transparent;
        box-shadow: none;
        padding: 0;
    }
    /* BUGFIX: the Retry button (page1_realtime.py) sits in a narrow
       column that was getting the full card treatment despite holding
       only one small button — confirmed via screenshot showing an
       oversized box around "Retry". Wrapped in st.container(key=
       "retry_btn_container") specifically so this CSS can exclude just
       that one instance, without affecting any other column.

       Second bugfix, same root cause as the main card stretching issue:
       even with background/padding zeroed out above, the COLUMN ITSELF
       (the flex item) was still being stretched to match the taller
       alert-banner column beside it in the same row — confirmed via a
       follow-up screenshot showing the transparent box still occupying
       the full row height. align-self:flex-start on the column (not
       just its keyed child) opts it out of that stretch too. */
    div[data-testid="stColumn"]:has(.st-key-retry_btn_container) {
        align-self: flex-start;
    }
    .st-key-retry_btn_container {
        background: transparent !important;
        box-shadow: none !important;
        padding: 0 !important;
    }

    /* Page 3 pipeline diagram, per explicit screenshot annotation: the
       first 7 steps need a visible boundary that hugs THEIR combined
       width (the "yellow box" in the annotation), separate from the
       8th step's own boundary (the "black box"). Both wrapped in
       st.container(horizontal=True) in page3_logs.py — CONFIRMED via
       Streamlit's own docs that horizontal containers size themselves
       based on their CONTENT natively (unlike st.columns, which divides
       fixed proportions of the full width) — so no extra CSS forcing
       is needed for the outer shrink-to-fit behavior at all. This CSS
       only adds the visible background/border decoration on top of
       that already-correct native sizing. */
    /* Page 3 pipeline diagram. BUGFIX confirmed via screenshot: the
       wrapper's own background (var(--bg-card-alt)) was IDENTICAL to
       each individual pill's background — same variable used in both
       places — so the pills visually disappeared into their own
       wrapper, showing as one solid rectangle with floating text
       instead of distinct rounded pills. Also corrected per explicit
       feedback: the two groups should NOT look stylistically different
       from each other (no border/color distinction) — the original
       screenshot annotation was purely about matching the OUTER height
       to the title card's height above it, not about visually
       differentiating "group of 7" from "the 8th step". Both wrappers
       now use a transparent background — just a thin neutral outline,
       sized to height/content only — so each pill's own background
       (set in page3_logs.py) is what actually shows. */
    .st-key-flow_main_steps, .st-key-flow_last_step {
        background: transparent !important;
        border: 1px solid var(--bg-card-alt) !important;
        border-radius: 14px !important;
        padding: 8px !important;
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
       Dashboard") get the card-surface treatment AND shrink-to-fit
       their own text width — rather than stretching across the full
       row, which looked disconnected from the actual title text.
       stHeadingWithActionElements is the real, current Streamlit
       wrapper testid for st.header/st.subheader/st.title text — NOT
       stHeader, which is a different element (the top app chrome bar). */
    [data-testid="stHeadingWithActionElements"] {
        background: var(--bg-card);
        border-radius: 18px;
        padding: 10px 16px;
        display: inline-block;
        width: fit-content;
        max-width: 100%;
        white-space: normal;
        box-shadow: var(--card-shadow);
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

    /* Main alert banner. UPDATED per explicit feedback: previously
       deliberately full-width per the design brief's "impossible to
       miss" requirement — but the person has now explicitly asked for
       it to wrap its own content instead, confirmed via screenshot
       showing it spanning the entire row. width:fit-content makes the
       box only as wide as its actual text, same approach as a standard
       inline error message. */
    .alert-danger, .alert-warning {
        background: var(--alert-bg);
        color: var(--alert-text);
        border: none;
        border-radius: 14px;
        padding: 12px 18px;
        font-size: 0.9rem;
        font-weight: 700;
        margin-bottom: 12px;
        width: fit-content;
        max-width: 100%;
        display: inline-block;
        box-shadow: var(--card-shadow);
    }

    /* THE fix for the "Connection to Raspberry Pi lost" banner width —
       confirmed via a live crash (StreamlitInvalidWidthError) that
       st.error()'s width parameter genuinely only accepts "stretch" or
       a fixed pixel integer, NOT "content" — there is no Python-side
       way to make st.error() size to its own content. This CSS rule is
       therefore the ONLY fix, not a fallback. Targets both .stAlert
       (the class form, confirmed via a real GitHub issue using this
       exact selector to add borders to alert widgets) and
       [data-testid="stAlert"] (the testid form) together, since I
       could only directly confirm the class form this time — covering
       both is safer than betting on just the unconfirmed one. */
    .stAlert, [data-testid="stAlert"] {
        width: fit-content !important;
        max-width: 100% !important;
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

    /* BUGFIX: replaces THEME_COLORS (Python-side st.context.theme.type
       detection) for these two specific spots — confirmed via screenshot
       that labels stayed dim/unreadable in dark mode despite the
       earlier fix being present in the code. Root cause, confirmed via
       Streamlit's own documentation: st.context.theme.type "may be
       incorrect... when the app is first loaded within a session, or
       when the user changes the theme in the settings menu" — exactly
       the two moments that matter most for this dashboard. A CSS class
       using var(--text-secondary-on-card) instead is resolved by the
       BROWSER at the same time as the actual background color, with no
       separate, uncertain Python read involved — so it can't fall out
       of sync with what's actually rendered the way the inline-style
       approach could. */
    .label-secondary { color: var(--text-secondary-on-card) !important; }
    .track-bg { background: var(--bg-card-alt); }
    .divider-border { border-color: var(--bg-card-alt) !important; }
</style>
""")

# Each piece (the <style> literal, _palette_css, and _css_rest) now has
# every line's leading whitespace stripped individually via
# _strip_css_indent() — confirmed via a real AppTest run to leave zero
# lines at 4+ space indentation, unlike the textwrap.dedent() attempt
# tried first, which only handled ONE of the two real nesting depths
# present in this CSS (see _strip_css_indent()'s docstring above for
# the full explanation).
st.markdown(
    "<style>" + _strip_css_indent(_palette_css) + _css_rest,
    unsafe_allow_html=True,
)

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
