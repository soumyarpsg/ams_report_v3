"""Shared filter state helpers.

Centralises the tier-card session state, so the same selected tier filter
applies on the Overview page, the Loyalty KPI page, AMS Migration Report,
Renewals and Rewards Intelligence — without each page having to reinvent
the logic.

Public API
----------
SELECTED_TIER_KEY     — st.session_state key holding the active tier (or None)
get_selected_tier()   — current selection
set_selected_tier(t)  — set to "Gold" | "Platinum" | "Diamond" | None
toggle_tier(t)        — click-to-select / click-again-to-clear
apply_tier_filter(df) — apply the active tier filter to a DataFrame
TIER_THEME            — visual config (color, gradient, label) per tier
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Session state key
# ---------------------------------------------------------------------------
SELECTED_TIER_KEY = "msr_selected_tier"  # value: None | "Gold" | "Platinum" | "Diamond"


# ---------------------------------------------------------------------------
# Per-tier visual config (used by tier cards and chart colour maps)
# ---------------------------------------------------------------------------
TIER_THEME = {
    "Gold": {
        "color": "#C9A227",            # Solid gold for chart series
        "gradient_from": "#F6E27A",
        "gradient_to": "#C9A227",
        "border": "#B8911E",
        "text_on": "#3D2E00",
        "icon": "🥇",
        "label": "Gold",
    },
    "Platinum": {
        "color": "#8C95A1",            # Cool silver
        "gradient_from": "#E6E9EE",
        "gradient_to": "#8C95A1",
        "border": "#6B7280",
        "text_on": "#1F2937",
        "icon": "🪙",
        "label": "Platinum",
    },
    "Diamond": {
        "color": "#1F6FEB",            # Luxury blue
        "gradient_from": "#A9C8FF",
        "gradient_to": "#1F6FEB",
        "border": "#155CC4",
        "text_on": "#0B2C66",
        "icon": "💎",
        "label": "Diamond",
    },
}

TIER_ORDER = ["Gold", "Platinum", "Diamond"]


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------
def get_selected_tier() -> Optional[str]:
    """Return the currently active tier filter ("Gold"/"Platinum"/"Diamond")
    or None when no tier is selected (= "show all tiers")."""
    return st.session_state.get(SELECTED_TIER_KEY)


def set_selected_tier(tier: Optional[str]) -> None:
    if tier not in (None, "Gold", "Platinum", "Diamond"):
        return
    st.session_state[SELECTED_TIER_KEY] = tier


def toggle_tier(tier: str) -> None:
    """Click handler: select if different, clear if same."""
    if tier not in ("Gold", "Platinum", "Diamond"):
        return
    current = st.session_state.get(SELECTED_TIER_KEY)
    st.session_state[SELECTED_TIER_KEY] = None if current == tier else tier


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------
def apply_tier_filter(df: pd.DataFrame, tier_col: str = "plan_tier") -> pd.DataFrame:
    """Return ``df`` filtered to the active tier (no-op when no tier is set
    or when the column is missing)."""
    tier = get_selected_tier()
    if tier is None or df.empty or tier_col not in df.columns:
        return df
    return df[df[tier_col] == tier]


def tier_filter_badge() -> Optional[str]:
    """Return a short label like ' (filtered to Gold members)' for callers
    that want to annotate page headings. Returns None when no tier is set."""
    tier = get_selected_tier()
    if tier is None:
        return None
    return f" · filtered to **{tier}** members"
