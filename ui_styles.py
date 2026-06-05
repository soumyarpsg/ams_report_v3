"""Reusable CSS for the new tier cards and Loyalty KPI page.

Kept separate so app.py stays slim and the same styles can be injected on
both Overview and Loyalty KPI pages without duplication.

Tier-card styling is keyed off the Streamlit ``key`` attribute we attach to
each ``st.button`` — modern Streamlit (>=1.32) emits an ``st-key-<key>``
class on the element container, which we target from CSS.
"""
from __future__ import annotations

import streamlit as st

from util_filters import TIER_THEME


def _tier_card_block(tier_name: str, theme: dict) -> str:
    """Build the per-tier card CSS (inactive + active states)."""
    cls = tier_name.lower()
    # ``st-key-tier_btn_<cls>`` is emitted automatically by Streamlit when we
    # render the button with key="tier_btn_<cls>".
    key_class = f"st-key-tier_btn_{cls}"
    active_class = f"st-key-tier_btn_{cls}_active"
    return f"""
    /* {tier_name} tier card — inactive */
    .{key_class} button {{
        background: linear-gradient(135deg, {theme['gradient_from']} 0%, {theme['gradient_to']} 100%) !important;
        color: {theme['text_on']} !important;
        border: 1px solid {theme['border']} !important;
        border-radius: 14px !important;
        padding: 1rem 1.15rem !important;
        height: auto !important;
        min-height: 138px !important;
        width: 100% !important;
        font-weight: 600 !important;
        text-align: left !important;
        line-height: 1.45 !important;
        white-space: pre-line !important;
        box-shadow: 0 4px 14px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.4) !important;
        transition: transform .18s ease, box-shadow .18s ease, filter .18s ease !important;
    }}
    .{key_class} button p {{
        color: {theme['text_on']} !important;
        font-weight: 600 !important;
        text-align: left !important;
    }}
    .{key_class} button:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 22px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.5) !important;
        filter: brightness(1.04) !important;
    }}
    .{key_class} button:focus {{
        outline: none !important;
        box-shadow: 0 0 0 3px {theme['border']}55, 0 8px 20px rgba(0,0,0,0.15) !important;
    }}
    /* Active state — ring + lifted shadow */
    .{active_class} button {{
        outline: 3px solid {theme['border']} !important;
        outline-offset: -3px !important;
        box-shadow: 0 10px 28px rgba(0,0,0,0.20), inset 0 1px 0 rgba(255,255,255,0.55) !important;
        transform: translateY(-1px) !important;
    }}
    """


def inject_tier_card_css() -> None:
    """Inject all tier-card + KPI page CSS. Safe to call once per page render."""
    blocks = "\n".join(_tier_card_block(t, TIER_THEME[t]) for t in TIER_THEME)
    st.markdown(
        f"""
        <style>
        /* ---------- Tier cards row ---------- */
        .tier-cards-section {{
            margin: 0.25rem 0 1rem 0;
        }}
        .tier-active-banner {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.95rem;
            border-radius: 999px;
            background: #FFFDF6;
            border: 1px solid #C9A227;
            color: #9C7A18;
            font-size: 0.85rem;
            font-weight: 600;
            margin: 0.25rem 0 0.85rem 0;
        }}

        /* ---------- KPI section heading ---------- */
        .kpi-section-h {{
            display: flex;
            align-items: center;
            gap: 0.65rem;
            margin: 1.6rem 0 0.7rem 0;
            padding-bottom: 0.45rem;
            border-bottom: 2px solid #E4DBC2;
        }}
        .kpi-section-h .num {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 1.75rem; height: 1.75rem;
            padding: 0 0.4rem;
            background: #C9A227;
            color: white;
            border-radius: 6px;
            font-weight: 700;
            font-size: 0.82rem;
            letter-spacing: 0.3px;
            box-shadow: 0 0 12px -2px rgba(201,162,39,0.6);
        }}
        .kpi-section-h .title {{
            margin: 0;
            color: #2A2410;
            font-size: 1.02rem;
            font-weight: 700;
            letter-spacing: 0.2px;
        }}

        /* ---------- Table title strip ---------- */
        .table-title-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 0.55rem 0 0.3rem 0;
            gap: 1rem;
        }}
        .table-title-row .lbl {{
            font-weight: 600;
            color: #2A2410;
            font-size: 0.92rem;
        }}

        /* Compact download buttons (dark, blue-edged) */
        .st-key-dl_csv button,
        .st-key-dl_xlsx button,
        .st-key-dl_pdf button,
        div[data-testid="stDownloadButton"] button {{
            background: #FFFDF6 !important;
            color: #2A2410 !important;
            border: 1px solid #C9A227 !important;
            border-radius: 8px !important;
            padding: 0.4rem 0.85rem !important;
            font-size: 0.82rem !important;
            font-weight: 600 !important;
            transition: all .15s ease !important;
        }}
        div[data-testid="stDownloadButton"] button:hover {{
            border-color: #E6C766 !important;
            background: #FBF4DD !important;
            box-shadow: 0 0 16px -3px rgba(201,162,39,0.6) !important;
        }}

        /* ---------- Sidebar logo / brand block ---------- */
        .msr-logo-wrap {{
            display: flex;
            justify-content: center;
            padding: 0.4rem 0 0.6rem 0;
        }}
        .msr-logo-wrap img {{
            max-width: 92%;
            height: auto;
            border-radius: 8px;
        }}
        .msr-logo-fallback {{
            width: 100%;
            text-align: center;
            padding: 0.95rem 0.6rem;
            background: linear-gradient(135deg, #C9A227 0%, #9C7A18 100%);
            border-radius: 12px;
            color: white;
            box-shadow: 0 0 22px -6px rgba(201,162,39,0.7);
        }}
        .msr-logo-fallback .brand {{
            font-size: 1.55rem;
            font-weight: 800;
            letter-spacing: 2px;
            line-height: 1;
        }}
        .msr-logo-fallback .sub {{
            font-size: 0.68rem;
            opacity: 0.95;
            margin-top: 0.35rem;
            letter-spacing: 1.4px;
            text-transform: uppercase;
        }}

        /* ---------- KPI chart wrapper (dark card) ---------- */
        .kpi-chart-card {{
            background: #FFFFFF;
            border: 1px solid #E4DBC2;
            border-radius: 12px;
            padding: 0.6rem 0.75rem;
            box-shadow: 0 0 18px -8px rgba(201,162,39,0.45);
        }}

        {blocks}
        </style>
        """,
        unsafe_allow_html=True,
    )
