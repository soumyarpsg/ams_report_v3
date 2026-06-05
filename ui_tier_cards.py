"""Clickable tier-filter cards.

Renders a row of three KPI cards (Gold / Platinum / Diamond). Clicking a
card toggles the global tier filter held in ``st.session_state``. The same
component is rendered on the Overview page and the Loyalty KPI page so the
selection stays in sync across navigation.

Each card surfaces 4 metrics computed on the (already region/cluster/format/
store-filtered) DataFrame passed in by the caller:

    Total Members  ·  Active Members  ·  Redemption %  ·  Avg Monthly Spend

Caller is responsible for any non-tier filtering before passing ``df`` in.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from util_filters import (
    TIER_ORDER,
    TIER_THEME,
    get_selected_tier,
    toggle_tier,
)


def _format_inr(value: float) -> str:
    if pd.isna(value) or value is None:
        return "₹0"
    return f"₹{value:,.0f}"


def _format_int(value) -> str:
    if pd.isna(value) or value is None:
        return "0"
    return f"{int(value):,}"


def _tier_metrics(df: pd.DataFrame, tier: str) -> dict:
    """Compute the 4 KPIs for a tier slice of ``df``."""
    if df.empty or "plan_tier" not in df.columns:
        return {"total": 0, "active": 0, "redemption_pct": 0.0, "avg_monthly_spend": 0.0}

    slice_df = df[df["plan_tier"] == tier]
    total = len(slice_df)
    if total == 0:
        return {"total": 0, "active": 0, "redemption_pct": 0.0, "avg_monthly_spend": 0.0}

    active = int((slice_df["shopper_behaviour"] == "Shopped").sum()) \
        if "shopper_behaviour" in slice_df.columns else 0

    # Redemption % = (members who redeemed YTD) / total tier members  × 100
    if "ytd_redemption" in slice_df.columns:
        redeemers = int((pd.to_numeric(slice_df["ytd_redemption"], errors="coerce").fillna(0) > 0).sum())
        redemption_pct = (redeemers / total) * 100
    else:
        redemption_pct = 0.0

    # Average Monthly Spend (current month bill value) — averaged over all
    # tier members (incl. non-shoppers, who get 0) so the number is comparable
    # tier-to-tier without active-base distortion.
    if "bill_value" in slice_df.columns:
        avg_spend = pd.to_numeric(slice_df["bill_value"], errors="coerce").fillna(0).mean()
    else:
        avg_spend = 0.0

    return {
        "total": total,
        "active": active,
        "redemption_pct": float(redemption_pct),
        "avg_monthly_spend": float(avg_spend),
    }


def _card_label(tier: str, m: dict) -> str:
    """Build the multi-line label rendered inside the button. We rely on
    CSS ``white-space: pre-line`` to honour the newlines."""
    theme = TIER_THEME[tier]
    return (
        f"{theme['icon']}  {theme['label'].upper()}\n"
        f"Total Members:  {_format_int(m['total'])}\n"
        f"Active:  {_format_int(m['active'])}\n"
        f"Redemption %:  {m['redemption_pct']:.1f}%\n"
        f"Avg Monthly Spend:  {_format_inr(m['avg_monthly_spend'])}"
    )


def render_tier_cards(df: pd.DataFrame, key_prefix: str = "ovr") -> None:
    """Render the three clickable tier cards as a row.

    Args:
        df: A DataFrame already filtered by region/cluster/format/store (but
            NOT by tier — tier breakdown is the point of this component).
        key_prefix: Disambiguates widget keys when the cards appear on two
            pages within the same session (e.g. Overview vs Loyalty KPI).
    """
    selected = get_selected_tier()

    st.markdown('<div class="tier-cards-section">', unsafe_allow_html=True)

    cols = st.columns(3, gap="small")
    for col, tier in zip(cols, TIER_ORDER):
        with col:
            metrics = _tier_metrics(df, tier)
            label = _card_label(tier, metrics)

            # The Streamlit element-container gets an `st-key-<key>` class
            # automatically. We use that to scope styling. When the tier is
            # active we use a different key so a second CSS rule applies the
            # "active ring" outline.
            active = selected == tier
            tier_lower = tier.lower()
            widget_key = f"tier_btn_{tier_lower}_active" if active else f"tier_btn_{tier_lower}"

            # Add a per-call uniqueness suffix on top of the key so the same
            # cards can render on two pages in the same Streamlit session
            # without "duplicate key" errors. We hide it as a `help` lookup.
            unique_key = f"{widget_key}__{key_prefix}"

            clicked = st.button(
                label,
                key=unique_key,
                use_container_width=True,
                help=(
                    f"Click to filter the entire dashboard to {tier} members. "
                    "Click again to clear the filter."
                ),
            )
            if clicked:
                toggle_tier(tier)
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # Active-tier banner with clear action
    if selected is not None:
        b1, b2 = st.columns([4, 1])
        with b1:
            st.markdown(
                f'<div class="tier-active-banner">🎯 Filter active: showing only '
                f'<strong>{selected}</strong> members across the dashboard</div>',
                unsafe_allow_html=True,
            )
        with b2:
            if st.button("✕ Clear tier filter", key=f"tier_clear_{key_prefix}",
                         use_container_width=True):
                from util_filters import set_selected_tier
                set_selected_tier(None)
                st.rerun()


# ---------------------------------------------------------------------------
# CSS-key wiring note
# ---------------------------------------------------------------------------
# The widget key contains an "__{prefix}" suffix so the same cards can render
# on multiple pages within one Streamlit session. Streamlit's `st-key-…` CSS
# class uses the full key, so we need the CSS to match a prefix rather than
# the exact key. Because the suffix is always trailing, an attribute-prefix
# selector ([class*="st-key-tier_btn_gold"]) reliably matches both the base
# key and the active-state key. The styles module uses class selectors like
# `.st-key-tier_btn_gold button {…}`, which match prefix-substrings of any
# longer key because element-containers carry the *exact* st-key class — so
# we add a small helper here to inject attribute-substring selectors that
# cover the prefix-suffixed keys we actually emit.
def inject_widget_key_selectors() -> None:
    """Augment the static CSS in components/styles.py with selectors that
    handle the key-prefix suffix added by ``render_tier_cards``.

    Streamlit emits exactly ``st-key-<full_key>`` on the wrapper div. The
    static CSS targets ``.st-key-tier_btn_gold`` but our actual keys look
    like ``tier_btn_gold__ovr``. We inject attribute-substring matchers as
    a thin overlay.
    """
    css_blocks = []
    for tier in TIER_ORDER:
        theme = TIER_THEME[tier]
        cls = tier.lower()
        css_blocks.append(f"""
        div[class*="st-key-tier_btn_{cls}"] button {{
            background: linear-gradient(135deg, {theme['gradient_from']} 0%, {theme['gradient_to']} 100%) !important;
            color: {theme['text_on']} !important;
            border: 1px solid {theme['border']} !important;
            border-radius: 14px !important;
            padding: 1rem 1.15rem !important;
            min-height: 138px !important;
            font-weight: 600 !important;
            text-align: left !important;
            line-height: 1.45 !important;
            white-space: pre-line !important;
            box-shadow: 0 4px 14px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.4) !important;
            transition: transform .18s ease, box-shadow .18s ease, filter .18s ease !important;
        }}
        div[class*="st-key-tier_btn_{cls}"] button p {{
            color: {theme['text_on']} !important;
            text-align: left !important;
        }}
        div[class*="st-key-tier_btn_{cls}"] button:hover {{
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 22px rgba(0,0,0,0.15), inset 0 1px 0 rgba(255,255,255,0.5) !important;
            filter: brightness(1.04) !important;
        }}
        div[class*="st-key-tier_btn_{cls}_active"] button {{
            outline: 3px solid {theme['border']} !important;
            outline-offset: -3px !important;
            box-shadow: 0 10px 28px rgba(0,0,0,0.20), inset 0 1px 0 rgba(255,255,255,0.55) !important;
            transform: translateY(-1px) !important;
        }}
        """)
    st.markdown("<style>" + "\n".join(css_blocks) + "</style>", unsafe_allow_html=True)
