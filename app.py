"""Spencer's MSR Dashboard — Streamlit entry point.

Run with:
    streamlit run app.py

Default admin login (change after first login under Settings):
    username: admin
    password: spencers@2026
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import base64
from pathlib import Path

import auth
import db
import ingest
import processing
import renewal
import rewards_intelligence
import rewards_native
from config import AMS_SLABS, BRAND_DARK, BRAND_LIGHT, BRAND_RED

# Modular UI pieces — flat-file layout for Streamlit Cloud compatibility
from ui_styles import inject_tier_card_css
from ui_tier_cards import (
    render_tier_cards as render_tier_filter_cards,
    inject_widget_key_selectors,
)
from util_filters import apply_tier_filter, get_selected_tier
from view_loyalty_kpi import render_loyalty_kpi_page


# ---------------------------------------------------------------------------
# Page configuration & global styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Spencer's MSR Dashboard",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
    /* ===================================================================
       SPENCER'S MSR — LIGHT THEME · GOLD + SILVER · GOLDEN COMET BORDERS
    =================================================================== */
    :root {
        --bg:        #FAF7EF;
        --bg2:       #F3EEDF;
        --panel:     #FFFFFF;
        --panel-2:   #FFFDF6;
        --border:    #E4DBC2;
        --gold:      #C9A227;
        --gold-soft: #E6C766;
        --gold-deep: #9C7A18;
        --silver:    #9AA3AD;
        --silver-soft:#C7CDD4;
        --platinum:  #7E8B99;
        --diamond:   #6FA8C7;
        --text:      #2A2410;
        --text-dim:  #6B6552;
    }

    /* Hide the sidebar completely (we use a top navbar) */
    section[data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }

    .stApp, [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(1100px 520px at 12% -8%, #FFF6DD 0%, transparent 60%),
            radial-gradient(900px 480px at 95% 0%, #EFF1F4 0%, transparent 55%),
            var(--bg) !important;
        color: var(--text) !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }

    .stApp, .stApp p, .stApp span, .stApp label, .stApp li, .stApp div,
    .stMarkdown, h1, h2, h3, h4, h5, h6,
    [data-testid="stWidgetLabel"] label, [data-testid="stMetricLabel"],
    [data-testid="stMetricValue"] { color: var(--text) !important; }
    .stApp small, [data-testid="stCaptionContainer"], .stCaption { color: var(--text-dim) !important; }

    /* ---------- Golden comet / tail border animation ---------- */
    @property --ang { syntax: '<angle>'; initial-value: 0deg; inherits: false; }
    @keyframes spinComet { to { --ang: 360deg; } }

    /* shared comet pseudo-element: a bright golden head with a fading tail
       circling the element's border */
    .comet-border { position: relative; }
    .comet-border::before {
        content: "";
        position: absolute; inset: -2px;
        border-radius: inherit;
        padding: 2px;
        background: conic-gradient(from var(--ang),
            rgba(201,162,39,0) 0deg,
            rgba(201,162,39,0) 250deg,
            rgba(230,199,102,0.65) 300deg,
            rgba(255,236,168,1) 340deg,
            #FFF6D0 352deg,
            rgba(201,162,39,0) 360deg);
        -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
        -webkit-mask-composite: xor; mask-composite: exclude;
        animation: spinComet 3.8s linear infinite;
        pointer-events: none;
        filter: drop-shadow(0 0 4px rgba(230,199,102,0.8));
    }

    /* ---------- Top brand ---------- */
    .msr-topbrand {
        display: flex; flex-direction: column; line-height: 1.05;
        padding: 0.15rem 0 0.25rem 0;
    }
    .msr-topbrand .brand {
        font-size: 1.55rem; font-weight: 900; letter-spacing: 1px;
        background: linear-gradient(90deg, var(--gold-deep), var(--gold), var(--gold-soft), var(--silver));
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .msr-topbrand .sub { font-size: 0.68rem; letter-spacing: 2px; color: var(--text-dim) !important; }
    .topbar-status { text-align: right; font-size: 0.82rem; color: var(--text-dim) !important; padding-top: 0.35rem; }
    .navbar-rule { border: none; border-top: 2px solid var(--border); margin: 0.5rem 0 1rem 0; }

    /* ---------- KPI cards (light, gold edge + comet) ---------- */
    .kpi-card {
        position: relative;
        background: linear-gradient(160deg, var(--panel) 0%, var(--panel-2) 100%);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1rem 1.25rem; height: 100%;
        box-shadow: 0 6px 16px -10px rgba(156,122,24,0.45);
        transition: transform .2s ease, box-shadow .2s ease;
    }
    .kpi-card::before {
        content: ""; position: absolute; inset: -2px; border-radius: 16px; padding: 2px;
        background: conic-gradient(from var(--ang),
            rgba(201,162,39,0) 0deg, rgba(201,162,39,0) 255deg,
            rgba(230,199,102,0.6) 305deg, rgba(255,236,168,1) 342deg,
            #FFF7D6 353deg, rgba(201,162,39,0) 360deg);
        -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
        -webkit-mask-composite: xor; mask-composite: exclude;
        animation: spinComet 5s linear infinite;
        filter: drop-shadow(0 0 3px rgba(230,199,102,0.7));
        pointer-events: none;
    }
    .kpi-card:hover { transform: translateY(-3px); box-shadow: 0 10px 26px -8px rgba(156,122,24,0.6); }
    .kpi-card .label { color: var(--text-dim) !important; font-size: 0.78rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 0.4rem; }
    .kpi-card .value { color: #1c1606 !important; font-size: 1.75rem; font-weight: 800; line-height: 1; }
    .kpi-card .delta { font-size: 0.82rem; color: var(--gold-deep) !important; margin-top: 0.35rem; }
    .kpi-card.accent { border-left: 3px solid var(--gold); }
    .kpi-card.accent .value {
        background: linear-gradient(90deg, var(--gold-deep), var(--gold)); -webkit-background-clip: text;
        background-clip: text; -webkit-text-fill-color: transparent; }

    /* ---------- Buttons: golden comet border ---------- */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
    [data-testid="stPopover"] button {
        position: relative;
        background: linear-gradient(135deg, #FFFDF5 0%, #F7EFD8 100%) !important;
        color: #2A2410 !important;
        border: 1px solid var(--gold) !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        overflow: hidden;
        transition: transform .15s ease, box-shadow .15s ease !important;
    }
    .stButton > button::before, .stDownloadButton > button::before,
    .stFormSubmitButton > button::before {
        content: ""; position: absolute; inset: -2px; border-radius: 12px; padding: 2px;
        background: conic-gradient(from var(--ang),
            rgba(201,162,39,0) 0deg, rgba(201,162,39,0) 250deg,
            rgba(230,199,102,0.7) 300deg, rgba(255,236,168,1) 340deg,
            #FFF6D0 352deg, rgba(201,162,39,0) 360deg);
        -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
        -webkit-mask-composite: xor; mask-composite: exclude;
        animation: spinComet 3.4s linear infinite;
        filter: drop-shadow(0 0 4px rgba(230,199,102,0.85));
        pointer-events: none;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 0 18px -2px rgba(230,199,102,0.85) !important;
    }
    /* Active (primary) nav tab + primary buttons: filled gold */
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--gold) 0%, var(--gold-soft) 100%) !important;
        color: #1c1606 !important; border-color: var(--gold-deep) !important;
        box-shadow: 0 0 20px -3px rgba(201,162,39,0.85) !important;
    }

    /* ---------- Textured nav tabs ---------- */
    .navbar-tabs { margin: 0.2rem 0 0.2rem 0; }
    .st-key-nav_loyalty button, .st-key-nav_rewards button {
        background: linear-gradient(135deg,#EAF4FA 0%,#D6E9F3 100%) !important;
        border-color: var(--diamond) !important; }
    .st-key-nav_ams button, .st-key-nav_stores button, .st-key-nav_settings button {
        background: linear-gradient(135deg,#F4F5F7 0%,#E2E6EB 100%) !important;
        border-color: var(--silver) !important; }
    .st-key-nav_renewals button, .st-key-nav_upload button {
        background: linear-gradient(135deg,#EEF0F3 0%,#DBE0E6 100%) !important;
        border-color: var(--platinum) !important; }

    /* ---------- Inputs ---------- */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    [data-baseweb="select"] > div, [data-baseweb="input"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        background-color: var(--panel) !important; color: var(--text) !important;
        border: 1px solid var(--border) !important; }
    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {
        background-color: var(--panel) !important; color: var(--text) !important; }
    [data-baseweb="tag"] { background-color: var(--gold) !important; color: #1c1606 !important; }

    /* ---------- Tabs / expander ---------- */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 2px solid var(--border); gap: 0.25rem; }
    .stTabs [data-baseweb="tab"] { color: var(--text-dim) !important; font-weight: 600; }
    .stTabs [aria-selected="true"] { color: var(--gold-deep) !important; }
    .stTabs [data-baseweb="tab-highlight"] { background-color: var(--gold) !important; }
    [data-testid="stExpander"] summary {
        background: var(--panel-2) !important; color: var(--text) !important;
        border: 1px solid var(--border) !important; border-radius: 10px !important; }

    /* ---------- Tables ---------- */
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        background: var(--panel) !important; border: 1px solid var(--border) !important;
        border-radius: 10px !important; }
    [data-testid="stDataFrame"] * { color: var(--text) !important; }
    .stApp table, .stApp .dataframe { background: var(--panel) !important; color: var(--text) !important; }
    .stApp table th, .stApp .dataframe th {
        background: linear-gradient(135deg,var(--gold) 0%,var(--gold-soft) 100%) !important;
        color: #1c1606 !important; border-color: var(--border) !important; }
    .stApp table td, .stApp .dataframe td { background: var(--panel) !important;
        color: var(--text) !important; border-color: #ECE6D2 !important; }
    .dataframe tbody tr:hover td { background: #FBF4DD !important; }

    /* Alerts */
    [data-testid="stAlert"] {
        background: var(--panel-2) !important; color: var(--text) !important;
        border: 1px solid var(--border) !important; border-radius: 10px !important; }
    [data-testid="stAlert"] * { color: var(--text) !important; }

    .spencer-header {
        position: relative; background: linear-gradient(90deg,#FFF7DD 0%, #F3EEDF 60%, #EAF0F4 100%);
        padding: 1rem 1.4rem; border-radius: 14px; margin-bottom: 1.1rem;
        border: 1px solid var(--border); box-shadow: 0 6px 18px -12px rgba(156,122,24,0.5); overflow: hidden; }
    .spencer-header h1 { margin: 0; font-size: 1.45rem; font-weight: 800; color: var(--gold-deep) !important; }
    .spencer-header .sub { color: var(--text-dim) !important; font-size: 0.9rem; margin-top: 0.2rem; }

    .block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 1500px; }

    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: var(--bg2); }
    ::-webkit-scrollbar-thumb { background: var(--gold-soft); border-radius: 6px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--gold); }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Inject CSS for the new tier-filter cards + Loyalty KPI page styling.
# Both helpers are idempotent within a single Streamlit run.
inject_tier_card_css()
inject_widget_key_selectors()


# ---------------------------------------------------------------------------
# DB init at first import
# ---------------------------------------------------------------------------
db.init_db()


# ---------------------------------------------------------------------------
# Cached fetchers (cache invalidated when underlying data changes)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cached_ams_report(version: str) -> pd.DataFrame:
    df = db.fetch_df("SELECT * FROM ams_report_cache")
    return df


@st.cache_data(show_spinner=False)
def cached_renewal_report(version: str) -> pd.DataFrame:
    return db.fetch_df("SELECT * FROM renewal_cache")


def report_version() -> str:
    """A cache-busting key based on last build time + row count."""
    return (
        f"{db.get_meta('report_built_at', 'never')}|"
        f"{db.row_count('ams_report_cache')}|"
        f"{db.row_count('renewal_cache')}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_int(n) -> str:
    if pd.isna(n):
        return "—"
    return f"{int(n):,}"


def fmt_inr(n, decimals: int = 0) -> str:
    if pd.isna(n):
        return "—"
    if decimals == 0:
        return f"₹{n:,.0f}"
    return f"₹{n:,.{decimals}f}"


def kpi_card(label: str, value: str, delta: str | None = None, accent: bool = False) -> str:
    accent_cls = " accent" if accent else ""
    delta_html = f'<div class="delta">{delta}</div>' if delta else ""
    return f"""
    <div class="kpi-card{accent_cls}">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {delta_html}
    </div>
    """


def header(title: str, subtitle: str = "") -> None:
    sub = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="spencer-header">
            <h1>🛒 Spencer's MSR Dashboard — {title}</h1>
            {sub}
        </div>
        """,
        unsafe_allow_html=True,
    )


def has_data() -> bool:
    return db.has_data("membership")


def current_period_label() -> str:
    return db.get_meta("current_period_label", "—") or "—"


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Gold / silver palette + chart & table styling helpers
# ---------------------------------------------------------------------------
GOLD = "#C9A227"
GOLD_SOFT = "#E6C766"
SILVER = "#9AA3AD"
SILVER_SOFT = "#C7CDD4"
PLATINUM = "#7E8B99"
DIAMOND = "#6FA8C7"
INK = "#2A2410"
CHART_SEQ = [GOLD, SILVER, "#B8862B", PLATINUM, GOLD_SOFT, DIAMOND, "#8A7320"]


def _style_plotly(fig, height: int = 340):
    """Light theme with gold/silver palette for inline charts."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, size=13),
        title=dict(font=dict(color=INK, size=15)),
        colorway=CHART_SEQ,
        margin=dict(l=10, r=10, t=44, b=10),
        height=height,
        xaxis=dict(gridcolor="#EAE2C8", linecolor="#D9CFB0", tickfont=dict(color=INK), tickangle=-25),
        yaxis=dict(gridcolor="#EAE2C8", linecolor="#D9CFB0", tickfont=dict(color=INK)),
        legend=dict(font=dict(color=INK)),
    )
    return fig


def _style_table(df: pd.DataFrame):
    """Return a pandas Styler with a gold header for small tables; for large
    tables fall back to the plain frame (themed globally via CSS) because the
    Styler has a hard cell-render cap and is slow on big data."""
    try:
        if df is None or df.empty or df.size > 60000:
            return df
        styler = (
            df.style
            .set_table_styles([
                {"selector": "th",
                 "props": [("background", f"linear-gradient(135deg,{GOLD} 0%,{GOLD_SOFT} 100%)"),
                           ("color", "#1c1606"), ("font-weight", "700"),
                           ("border-color", "#D9CFB0")]},
                {"selector": "td", "props": [("border-color", "#ECE6D2")]},
            ])
            .set_properties(**{"background-color": "#FFFDF6", "color": INK})
        )
        return styler
    except Exception:
        return df


def _event_points(event):
    """Extract clicked points from a st.plotly_chart on_select event."""
    try:
        sel = getattr(event, "selection", None) or event.get("selection", {})
        return sel.get("points", []) if sel else []
    except Exception:
        return []


_EXPORT_COLS = [
    "msr_number", "customer_name", "plan_tier", "enrollment_status",
    "store_code", "store_name", "region", "city",
    "enroll_month_label", "expiry_month_label", "expiry_date_str",
    "renewal_window_str", "renewal_state",
    "shopped_current_month", "bill_value",
    "mtd_cashback_earned", "mtd_cashback_earned_liq", "mtd_redemption",
]


def _offer_segment_csv(rows: pd.DataFrame, fname: str, key: str, note: str):
    """Render an info strip + download button for a clicked chart segment."""
    if rows is None or rows.empty:
        return
    cols = [c for c in _EXPORT_COLS if c in rows.columns]
    out = rows[cols] if cols else rows
    st.info(f"🔎 Selected: **{note}** — {len(out):,} records ready to export.")
    st.download_button(
        f"⬇️ Download selected segment ({len(out):,} rows)",
        data=df_to_csv_bytes(out),
        file_name=fname, mime="text/csv", key=key)


def _segment_download_from_event(event, ams_df, ne_module, field, label, key_prefix):
    """Pipeline-bar click -> download the member rows for that expiry cohort."""
    pts = _event_points(event)
    if not pts:
        st.caption("💡 Click a bar above to download that cohort's members.")
        return
    val = pts[0].get("x") or pts[0].get("label")
    if val is None:
        return
    members = ne_module.build_near_expiry(ams_df, "All months")
    rows = members[members[field] == val]
    _offer_segment_csv(
        rows, f"{label}_{str(val).replace('-','')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        key=f"{key_prefix}_dl", note=f"{label} = {val}")


def _behaviour_segment_download(event, ne_df, ne_module, key_prefix):
    """Pie-slice click -> download Shopped / Not-Shopped members."""
    pts = _event_points(event)
    if not pts:
        st.caption("💡 Click a slice above to download just that segment.")
        return
    lbl = pts[0].get("label")
    if lbl is None:
        return
    val = "Yes" if lbl == "Shopped" else "No"
    rows = ne_df[ne_df["shopped_current_month"] == val]
    _offer_segment_csv(
        rows, f"behaviour_{lbl.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        key=f"{key_prefix}_dl", note=lbl)


# ---------------------------------------------------------------------------
# Top navigation bar  (login + textured tabs)
# ---------------------------------------------------------------------------
def _sidebar_logo_html() -> str:
    """Return HTML for the sidebar brand block.

    Looks for ``assets/msr_logo.<png|jpg|jpeg|svg>`` first; if present it is
    inlined as a data-URI so Streamlit doesn't need to serve a static path.
    Falls back to a clean text brand block when no file is supplied.
    """
    assets_dir = Path(__file__).parent / "assets"
    for ext, mime in (("png", "image/png"), ("jpg", "image/jpeg"),
                      ("jpeg", "image/jpeg"), ("svg", "image/svg+xml")):
        logo_path = assets_dir / f"msr_logo.{ext}"
        if logo_path.exists():
            try:
                raw = logo_path.read_bytes()
                if ext == "svg":
                    # SVG can be embedded directly without base64
                    data = raw.decode("utf-8", errors="ignore")
                    return (
                        f'<div class="msr-logo-wrap" title="MSR Loyalty Analytics">'
                        f'{data}</div>'
                    )
                b64 = base64.b64encode(raw).decode("ascii")
                return (
                    f'<div class="msr-logo-wrap" title="MSR Loyalty Analytics">'
                    f'<img src="data:{mime};base64,{b64}" alt="MSR" /></div>'
                )
            except Exception:
                continue
    # Fallback: clean text brand block
    return (
        '<div class="msr-logo-fallback" title="MSR Loyalty Analytics">'
        '<div class="brand">MSR</div>'
        '<div class="sub">Loyalty Analytics</div>'
        '</div>'
    )


def _navbar_logo_html() -> str:
    return (
        '<div class="msr-topbrand">'
        '<span class="brand">SPENCER\'S</span>'
        '<span class="sub">MSR LOYALTY ANALYTICS</span>'
        '</div>'
    )


NAV_ITEMS = [
    ("nav_overview",   "📊 Overview",              "Overview",              "gold"),
    ("nav_loyalty",    "💎 Loyalty KPI",           "Loyalty KPI",           "diamond"),
    ("nav_ams",        "📋 AMS Migration Report",  "AMS Migration Report",  "silver"),
    ("nav_renewals",   "🔁 Renewals",              "Renewals",              "platinum"),
    ("nav_nearexp",    "⏳ Near Expiry",           "Near Expiry",           "gold"),
    ("nav_rewards",    "🎯 Rewards Intelligence",  "Rewards Intelligence",  "diamond"),
    ("nav_stores",     "🏬 Store Master",          "Store Master",          "silver"),
]
ADMIN_NAV = [
    ("nav_upload",     "⬆️ Upload Data",           "Upload Data",           "platinum"),
    ("nav_settings",   "⚙️ Settings",              "Settings",              "silver"),
]


def render_navbar() -> str:
    """Top navigation bar: brand + textured tab buttons + admin controls."""
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "Overview"

    items = list(NAV_ITEMS)
    if auth.is_admin():
        items += ADMIN_NAV

    # ---- Brand + status + admin login row ----
    top_l, top_r = st.columns([3, 2])
    with top_l:
        st.markdown(_navbar_logo_html(), unsafe_allow_html=True)
    with top_r:
        bits = [f"Data period: **{current_period_label()}**"]
        if has_data():
            bits.append(f"Members: {db.row_count('membership'):,}")
        st.markdown(
            f'<div class="topbar-status">{" &nbsp;·&nbsp; ".join(bits)}</div>',
            unsafe_allow_html=True,
        )
        if auth.is_admin():
            cA, cB = st.columns([2, 1])
            cA.markdown(f'<div class="topbar-status">👤 <b>{auth.current_user()}</b> (Admin)</div>',
                        unsafe_allow_html=True)
            if cB.button("🚪 Log out", key="nav_logout", use_container_width=True):
                auth.logout(); st.rerun()
        else:
            with st.popover("🔐 Admin login", use_container_width=True):
                u = st.text_input("Username", key="login_user")
                p = st.text_input("Password", type="password", key="login_pass")
                if st.button("Sign in", key="login_btn", use_container_width=True):
                    if auth.login(u, p):
                        st.rerun()
                    else:
                        st.error("Invalid credentials")

    # ---- Tab buttons ----
    st.markdown('<div class="navbar-tabs">', unsafe_allow_html=True)
    cols = st.columns(len(items))
    for col, (key, label, page, _texture) in zip(cols, items):
        is_active = st.session_state["nav_page"] == page
        with col:
            if st.button(label, key=key, use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state["nav_page"] = page
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ---- Active tier filter strip ----
    active_tier = get_selected_tier()
    if active_tier:
        tcol1, tcol2 = st.columns([4, 1])
        tcol1.markdown(
            f'<div class="tier-active-banner">🎯 Tier filter: <strong>{active_tier}</strong></div>',
            unsafe_allow_html=True)
        if tcol2.button("✕ Clear tier", key="nav_clear_tier", use_container_width=True):
            from util_filters import set_selected_tier
            set_selected_tier(None)
            st.rerun()

    st.markdown('<hr class="navbar-rule"/>', unsafe_allow_html=True)
    return st.session_state["nav_page"]


# ---------------------------------------------------------------------------
# Page: Overview
# ---------------------------------------------------------------------------
def page_overview():
    header(
        "Overview",
        f"Loyalty programme performance snapshot · current period {current_period_label()}",
    )

    if not has_data():
        st.info("No data has been uploaded yet. An admin can upload files via the **Upload Data** menu.")
        return

    df = cached_ams_report(report_version())
    if df.empty:
        st.warning("Report cache is empty. Trigger a rebuild from the Upload page.")
        return

    # ----- KPI row -------------------------------------------------------
    total_customers = len(df)
    shopped = (df["shopper_behaviour"] == "Shopped").sum()
    shopped_pct = (shopped / total_customers * 100) if total_customers else 0
    bill_value = df["bill_value"].sum()
    eligible = df["eligible_bill_value"].sum()
    mtd_cb = df["mtd_cashback_earned"].sum()
    mtd_re = df["mtd_redemption"].sum()
    ytd_cb = df["ytd_cashback_earned"].sum()
    ytd_re = df["ytd_redemption"].sum()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Enrolled Customers", fmt_int(total_customers), accent=True), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Shopped This Month", fmt_int(shopped), f"{shopped_pct:.1f}% of base"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("MTD Bill Value", fmt_inr(bill_value)), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("MTD Eligible Bill", fmt_inr(eligible)), unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.markdown(kpi_card("MTD Cashback Earned", fmt_inr(mtd_cb)), unsafe_allow_html=True)
    with c6:
        st.markdown(kpi_card("MTD Redemption", fmt_inr(mtd_re)), unsafe_allow_html=True)
    with c7:
        st.markdown(kpi_card("YTD Cashback Earned", fmt_inr(ytd_cb), accent=True), unsafe_allow_html=True)
    with c8:
        st.markdown(kpi_card("YTD Redemption", fmt_inr(ytd_re), accent=True), unsafe_allow_html=True)

    st.markdown("&nbsp;")

    # ----- Tier filter cards (clickable, sync across pages) -------------
    # Cards always show the full tier breakdown of the *non-tier-filtered*
    # dataset so the user can see what each tier looks like before clicking
    # in. The click sets st.session_state["msr_selected_tier"] which then
    # gates everything below.
    st.markdown("### Tier filter")
    render_tier_filter_cards(df, key_prefix="ovr")

    st.markdown("&nbsp;")

    # ----- Filters (Plan Tier removed — handled by clickable cards above) --
    with st.expander("Filters", expanded=False):
        f1, f2, f3 = st.columns(3)
        regions = sorted([r for r in df["region"].dropna().unique() if r])
        formats = sorted([f for f in df["format"].dropna().unique() if f])
        clusters = sorted([c for c in df["cluster"].dropna().unique() if c])
        sel_regions = f1.multiselect("Region", regions, default=regions)
        sel_formats = f2.multiselect("Format", formats, default=formats)
        sel_clusters = f3.multiselect("Cluster", clusters, default=clusters)

    fdf = df[
        df["region"].isin(sel_regions)
        & df["format"].isin(sel_formats)
        & df["cluster"].isin(sel_clusters)
    ]
    # Apply the globally-selected tier (None = all tiers).
    fdf = apply_tier_filter(fdf)

    if fdf.empty:
        st.warning("No customers match the selected filters.")
        return

    # ----- Charts row 1: enrollment + shopper behaviour ------------------
    g1, g2 = st.columns([2, 1])
    with g1:
        enroll_trend = (
            fdf.groupby("enroll_month_label")
            .size()
            .reset_index(name="customers")
        )
        # sort by actual date
        enroll_trend["sort_key"] = pd.to_datetime(enroll_trend["enroll_month_label"], format="%b-%y", errors="coerce")
        enroll_trend = enroll_trend.sort_values("sort_key")
        fig = px.bar(
            enroll_trend, x="enroll_month_label", y="customers",
            title="Enrolment trend by month",
            labels={"enroll_month_label": "Month", "customers": "Enrolments"},
        )
        fig.update_traces(marker_color=GOLD)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with g2:
        beh = fdf["shopper_behaviour"].value_counts().reset_index()
        beh.columns = ["Behaviour", "Count"]
        fig = px.pie(
            beh, names="Behaviour", values="Count",
            title="Shopper behaviour",
            color="Behaviour",
            color_discrete_map={"Shopped": GOLD, "Not Shopped": SILVER},
            hole=0.45,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)

    # ----- Charts row 2: store leaderboard + channel ---------------------
    g3, g4 = st.columns([2, 1])
    with g3:
        store_lb = (
            fdf.groupby(["store_code", "store_name"])
            .agg(customers=("msr_number", "count"),
                 bill=("bill_value", "sum"))
            .reset_index()
            .sort_values("customers", ascending=False)
            .head(15)
        )
        store_lb["label"] = store_lb["store_code"] + " · " + store_lb["store_name"].fillna("")
        fig = px.bar(
            store_lb.sort_values("customers"),
            x="customers", y="label", orientation="h",
            title="Top 15 stores by enrolment",
            labels={"label": "Store", "customers": "Enrolments"},
            hover_data={"bill": ":,.0f"},
        )
        fig.update_traces(marker_color=GOLD)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=480)
        st.plotly_chart(fig, use_container_width=True)

    with g4:
        ch = fdf["channel"].fillna("Unknown").replace("", "Unknown").value_counts().reset_index()
        ch.columns = ["Channel", "Count"]
        fig = px.pie(
            ch, names="Channel", values="Count",
            title="Channel of enrolment",
            color_discrete_sequence=[GOLD, SILVER, PLATINUM, DIAMOND],
            hole=0.45,
        )
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=480)
        st.plotly_chart(fig, use_container_width=True)

    # ----- Charts row 3: bill slabs + AMS slab migration ----------------
    g5, g6 = st.columns(2)
    with g5:
        bs_order = ["<=25K", ">25K_<50K", ">50K_<75K", ">75K_<1L", ">1L"]
        bs = fdf["bill_slab"].value_counts().reindex(bs_order, fill_value=0).reset_index()
        bs.columns = ["Slab", "Customers"]
        fig = px.bar(bs, x="Slab", y="Customers", title="Bill-value slab distribution")
        fig.update_traces(marker_color=GOLD)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=340)
        st.plotly_chart(fig, use_container_width=True)

    with g6:
        ams_order = [s[0] for s in AMS_SLABS] + ["No Data"]
        past_ams = fdf["past_ams_slab"].value_counts().reindex(ams_order, fill_value=0).reset_index()
        past_ams.columns = ["Slab", "Customers"]
        fig = px.bar(past_ams, x="Slab", y="Customers", title="Past AMS slab distribution")
        fig.update_traces(marker_color="#1F1F2E")
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=340, xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)

    # ----- Charts row 4: cashback by region + sales delta -------------
    g7, g8 = st.columns(2)
    with g7:
        reg = (
            fdf.groupby("region")
            .agg(mtd_cashback=("mtd_cashback_earned", "sum"),
                 mtd_redemption=("mtd_redemption", "sum"),
                 ytd_cashback=("ytd_cashback_earned", "sum"),
                 ytd_redemption=("ytd_redemption", "sum"))
            .reset_index()
        )
        reg_long = reg.melt(id_vars="region", var_name="Metric", value_name="Amount")
        fig = px.bar(reg_long, x="region", y="Amount", color="Metric",
                     barmode="group", title="Cashback & redemption by region",
                     color_discrete_sequence=[GOLD, GOLD_SOFT, SILVER, PLATINUM])
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380)
        st.plotly_chart(fig, use_container_width=True)

    with g8:
        delta = pd.DataFrame({
            "Metric": ["Incremental Sales", "Lost Sales"],
            "Value": [fdf["incremental_sales"].sum(), fdf["lost_sales"].sum()],
        })
        fig = px.bar(delta, x="Metric", y="Value",
                     title="Incremental vs Lost Sales (current month)",
                     color="Metric",
                     color_discrete_map={"Incremental Sales": GOLD, "Lost Sales": SILVER},
                     text_auto=".2s")
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # ----- Diamond Liquor section ---------------------------------------
    render_diamond_liquor_section(fdf)


def render_diamond_liquor_section(fdf: pd.DataFrame) -> None:
    """Liquor purchase + redemption snapshot for Diamond members."""
    st.markdown("---")
    st.markdown(
        '<div style="position:relative;background:linear-gradient(100deg,#FFF7DD 0%,#F3EEDF 55%,#EAF0F4 100%);'
        'padding:0.85rem 1.25rem;border-radius:12px;color:#2A2410;margin-bottom:1rem;'
        'border:1px solid #E4DBC2;box-shadow:0 6px 18px -12px rgba(156,122,24,0.5);">'
        '<span style="font-size:1.15rem;font-weight:800;color:#9C7A18;">🥂 Diamond Liquor — Purchase &amp; Redemption</span>'
        '<div style="color:#6B6552;font-size:0.85rem;margin-top:0.25rem;">'
        'Liquor cashback &amp; redemption are exclusive to Diamond members. '
        '&quot;Existing Liq Buyer&quot; = found in the 1-year liquor-buyers base; otherwise &quot;New Liq Buyer&quot;.'
        '</div></div>',
        unsafe_allow_html=True,
    )

    diam = fdf[fdf["plan_tier"] == "Diamond"].copy()
    if diam.empty:
        st.info("No Diamond members in the current filter selection.")
        return

    n_diamond = len(diam)
    existing_liq = (diam["liq_buyer_type"] == "Existing Liq Buyer").sum()
    new_liq = (diam["liq_buyer_type"] == "New Liq Buyer").sum()
    liq_sales = diam.get("liq_gross_sales", pd.Series(dtype=float)).sum()
    liq_nob = diam.get("liq_nob", pd.Series(dtype=float)).sum()
    liq_cb_mtd = diam.get("mtd_cashback_earned_liq", pd.Series(dtype=float)).sum()
    liq_cb_ytd = diam.get("ytd_cashback_earned_liq", pd.Series(dtype=float)).sum()
    liq_re_mtd = diam.get("mtd_redemption_liq", pd.Series(dtype=float)).sum()
    liq_re_ytd = diam.get("ytd_redemption_liq", pd.Series(dtype=float)).sum()
    liq_buyers_with_sales = (diam.get("liq_gross_sales", 0) > 0).sum()

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.markdown(kpi_card("Diamond Members", fmt_int(n_diamond), accent=True), unsafe_allow_html=True)
    with d2:
        st.markdown(kpi_card("Existing Liq Buyers", fmt_int(existing_liq),
                             f"{existing_liq/n_diamond*100:.0f}% of Diamond"), unsafe_allow_html=True)
    with d3:
        st.markdown(kpi_card("New Liq Buyers", fmt_int(new_liq),
                             f"{new_liq/n_diamond*100:.0f}% of Diamond"), unsafe_allow_html=True)
    with d4:
        st.markdown(kpi_card("Bought Liquor (this month)", fmt_int(liq_buyers_with_sales)), unsafe_allow_html=True)

    d5, d6, d7, d8 = st.columns(4)
    with d5:
        st.markdown(kpi_card("Liq Gross Sales (MTD)", fmt_inr(liq_sales)), unsafe_allow_html=True)
    with d6:
        st.markdown(kpi_card("Liq Cashback Earned (MTD)", fmt_inr(liq_cb_mtd)), unsafe_allow_html=True)
    with d7:
        st.markdown(kpi_card("Liq Cashback Earned (YTD)", fmt_inr(liq_cb_ytd), accent=True), unsafe_allow_html=True)
    with d8:
        st.markdown(kpi_card("Liq Redemption (YTD)", fmt_inr(liq_re_ytd), accent=True), unsafe_allow_html=True)

    gA, gB = st.columns([1, 1])
    with gA:
        split = pd.DataFrame({
            "Type": ["Existing Liq Buyer", "New Liq Buyer"],
            "Count": [existing_liq, new_liq],
        })
        fig = px.pie(split, names="Type", values="Count",
                     title="Diamond members — existing vs new liquor buyers",
                     color="Type",
                     color_discrete_map={"Existing Liq Buyer": GOLD,
                                         "New Liq Buyer": SILVER},
                     hole=0.45)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with gB:
        liq_flow = pd.DataFrame({
            "Metric": ["Cashback MTD", "Cashback YTD", "Redemption MTD", "Redemption YTD"],
            "Amount": [liq_cb_mtd, liq_cb_ytd, liq_re_mtd, liq_re_ytd],
        })
        fig = px.bar(liq_flow, x="Metric", y="Amount",
                     title="Liquor cashback & redemption (Diamond)",
                     text_auto=".2s",
                     color="Metric",
                     color_discrete_sequence=[GOLD, GOLD_SOFT, SILVER, PLATINUM])
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=320, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Diamond liquor buyers table
    with st.expander("View Diamond liquor-buyer detail", expanded=False):
        cols = ["msr_number", "customer_name", "store_code", "region", "city",
                "liq_buyer_type", "liq_gross_sales", "liq_nob", "liq_qty",
                "mtd_cashback_earned_liq", "ytd_cashback_earned_liq",
                "mtd_redemption_liq", "ytd_redemption_liq"]
        cols = [c for c in cols if c in diam.columns]
        dt = diam[cols].rename(columns={
            "msr_number": "Mobile", "customer_name": "Name", "store_code": "Store",
            "region": "Region", "city": "City", "liq_buyer_type": "Liq Buyer Type",
            "liq_gross_sales": "Liq Sales (MTD)", "liq_nob": "Liq NOB", "liq_qty": "Liq Qty",
            "mtd_cashback_earned_liq": "Liq Cashback MTD",
            "ytd_cashback_earned_liq": "Liq Cashback YTD",
            "mtd_redemption_liq": "Liq Redemption MTD",
            "ytd_redemption_liq": "Liq Redemption YTD",
        })
        st.dataframe(dt.sort_values("Liq Cashback YTD", ascending=False),
                     use_container_width=True, hide_index=True, height=360)
        st.download_button(
            "⬇️ Download Diamond liquor detail CSV",
            data=df_to_csv_bytes(dt),
            file_name=f"diamond_liquor_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Page: AMS Migration Report (the big table)
# ---------------------------------------------------------------------------
def page_ams_report():
    header(
        "AMS Migration Report",
        "Customer-level KPI table · download as CSV for further analysis",
    )

    if not has_data():
        st.info("No data has been uploaded yet.")
        return

    df = cached_ams_report(report_version())
    if df.empty:
        st.warning("Report cache is empty.")
        return

    # ----- Filters -------------------------------------------------------
    with st.expander("Filters", expanded=False):
        f1, f2, f3 = st.columns(3)
        regions = sorted([r for r in df["region"].dropna().unique() if r])
        clusters = sorted([c for c in df["cluster"].dropna().unique() if c])
        formats = sorted([f for f in df["format"].dropna().unique() if f])
        sel_regions = f1.multiselect("Region", regions, default=regions)
        sel_clusters = f2.multiselect("Cluster", clusters, default=clusters)
        sel_formats = f3.multiselect("Format", formats, default=formats)

        f4, f5, f6 = st.columns(3)
        store_options = sorted(df["store_code"].dropna().unique().tolist())
        sel_stores = f4.multiselect("Store Code", store_options, default=[])

        months = (
            df.dropna(subset=["enroll_month"])
            .drop_duplicates("enroll_month")
            .sort_values("enroll_month")[["enroll_month", "enroll_month_label"]]
        )
        month_options = months["enroll_month_label"].tolist()
        sel_months = f5.multiselect("Enrolment Month", month_options, default=month_options)

        beh_options = ["Shopped", "Not Shopped"]
        sel_beh = f6.multiselect("Shopper Behaviour", beh_options, default=beh_options)

    fdf = df[
        df["region"].isin(sel_regions)
        & df["cluster"].isin(sel_clusters)
        & df["format"].isin(sel_formats)
        & df["enroll_month_label"].isin(sel_months)
        & df["shopper_behaviour"].isin(sel_beh)
    ]
    if sel_stores:
        fdf = fdf[fdf["store_code"].isin(sel_stores)]

    # Global tier filter (driven by tier cards on Overview / Loyalty KPI)
    fdf = apply_tier_filter(fdf)

    active_tier = get_selected_tier()
    if active_tier:
        st.caption(
            f"Showing **{len(fdf):,}** of {len(df):,} rows · "
            f"tier filter active: **{active_tier}**"
        )
    else:
        st.caption(f"Showing **{len(fdf):,}** of {len(df):,} rows.")

    # ----- Build display frame ------------------------------------------
    fdf = fdf.sort_values("start_date", ascending=True)
    show = processing.format_for_display(fdf)
    # Numeric rounding + date formatting are handled inside format_for_display,
    # which also emits the columns in the analyst's required template order.

    st.dataframe(show, use_container_width=True, hide_index=True, height=560)

    # ----- Download ------------------------------------------------------
    st.download_button(
        "⬇️ Download filtered CSV",
        data=df_to_csv_bytes(show),
        file_name=f"ams_migration_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=False,
    )

    # ----- AMS Slab Transition Matrix (waterfall view) -------------------
    st.markdown("---")
    st.markdown("### AMS Slab Transition Matrix")
    st.caption(
        "How customers moved between the Past 6-month average AMS slab (rows) and "
        "the current month AMS slab (columns). "
        "🟦 Blue = stayed in the same slab · 🟩 Green = upgraded to a higher slab · "
        "🟧 Orange = downgraded to a lower slab."
    )

    slab_order = [s[0] for s in AMS_SLABS]   # 14 ordered slabs

    # Use the filtered frame so region/cluster/store filters apply here too.
    if "past_ams_slab" in fdf.columns and "current_ams_slab" in fdf.columns and not fdf.empty:
        # Drop rows missing either past or current slab — they're not useful for
        # a transition view and the user doesn't want a "No Data" bucket.
        slab_known = fdf["past_ams_slab"].isin(slab_order) & fdf["current_ams_slab"].isin(slab_order)
        tx_df = fdf.loc[slab_known].copy()

        if tx_df.empty:
            st.info(
                "No customers in the current filter have both a past 6-month AMS slab "
                "and a current AMS slab — the transition matrix is empty."
            )
        else:
            pivot = pd.crosstab(
                tx_df["past_ams_slab"],
                tx_df["current_ams_slab"],
                margins=True,
                margins_name="Grand Total",
            )

            # Reindex strictly to known slab order + Grand Total at the end.
            def _ordered_axis(values):
                ordered = [s for s in slab_order if s in values]
                if "Grand Total" in values:
                    ordered.append("Grand Total")
                return ordered

            pivot = pivot.reindex(
                index=_ordered_axis(pivot.index.tolist()),
                columns=_ordered_axis(pivot.columns.tolist()),
                fill_value=0,
            )
            pivot.index.name = "Past 6M AMS Slab"
            pivot.columns.name = "Current AMS Slab"

            def _color_cells(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for r in df.index:
                    for c in df.columns:
                        if r == "Grand Total" or c == "Grand Total":
                            styles.loc[r, c] = (
                                "background-color: #1F1F2E; color: white; font-weight: 700;"
                            )
                        elif r in slab_order and c in slab_order:
                            ri = slab_order.index(r)
                            ci = slab_order.index(c)
                            if ri == ci:
                                styles.loc[r, c] = (
                                    "background-color: #4FC3F7; color: white; font-weight: 600;"
                                )
                            elif ci > ri:
                                styles.loc[r, c] = (
                                    "background-color: #66BB6A; color: white;"
                                )
                            else:
                                styles.loc[r, c] = (
                                    "background-color: #F5A623; color: white;"
                                )
                return styles

            styled = pivot.style.apply(_color_cells, axis=None).format("{:,.0f}")
            st.dataframe(styled, use_container_width=True, height=560)

            # Quick movement summary (Grand Total excluded)
            body = pivot.drop(index=["Grand Total"], errors="ignore").drop(columns=["Grand Total"], errors="ignore")
            upgraded = downgraded = stayed = 0
            for r in body.index:
                for c in body.columns:
                    if r in slab_order and c in slab_order:
                        val = int(body.loc[r, c])
                        ri = slab_order.index(r)
                        ci = slab_order.index(c)
                        if ri == ci:
                            stayed += val
                        elif ci > ri:
                            upgraded += val
                        else:
                            downgraded += val
            total = upgraded + downgraded + stayed
            if total:
                c1, c2, c3 = st.columns(3)
                c1.markdown(
                    kpi_card("Upgraded", fmt_int(upgraded), f"{upgraded/total*100:.1f}% of base"),
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    kpi_card("Stayed Same", fmt_int(stayed), f"{stayed/total*100:.1f}% of base"),
                    unsafe_allow_html=True,
                )
                c3.markdown(
                    kpi_card("Downgraded", fmt_int(downgraded), f"{downgraded/total*100:.1f}% of base"),
                    unsafe_allow_html=True,
                )

            st.download_button(
                "⬇️ Download transition matrix CSV",
                data=df_to_csv_bytes(pivot.reset_index()),
                file_name=f"ams_slab_transition_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )


# ---------------------------------------------------------------------------
# Page: Renewals
# ---------------------------------------------------------------------------
def page_renewals():
    header(
        "Renewals & New Acquisition",
        "Store-wise · month-wise renewal performance",
    )

    if not has_data():
        st.info("No data has been uploaded yet.")
        return

    df = cached_renewal_report(report_version())
    if df.empty:
        st.warning("Renewal cache is empty.")
        return

    # Honour the global tier filter — the renewals cache is store-month
    # aggregated and carries per-tier counts as columns (gold_renewals,
    # platinum_renewals, diamond_renewals), so a tier filter narrows the
    # "Total Renewals" KPI to the selected tier's column.
    active_tier = get_selected_tier()
    tier_col_map = {
        "Gold": "gold_renewals",
        "Platinum": "platinum_renewals",
        "Diamond": "diamond_renewals",
    }

    # KPI row
    total_new = int(df["new_acquisitions"].sum())
    if active_tier and tier_col_map[active_tier] in df.columns:
        total_ren = int(df[tier_col_map[active_tier]].sum())
        ren_label = f"{active_tier} Renewals"
    else:
        total_ren = int(df["renewals"].sum())
        ren_label = "Total Renewals"
    total_eu = int(df["existing_upgrades"].sum()) if "existing_upgrades" in df.columns else 0
    total_fe = int(df["force_upgrades"].sum()) if "force_upgrades" in df.columns else 0

    # ----- Bounded overall renewal % ------------------------------------
    # Only months that have already occurred (period <= current data period)
    # count toward the headline %, so early renewals of future-dated terms
    # don't push it past 100%. Early (future-month) renewals are shown
    # separately.
    cur_period = pd.to_datetime(db.get_meta("current_period", None), errors="coerce")
    pser = pd.to_datetime(df["period"], errors="coerce")
    if pd.notna(cur_period):
        occurred = pser <= (cur_period + pd.offsets.MonthEnd(0))
    else:
        occurred = pd.Series(True, index=df.index)

    occ_df = df[occurred]
    total_prev = int(occ_df["previously_registered"].sum())
    matured_ren = int(occ_df["renewals"].sum())
    early_ren = int(df.loc[~occurred, "renewals"].sum())
    overall_pct = (matured_ren / total_prev * 100) if total_prev else 0.0

    # ----- Registration-status cards (N / R / EU / FE) ------------------
    st.markdown("### Registration activity")
    st.caption(
        "Driven by the membership file's **Registration Type** column and the "
        "member's enrolment history. **N** = New Acquisition (bucketed by the "
        "**original** enrolment month, *not* the transaction date) · **R** = "
        "Renewal (a later membership term, bucketed by the month the old term "
        "came up for renewal) · **EU** = Existing Upgrade (tier raised, validity "
        "unchanged) · **FE** = Force Upgrade (mid-term upgrade, fresh validity)."
    )
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        st.markdown(kpi_card("🆕 New Acquisition", fmt_int(total_new), accent=True), unsafe_allow_html=True)
    with sc2:
        st.markdown(kpi_card("🔁 Renewal", fmt_int(total_ren)), unsafe_allow_html=True)
    with sc3:
        st.markdown(kpi_card("⬆️ Existing Upgrade", fmt_int(total_eu)), unsafe_allow_html=True)
    with sc4:
        st.markdown(kpi_card("⚡ Force Upgrade", fmt_int(total_fe)), unsafe_allow_html=True)

    st.markdown("&nbsp;")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card(ren_label, fmt_int(total_ren), accent=True), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Memberships Due (Expired)", fmt_int(total_prev),
                             delta="Terms that have come up for renewal so far"),
                    unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Overall Renewal %", f"{overall_pct:.1f}%",
                             delta="Matured renewals ÷ memberships due"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Early Renewals", fmt_int(early_ren),
                             delta="Future-dated terms renewed ahead of expiry"),
                    unsafe_allow_html=True)

    if active_tier:
        st.caption(f"🎯 Tier filter active: showing renewals for **{active_tier}** members only.")

    if total_prev == 0:
        st.info("ℹ️ No 1-year memberships have come up for renewal yet, so the renewal % covers only the few short/early terms. The first big renewal wave appears once the July-2025 cohort's 12-month plans reach their End Date.")

    st.markdown("&nbsp;")

    # Filters
    with st.expander("Filters", expanded=False):
        f1, f2 = st.columns(2)
        regions = sorted([r for r in df["region"].dropna().unique() if r])
        sel_regions = f1.multiselect("Region", regions, default=regions)
        store_opts = sorted(df["store_code"].dropna().unique().tolist())
        sel_stores = f2.multiselect("Store Code", store_opts, default=[])

    fdf = df[df["region"].isin(sel_regions)]
    if sel_stores:
        fdf = fdf[fdf["store_code"].isin(sel_stores)]
    if fdf.empty:
        st.warning("No rows match the selected filters.")
        return

    # Charts
    g1, g2 = st.columns(2)
    with g1:
        trend = (
            fdf.groupby(["period", "period_label"])
            .agg(new=("new_acquisitions", "sum"), renewals=("renewals", "sum"),
                 eu=("existing_upgrades", "sum"), fe=("force_upgrades", "sum"))
            .reset_index()
            .sort_values("period")
        )
        fig = go.Figure()
        fig.add_bar(x=trend["period_label"], y=trend["new"], name="New Acquisitions", marker_color=GOLD)
        fig.add_bar(x=trend["period_label"], y=trend["renewals"], name="Renewals", marker_color="#1F1F2E")
        fig.add_bar(x=trend["period_label"], y=trend["eu"], name="Existing Upgrade", marker_color=SILVER)
        fig.add_bar(x=trend["period_label"], y=trend["fe"], name="Force Upgrade", marker_color="#4FC3F7")
        fig.update_layout(
            barmode="group", title="Acquisitions vs renewals by month",
            margin=dict(l=10, r=10, t=40, b=10), height=380,
        )
        st.plotly_chart(fig, use_container_width=True)

    with g2:
        tier = pd.DataFrame({
            "Tier": ["Gold", "Platinum", "Diamond"],
            "Renewals": [int(fdf["gold_renewals"].sum()),
                         int(fdf["platinum_renewals"].sum()),
                         int(fdf["diamond_renewals"].sum())],
        })
        fig = px.bar(tier, x="Tier", y="Renewals", title="Renewals by plan tier",
                     color="Tier",
                     color_discrete_map={"Gold": "#D4AF37", "Platinum": "#1F1F2E", "Diamond": "#A6AAB1"})
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=380, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Store · month renewal table")
    show = renewal.format_renewal_for_display(fdf)
    # Type-friendly rounding
    if "Renewal %" in show.columns:
        show["Renewal %"] = pd.to_numeric(show["Renewal %"], errors="coerce").round(2)
    st.dataframe(show, use_container_width=True, hide_index=True, height=520)

    st.download_button(
        "⬇️ Download renewals CSV",
        data=df_to_csv_bytes(show),
        file_name=f"renewals_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Page: Near Expiry
# ---------------------------------------------------------------------------
def page_near_expiry():
    import near_expiry

    header(
        "Near Expiry & Upcoming Renewals",
        "Cohort expiry (enrolment month + 11) · 30-day renewal window · renewals deducted as they happen",
    )

    if not has_data():
        st.info("No data has been uploaded yet.")
        return

    df = cached_ams_report(report_version())
    if df.empty:
        st.warning("Report cache is empty. Trigger a rebuild from the Upload page.")
        return

    months = near_expiry.expiry_months(df)
    if not months:
        st.warning("No enrolment data found to compute expiries.")
        return

    cur_period = pd.to_datetime(db.get_meta("current_period", None), errors="coerce")
    if pd.isna(cur_period):
        cur_period = pd.Timestamp.today().normalize()

    st.caption(
        "Memberships are 12-month plans. Expiry is taken from the **enrolment "
        "month**: Jul-25 → **Jun-26**, Aug-25 → **Jul-26**, and so on for the "
        "whole base. A 30-day renewal window opens before each expiry date, and "
        "members who have already renewed are **deducted** from the pending count."
    )

    tab_pipe, tab_members = st.tabs(["🔁 Upcoming Renewal Pipeline", "👥 Expiring Members"])

    # ===================== Upcoming Renewal Pipeline =====================
    with tab_pipe:
        pipe = near_expiry.build_renewal_pipeline(df, current_period=cur_period)
        if pipe.empty:
            st.info("No expiry cohorts to show.")
        else:
            open_mask = pipe["window_status"] == "Window open"
            upcoming_mask = pipe["window_status"] == "Upcoming"
            tot_expiring = int(pipe["expiring"].sum())
            tot_renewed = int(pipe["renewed"].sum())
            tot_pending = int(pipe["pending"].sum())
            in_window_pending = int(pipe.loc[open_mask, "pending"].sum())

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown(kpi_card("Total Memberships Expiring", fmt_int(tot_expiring), accent=True), unsafe_allow_html=True)
            with k2:
                st.markdown(kpi_card("Already Renewed", fmt_int(tot_renewed),
                                     delta="Deducted from pending"), unsafe_allow_html=True)
            with k3:
                st.markdown(kpi_card("Pending Renewal", fmt_int(tot_pending)), unsafe_allow_html=True)
            with k4:
                st.markdown(kpi_card("Pending — Window Open", fmt_int(in_window_pending),
                                     delta="Within 30 days of expiry — act now"), unsafe_allow_html=True)

            st.markdown("&nbsp;")

            # Next-month focus card: cohort expiring in the month after current period
            nxt = (cur_period + pd.offsets.MonthBegin(1))
            nxt_label = nxt.strftime("%b-%y")
            nxt_row = pipe[pipe["expiry_month_label"] == nxt_label]
            if not nxt_row.empty:
                r = nxt_row.iloc[0]
                st.success(
                    f"📅 **Next month ({nxt_label})**: {int(r['expiring']):,} memberships expire "
                    f"(enrolled {r['enroll_month']}). {int(r['renewed']):,} already renewed · "
                    f"**{int(r['pending']):,} still pending** · window opens {r['window_open']}."
                )

            # Stacked chart: renewed vs pending per expiry month (clickable)
            melt = pipe.melt(id_vars=["expiry_month_label"],
                             value_vars=["renewed", "pending"],
                             var_name="state", value_name="members")
            melt["state"] = melt["state"].map({"renewed": "Renewed", "pending": "Pending"})
            melt["sort_key"] = pd.to_datetime(melt["expiry_month_label"], format="%b-%y", errors="coerce")
            melt = melt.sort_values("sort_key")
            fig = px.bar(melt, x="expiry_month_label", y="members", color="state",
                         barmode="stack", title="Renewal pipeline by expiry month (click a bar to download that cohort)",
                         color_discrete_map={"Renewed": GOLD, "Pending": SILVER},
                         labels={"expiry_month_label": "Expiry Month", "members": "Members"})
            _style_plotly(fig, height=380)
            event = st.plotly_chart(fig, use_container_width=True,
                                    on_select="rerun", key="ne_pipe_chart")
            _segment_download_from_event(
                event, df, near_expiry,
                field="expiry_month_label", label="cohort", key_prefix="ne_pipe")

            st.markdown("#### Renewal pipeline table")
            show = near_expiry.format_renewal_for_display(pipe)
            if "Renewal %" in show.columns:
                show["Renewal %"] = show["Renewal %"].astype(str) + "%"
            st.dataframe(_style_table(show), use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download full renewal pipeline (CSV)",
                data=df_to_csv_bytes(show),
                file_name=f"renewal_pipeline_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv", key="dl_pipe_full")

    # ========================= Expiring Members ==========================
    with tab_members:
        f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1])
        month_choice = f1.selectbox("Expiry month", ["All months"] + months,
                                    index=1 if months else 0, key="ne_month")
        tier_opts = ["All tiers"] + sorted([t for t in df["plan_tier"].dropna().unique() if t])
        tier_choice = f2.selectbox("Tier", tier_opts, index=0, key="ne_tier")
        shop_choice = f3.selectbox("Shopped this month?", ["All", "Yes", "No"], index=0, key="ne_shop")
        state_choice = f4.selectbox("Renewal state", ["All", "Pending", "Renewed"], index=0, key="ne_state")

        ne = near_expiry.build_near_expiry(df, month_choice)
        if tier_choice != "All tiers":
            ne = ne[ne["plan_tier"] == tier_choice]
        if shop_choice != "All":
            ne = ne[ne["shopped_current_month"] == shop_choice]
        if state_choice != "All":
            ne = ne[ne["renewal_state"] == state_choice]

        if ne.empty:
            st.info("No members match the selected filters.")
            return

        total = len(ne)
        shopped = int((ne["shopped_current_month"] == "Yes").sum())
        not_shopped = total - shopped
        pending = int((ne["renewal_state"] == "Pending").sum())

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(kpi_card("Expiring Members", fmt_int(total), accent=True), unsafe_allow_html=True)
        with k2:
            st.markdown(kpi_card("Pending Renewal", fmt_int(pending),
                                 f"{pending/total*100:.1f}% to chase"), unsafe_allow_html=True)
        with k3:
            st.markdown(kpi_card("Shopped This Month", fmt_int(shopped),
                                 f"{shopped/total*100:.1f}% active"), unsafe_allow_html=True)
        with k4:
            st.markdown(kpi_card("Did Not Shop", fmt_int(not_shopped),
                                 f"{not_shopped/total*100:.1f}% at risk"), unsafe_allow_html=True)

        st.markdown("&nbsp;")

        # Clickable shopping-behaviour donut -> per-segment download
        beh = pd.DataFrame({"Behaviour": ["Shopped", "Did Not Shop"],
                            "Count": [shopped, not_shopped]})
        fig = px.pie(beh, names="Behaviour", values="Count",
                     title="Shopping behaviour (click a slice to download that segment)",
                     color="Behaviour",
                     color_discrete_map={"Shopped": GOLD, "Did Not Shop": SILVER}, hole=0.5)
        _style_plotly(fig, height=340)
        beh_event = st.plotly_chart(fig, use_container_width=True,
                                    on_select="rerun", key="ne_beh_chart")
        _behaviour_segment_download(beh_event, ne, near_expiry, key_prefix="ne_beh")

        st.markdown("### Near-expiry member table")
        label = "all expiry months" if month_choice == "All months" else month_choice
        st.caption(f"Showing **{total:,}** members · {label} · {state_choice.lower()} state.")
        show = near_expiry.format_for_display(ne)
        for c in ("Current Bill Value", "MTD Cashback Earned", "MTD Redemption"):
            if c in show.columns:
                show[c] = pd.to_numeric(show[c], errors="coerce").round(2)
        st.dataframe(_style_table(show), use_container_width=True, hide_index=True, height=520)

        st.download_button(
            "⬇️ Download near-expiry CSV",
            data=df_to_csv_bytes(show),
            file_name=f"near_expiry_{month_choice.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv", key="dl_ne_full")


# ---------------------------------------------------------------------------
# Page: Rewards Intelligence (embedded HTML dashboard fed by AMS report)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cached_rewards_html(version: str) -> tuple[str, int, str]:
    """Build the embedded rewards dashboard once per data version."""
    df = db.fetch_df("SELECT * FROM ams_report_cache")
    if df.empty:
        return ("", 0, "")
    return rewards_intelligence.build_for_streamlit(
        df, current_period_label=current_period_label()
    )


def page_rewards_intelligence():
    header(
        "Rewards Intelligence",
        "Live charts, KPIs and analytics — native Python, fast on large data",
    )

    if not has_data():
        st.info("No data has been uploaded yet. An admin can upload files via the **Upload Data** menu.")
        return

    df = cached_ams_report(report_version())
    if df.empty:
        st.warning("Report cache is empty. Trigger a rebuild from the Upload page.")
        return

    # Reporting month = latest enrolment month present, falling back to period.
    rm = current_period_label()

    rewards_native.render(
        st, df,
        kpi_card=kpi_card,
        fmt_int=fmt_int,
        fmt_inr=fmt_inr,
        reporting_month=rm,
    )

    st.markdown("&nbsp;")
    # Optional: still offer the standalone HTML export for sharing offline.
    with st.expander("⬇️ Download standalone HTML report (for sharing offline)", expanded=False):
        st.caption(
            "The interactive view above is fully native and fast. If you need a "
            "single self-contained file to email or open without the app, generate "
            "the HTML snapshot below (it can be slow to build for very large data)."
        )
        if st.button("Build HTML snapshot", key="build_html_snapshot"):
            with st.spinner("Building HTML snapshot…"):
                html, n_records, rm2 = cached_rewards_html(report_version())
            if html:
                st.download_button(
                    "Download rewards_intelligence.html",
                    data=html.encode("utf-8"),
                    file_name="rewards_intelligence.html",
                    mime="text/html",
                    key="dl_rewards_html",
                )
                st.success(f"Snapshot ready — {n_records:,} records · reporting month {rm2}.")
            else:
                st.warning("Nothing to export yet.")


# ---------------------------------------------------------------------------
# Page: Store Master
# ---------------------------------------------------------------------------
def page_store_master():
    header("Store Master", "Mapping for store name, region, cluster, city, format")


    stores = db.list_stores()

    st.dataframe(stores, use_container_width=True, hide_index=True, height=500)
    st.caption(f"{len(stores)} stores in master.")

    if not auth.is_admin():
        st.info("🔒 Sign in as an admin to add or remove stores.")
        return

    st.markdown("---")
    st.markdown("### Admin actions")

    tab_add, tab_edit, tab_delete = st.tabs(["➕ Add / update store", "✏️ Edit existing", "🗑 Delete store"])

    with tab_add:
        with st.form("add_store_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            sc = c1.text_input("Store Code")
            sn = c2.text_input("Store Name")
            fmt = c3.selectbox("Format", ["Daily", "Super", "Hyper", "Other"])
            c4, c5, c6 = st.columns(3)
            region = c4.text_input("Region", value="East")
            cluster = c5.text_input("Cluster")
            city = c6.text_input("City")
            submit = st.form_submit_button("Save store", type="primary")
            if submit:
                if not sc.strip():
                    st.error("Store code is required.")
                else:
                    db.upsert_store(sc, sn, region, city, cluster, fmt)
                    st.success(f"Saved store **{sc}**.")
                    st.rerun()

    with tab_edit:
        codes = stores["Store Code"].tolist()
        if not codes:
            st.info("No stores to edit.")
        else:
            pick = st.selectbox("Pick a store to edit", codes, key="edit_pick")
            match = stores[stores["Store Code"] == pick]
            if match.empty:
                st.info("Pick a store from the list above.")
            else:
                row = match.iloc[0]
                with st.form(f"edit_form_{pick}"):
                    c1, c2, c3 = st.columns(3)
                    sn = c1.text_input("Store Name", value=row["Store Name"])
                    fmt = c2.text_input("Format", value=row["Format"])
                    region = c3.text_input("Region", value=row["Region"])
                    c4, c5 = st.columns(2)
                    cluster = c4.text_input("Cluster", value=row["Cluster"])
                    city = c5.text_input("City", value=row["City"])
                    submit = st.form_submit_button("Update", type="primary")
                    if submit:
                        db.upsert_store(pick, sn, region, city, cluster, fmt)
                        st.success(f"Updated **{pick}**.")
                        st.rerun()

    with tab_delete:
        codes = stores["Store Code"].tolist()
        if not codes:
            st.info("No stores to delete.")
        else:
            pick_d = st.selectbox("Pick a store to delete", codes, key="delete_pick")
            confirm = st.checkbox(f"I understand this will permanently remove **{pick_d}** from the master.",
                                  key="delete_confirm")
            if st.button("Delete store", type="primary", disabled=not confirm):
                db.delete_store(pick_d)
                st.success(f"Deleted store **{pick_d}**.")
                st.rerun()


# ---------------------------------------------------------------------------
# Page: Upload Data (admin only)
# ---------------------------------------------------------------------------
def page_upload():
    header("Upload Data", "Refresh the dashboard with the latest source files")

    if not auth.is_admin():
        st.error("🔒 Admin access required.")
        return

    st.markdown(
        """
        Upload one or more of the four source files. Anything you upload is loaded
        into SQLite and **persists** until you upload a newer version (or click
        *Clear all data* below).
        """
    )

    # ----- Status panel --------------------------------------------------
    st.markdown("### Current data status")
    status = pd.DataFrame([
        {"Table": "Membership", "Rows": db.row_count("membership")},
        {"Table": "Shopping Summary", "Rows": db.row_count("shopping")},
        {"Table": "Redemption", "Rows": db.row_count("redemption")},
        {"Table": "Customer Trend", "Rows": db.row_count("customer_trend")},
        {"Table": "Liquor Buyers Base (mobiles)", "Rows": db.row_count("liq_buyers_base")},
        {"Table": "Liquor Sales (transactions)", "Rows": db.row_count("liq_sales")},
    ])
    st.dataframe(status, use_container_width=True, hide_index=True)
    st.caption(f"Last report build: {db.get_meta('report_built_at', '—')}  "
               f"·  Current period: **{current_period_label()}**")

    st.markdown("---")
    st.markdown("### Upload files")

    c1, c2 = st.columns(2)
    mem_file = c1.file_uploader("Membership CSV", type=["csv"], key="upload_mem")
    shop_file = c2.file_uploader("Shopping Summary CSV", type=["csv"], key="upload_shop")
    c3, c4 = st.columns(2)
    redm_file = c3.file_uploader("Redemption CSV", type=["csv"], key="upload_red")
    trend_file = c4.file_uploader("Customer Trend CSV (UTF-16, tab-separated)", type=["csv"], key="upload_trend")

    # ----- Liquor data --------------------------------------------------
    st.markdown("---")
    st.markdown("### 🥂 Liquor data")
    st.caption(
        "Two separate liquor files. The **buyers base** is the 1-year master "
        "list of mobile numbers that flags Diamond members as Existing vs New "
        "liquor buyers (upload occasionally). The **sales** file is the ongoing "
        "transactional data shown on the Overview — upload just the latest day "
        "and it auto-appends to what's already stored (de-duplicated)."
    )

    lc1, lc2 = st.columns(2)
    liq_base_file = lc1.file_uploader(
        "Liquor Buyers BASE CSV (single column of mobile numbers)",
        type=["csv"], key="upload_liq_base")
    liq_sales_file = lc2.file_uploader(
        "Liquor SALES CSV (append — date, store, mobile, nob, qty, sales)",
        type=["csv"], key="upload_liq_sales")

    # Sample CSV + consolidated Excel download
    sample_liq = pd.DataFrame([
        {"date": "2026-06-01", "month": "Jun-26", "store code": "M053",
         "store name": "Springdale S", "mobile number": "9830000001",
         "nob": 1, "billed qty": 2, "gross sales": 1450},
        {"date": "2026-06-01", "month": "Jun-26", "store code": "S004",
         "store name": "Park Street S", "mobile number": "9830000002",
         "nob": 2, "billed qty": 3, "gross sales": 2780},
    ])
    sc1, sc2 = st.columns(2)
    sc1.download_button(
        "⬇️ Download liquor-sales sample CSV format",
        data=df_to_csv_bytes(sample_liq),
        file_name="liquor_sales_sample_format.csv",
        mime="text/csv",
        use_container_width=True,
    )
    # Consolidated Excel of everything stored so far
    liq_all = db.liq_sales_df()
    if not liq_all.empty:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            liq_all.to_excel(xw, index=False, sheet_name="Liquor Sales")
        sc2.download_button(
            f"⬇️ Download consolidated liquor-sales Excel ({len(liq_all):,} rows)",
            data=buf.getvalue(),
            file_name=f"liquor_sales_consolidated_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        sc2.button("⬇️ Consolidated Excel (no liquor sales yet)",
                   disabled=True, use_container_width=True)

    with st.expander("Manage stored liquor data"):
        st.caption(
            f"Buyers base: **{db.row_count('liq_buyers_base'):,}** mobiles · "
            f"Sales: **{db.row_count('liq_sales'):,}** transactions."
        )
        if st.button("🗑 Clear stored liquor SALES (keeps buyers base)"):
            db.clear_liq_sales()
            cached_ams_report.clear()
            st.success("Liquor sales cleared.")
            st.rerun()

    # ----- Report-month selector ----------------------------------------
    # By default the report is built for the latest month found across the
    # uploaded files. But sometimes the redemption file contains a few
    # transactions that posted on the 1st of the *next* month (auto-credits
    # for the previous month's purchases), which would push "current period"
    # forward to a month for which Shopping has no data — making the report
    # show zeros. The selector below lets you pin the report to a specific
    # month.
    st.markdown("### Report month")
    available = processing.available_periods()
    smart_default = processing.smart_default_period()

    if available:
        # Newest first so the most likely choice sits at the top of the list.
        options = list(reversed(available))
        labels = [p.strftime("%b-%Y") for p in options]

        if smart_default is not None and smart_default in options:
            default_idx = options.index(smart_default)
        else:
            default_idx = 0

        chosen_label = st.selectbox(
            "Build the report for which month?",
            labels,
            index=default_idx,
            key="report_month_picker",
            help=(
                "Defaults to the latest month with Shopping data. Change it "
                "if you've uploaded data through a particular month-end and "
                "the auto-detected period is rolling forward into the next "
                "month because of redemption auto-credits."
            ),
        )
        chosen_period = options[labels.index(chosen_label)]
        chosen_period_str = chosen_period.strftime("%Y-%m-%d")
    else:
        st.info(
            "No data loaded yet — upload at least one file below, then come "
            "back to pick a report month."
        )
        chosen_period = None
        chosen_period_str = None

    if st.button("🔄 Process uploaded files & rebuild reports", type="primary", use_container_width=True):
        load_steps = []
        progress = st.progress(0.0, text="Starting...")
        try:
            step_n = sum(1 for f in (mem_file, shop_file, redm_file, trend_file,
                                     liq_base_file, liq_sales_file) if f is not None) + 2
            done = 0

            if mem_file is not None:
                progress.progress(done / step_n, text="Parsing membership...")
                m = ingest.parse_membership(mem_file)
                db.replace_table("membership", m)
                load_steps.append(f"Membership: {len(m):,} rows")
                done += 1
                progress.progress(done / step_n)

            if shop_file is not None:
                progress.progress(done / step_n, text="Parsing shopping summary...")
                s = ingest.parse_shopping(shop_file)
                db.replace_table("shopping", s)
                load_steps.append(f"Shopping: {len(s):,} rows")
                done += 1
                progress.progress(done / step_n)

            if redm_file is not None:
                progress.progress(done / step_n, text="Parsing redemption...")
                r = ingest.parse_redemption(redm_file)
                db.replace_table("redemption", r)
                load_steps.append(f"Redemption: {len(r):,} rows")
                done += 1
                progress.progress(done / step_n)

            if trend_file is not None:
                progress.progress(done / step_n, text="Parsing customer trend (this can take ~20s)...")
                t = ingest.parse_customer_trend(trend_file)
                db.replace_table("customer_trend", t)
                load_steps.append(f"Customer Trend: {len(t):,} rows")
                done += 1
                progress.progress(done / step_n)

            if liq_base_file is not None:
                progress.progress(done / step_n, text="Parsing liquor buyers base...")
                lb = ingest.parse_liq_base(liq_base_file)
                db.replace_liq_base(lb)
                load_steps.append(f"Liquor Buyers Base: {len(lb):,} mobiles")
                done += 1
                progress.progress(done / step_n)

            if liq_sales_file is not None:
                progress.progress(done / step_n, text="Parsing & appending liquor sales...")
                ls = ingest.parse_liq_sales(liq_sales_file)
                added, skipped = db.append_liq_sales(ls)
                load_steps.append(
                    f"Liquor Sales: +{added:,} new rows appended"
                    + (f" ({skipped:,} duplicates skipped)" if skipped else "")
                )
                done += 1
                progress.progress(done / step_n)

            # If files were just uploaded, the period list might have changed —
            # fall back to the smart default if the previously-chosen period no
            # longer exists.
            build_period = chosen_period_str
            if build_period is None:
                fresh_default = processing.smart_default_period()
                build_period = fresh_default.strftime("%Y-%m-%d") if fresh_default is not None else None

            period_msg = (
                pd.to_datetime(build_period).strftime("%b-%Y")
                if build_period else "auto-detected"
            )
            progress.progress(done / step_n, text=f"Building AMS Migration Report for {period_msg}...")
            ams = processing.build_ams_report(report_period=build_period)
            done += 1
            progress.progress(done / step_n, text="Building Renewal Report...")
            ren = renewal.build_renewal_report()
            done += 1
            progress.progress(1.0, text="Done.")

            # Bust caches
            cached_ams_report.clear()
            cached_renewal_report.clear()
            cached_rewards_html.clear()

            if load_steps:
                st.success("✅ Loaded:\n\n- " + "\n- ".join(load_steps))
            st.success(
                f"✅ Reports rebuilt for **{period_msg}** — {len(ams):,} customer rows, "
                f"{len(ren):,} store-month renewal rows."
            )

        except Exception as e:
            progress.empty()
            st.error(f"❌ Processing failed: {e}")
            st.exception(e)

    # ----- Rebuild-only (no re-upload) ----------------------------------
    # Useful when the data is already loaded and you just want to switch the
    # report month — e.g. you uploaded files dated through 30-Apr but the
    # report initially built for May because of stray May-1 auto-credits in
    # the redemption file. Pick April above and click rebuild.
    if available:
        st.markdown("---")
        st.markdown("### Rebuild reports for selected month")
        st.caption(
            "Already uploaded the files? Pick a month above and click below — "
            "no need to re-upload. This rebuilds the AMS Migration Report and "
            "Renewals for the chosen month."
        )
        if st.button("🛠️ Rebuild reports for selected month", use_container_width=True):
            try:
                with st.spinner(
                    f"Rebuilding for {chosen_period.strftime('%b-%Y')}..."
                ):
                    ams = processing.build_ams_report(report_period=chosen_period_str)
                    ren = renewal.build_renewal_report()
                cached_ams_report.clear()
                cached_renewal_report.clear()
                cached_rewards_html.clear()
                st.success(
                    f"✅ Reports rebuilt for **{chosen_period.strftime('%b-%Y')}** — "
                    f"{len(ams):,} customer rows, {len(ren):,} store-month renewal rows."
                )
            except Exception as e:
                st.error(f"❌ Rebuild failed: {e}")
                st.exception(e)

    st.markdown("---")
    st.markdown("### Danger zone")
    with st.expander("Clear all uploaded data"):
        confirm = st.checkbox("I understand this wipes all loaded data (stores & admins are kept).",
                              key="clear_confirm")
        if st.button("Clear all data", disabled=not confirm):
            db.clear_all_data()
            cached_ams_report.clear()
            cached_renewal_report.clear()
            cached_rewards_html.clear()
            st.success("All data cleared.")
            st.rerun()


# ---------------------------------------------------------------------------
# Page: Settings
# ---------------------------------------------------------------------------
def page_settings():
    header("Settings", "Admin account management")
    if not auth.is_admin():
        st.error("🔒 Admin access required.")
        return

    st.markdown("### Change admin password")
    with st.form("change_pw_form"):
        current = st.text_input("Current password", type="password")
        new1 = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        ok = st.form_submit_button("Update password", type="primary")
        if ok:
            if not db.verify_admin(auth.current_user(), current):
                st.error("Current password is incorrect.")
            elif new1 != new2 or len(new1) < 6:
                st.error("New passwords don't match or are shorter than 6 characters.")
            else:
                db.change_admin_password(auth.current_user(), new1)
                st.success("Password updated. Please sign in again.")
                auth.logout()
                st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def main():
    page = render_navbar()
    if page == "Overview":
        page_overview()
    elif page == "Loyalty KPI":
        render_loyalty_kpi_page(
            header_fn=header,
            has_data_fn=has_data,
            cached_ams_report_fn=cached_ams_report,
            report_version_fn=report_version,
            current_period_label_fn=current_period_label,
        )
    elif page == "AMS Migration Report":
        page_ams_report()
    elif page == "Renewals":
        page_renewals()
    elif page == "Near Expiry":
        page_near_expiry()
    elif page == "Rewards Intelligence":
        page_rewards_intelligence()
    elif page == "Store Master":
        page_store_master()
    elif page == "Upload Data":
        page_upload()
    elif page == "Settings":
        page_settings()


if __name__ == "__main__":
    main()
