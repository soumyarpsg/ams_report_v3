"""Plotly chart builders for the Loyalty KPI page.

Each builder takes a DataFrame (already filtered by the caller — tier card
filter + sidebar filters applied upstream) and returns a Plotly Figure.
Builders are pure: same inputs → same outputs, safe to wrap with caching.

Sections covered (mapped to the spec):
    A. enrolment_trend_by_month
    B. enrolment_trend_by_region
    C. shopped_vs_not_shopped
    D. top_stores_by_tier
    E. channel_of_enrollment
    F. bill_value_slab
    G. cashback_earn_rate_trend
    H. redemption_rate_charts
    I. monthly_active_members_trend (needs raw customer_trend; see helpers)
    J. avg_purchase_frequency
    K. avg_monthly_spend_by_dim
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import AMS_SLABS, BRAND_DARK, BRAND_RED
from util_filters import TIER_ORDER, TIER_THEME


# ---------------------------------------------------------------------------
# Shared visual config
# ---------------------------------------------------------------------------
TIER_COLOR_MAP = {t: TIER_THEME[t]["color"] for t in TIER_ORDER}

DEFAULT_LAYOUT = dict(
    margin=dict(l=10, r=10, t=44, b=10),
    height=360,
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#1F1F2E"),
    title_font=dict(size=14, color="#1F1F2E"),
    legend=dict(
        orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5,
        font=dict(size=11),
    ),
)


def _apply_layout(fig: go.Figure, **overrides) -> go.Figure:
    layout = {**DEFAULT_LAYOUT, **overrides}
    fig.update_layout(**layout)
    fig.update_xaxes(gridcolor="#F0F0F4", zerolinecolor="#F0F0F4")
    fig.update_yaxes(gridcolor="#F0F0F4", zerolinecolor="#F0F0F4")
    return fig


def _empty_figure(message: str = "No data") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False,
                       font=dict(color="#9090A0", size=13),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return _apply_layout(fig)


def _month_sort_key(label_series: pd.Series) -> pd.Series:
    """Convert mmm-yy labels (e.g. 'May-26') to sortable timestamps."""
    return pd.to_datetime(label_series, format="%b-%y", errors="coerce")


# ===========================================================================
# A. Enrolment Trend by Month  (line, separate colors by tier)
# ===========================================================================
def enrolment_trend_by_month(df: pd.DataFrame, single_tier: Optional[str] = None) -> go.Figure:
    """Monthly enrolments. When ``single_tier`` is set we plot one line for
    that tier only; otherwise three lines (one per tier)."""
    if df.empty or "enroll_month_label" not in df.columns:
        return _empty_figure()

    if single_tier:
        slice_df = df[df["plan_tier"] == single_tier]
        if slice_df.empty:
            return _empty_figure()
        agg = (slice_df.groupby("enroll_month_label").size()
               .reset_index(name="Enrolments"))
        agg["sort"] = _month_sort_key(agg["enroll_month_label"])
        agg = agg.sort_values("sort")
        fig = px.line(
            agg, x="enroll_month_label", y="Enrolments",
            title=f"Enrolment trend by month — {single_tier}",
            markers=True,
            color_discrete_sequence=[TIER_THEME[single_tier]["color"]],
        )
        fig.update_traces(line=dict(width=3))
    else:
        agg = (df.groupby(["enroll_month_label", "plan_tier"]).size()
               .reset_index(name="Enrolments"))
        agg["sort"] = _month_sort_key(agg["enroll_month_label"])
        agg = agg.sort_values("sort")
        fig = px.line(
            agg, x="enroll_month_label", y="Enrolments", color="plan_tier",
            title="Enrolment trend by month — split by tier",
            markers=True,
            color_discrete_map=TIER_COLOR_MAP,
            category_orders={"plan_tier": TIER_ORDER},
        )
        fig.update_traces(line=dict(width=2.5))

    fig.update_xaxes(title_text="Month")
    fig.update_yaxes(title_text="Enrolments")
    return _apply_layout(fig)


def enrolment_trend_by_month_table(df: pd.DataFrame) -> pd.DataFrame:
    """Columns: Month, Tier, Enrolments, Active Members, Growth %."""
    if df.empty or "enroll_month_label" not in df.columns:
        return pd.DataFrame(columns=["Month", "Tier", "Enrolments", "Active Members", "Growth %"])

    g = (df.groupby(["enroll_month_label", "plan_tier"])
         .agg(Enrolments=("msr_number", "count"),
              **{"Active Members": ("shopper_behaviour",
                                    lambda s: int((s == "Shopped").sum()))})
         .reset_index()
         .rename(columns={"enroll_month_label": "Month", "plan_tier": "Tier"}))
    g["__sort"] = _month_sort_key(g["Month"])
    g = g.sort_values(["__sort", "Tier"])

    # Growth % vs previous month, per tier
    g["Growth %"] = (
        g.groupby("Tier")["Enrolments"]
         .pct_change()
         .multiply(100)
         .round(1)
    )
    g["Growth %"] = g["Growth %"].fillna(0.0)
    return g.drop(columns=["__sort"])


# ===========================================================================
# B. Enrolment Trend by Region  (stacked bar, tier-coloured)
# ===========================================================================
def enrolment_by_region(df: pd.DataFrame) -> go.Figure:
    if df.empty or "region" not in df.columns:
        return _empty_figure()
    agg = (df.groupby(["region", "plan_tier"]).size()
           .reset_index(name="Members"))
    if agg.empty:
        return _empty_figure()
    fig = px.bar(
        agg, x="region", y="Members", color="plan_tier",
        title="Enrolment by region (stacked by tier)",
        color_discrete_map=TIER_COLOR_MAP,
        category_orders={"plan_tier": TIER_ORDER},
    )
    fig.update_xaxes(title_text="Region")
    fig.update_yaxes(title_text="Members")
    return _apply_layout(fig)


def enrolment_by_region_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "region" not in df.columns:
        return pd.DataFrame(
            columns=["Region", "Total Members", "Gold", "Platinum", "Diamond", "Active Members"]
        )
    pivot = (df.pivot_table(index="region", columns="plan_tier",
                            values="msr_number", aggfunc="count",
                            fill_value=0)
             .reindex(columns=TIER_ORDER, fill_value=0))
    pivot["Total Members"] = pivot.sum(axis=1)
    active = (df[df["shopper_behaviour"] == "Shopped"]
              .groupby("region")["msr_number"].count())
    pivot["Active Members"] = active.reindex(pivot.index, fill_value=0).astype(int)
    out = (pivot.reset_index()
           .rename(columns={"region": "Region"})
           [["Region", "Total Members", "Gold", "Platinum", "Diamond", "Active Members"]])
    return out.sort_values("Total Members", ascending=False).reset_index(drop=True)


# ===========================================================================
# C. Shopped vs Not Shopped in Current Month  (donut + counts)
# ===========================================================================
def shopped_vs_not_shopped(df: pd.DataFrame) -> go.Figure:
    if df.empty or "shopper_behaviour" not in df.columns:
        return _empty_figure()
    counts = df["shopper_behaviour"].value_counts().reset_index()
    counts.columns = ["Behaviour", "Count"]
    fig = px.pie(
        counts, names="Behaviour", values="Count",
        title="Shopped vs Not Shopped (current month)",
        color="Behaviour",
        color_discrete_map={"Shopped": BRAND_RED, "Not Shopped": "#B5B5C2"},
        hole=0.55,
    )
    fig.update_traces(
        textinfo="percent+label",
        textposition="outside",
        marker=dict(line=dict(color="white", width=2)),
    )
    return _apply_layout(fig, height=380)


def shopped_vs_not_shopped_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Tier", "Shopped Members", "Not Shopped Members",
                                     "Shopped %", "AMS"])
    g = (df.groupby("plan_tier")
         .agg(**{
             "Shopped Members": ("shopper_behaviour",
                                 lambda s: int((s == "Shopped").sum())),
             "Not Shopped Members": ("shopper_behaviour",
                                     lambda s: int((s == "Not Shopped").sum())),
             "AMS": ("bill_value", "mean"),
         })
         .reset_index()
         .rename(columns={"plan_tier": "Tier"}))
    total = g["Shopped Members"] + g["Not Shopped Members"]
    g["Shopped %"] = (g["Shopped Members"] / total.replace(0, np.nan) * 100).round(1).fillna(0)
    g["AMS"] = g["AMS"].round(2)
    g["Tier"] = pd.Categorical(g["Tier"], categories=TIER_ORDER, ordered=True)
    return g.sort_values("Tier")[["Tier", "Shopped Members", "Not Shopped Members",
                                  "Shopped %", "AMS"]]


# ===========================================================================
# D. Top 15 Stores by Members — horizontal stacked bar (tier breakdown)
# ===========================================================================
def top_stores_by_tier(df: pd.DataFrame, n: int = 15) -> go.Figure:
    if df.empty or "store_code" not in df.columns:
        return _empty_figure()
    # Pick top N stores by overall member count
    totals = df.groupby(["store_code", "store_name"]).size().reset_index(name="total")
    top = totals.sort_values("total", ascending=False).head(n)
    top_codes = top["store_code"].tolist()
    if not top_codes:
        return _empty_figure()

    sub = df[df["store_code"].isin(top_codes)]
    pivot = (sub.groupby(["store_code", "store_name", "plan_tier"]).size()
             .reset_index(name="Members"))
    pivot["label"] = pivot["store_code"].fillna("") + " · " + pivot["store_name"].fillna("")
    # Maintain order: stores with biggest total at top of horizontal chart
    order = (totals.set_index("store_code").reindex(top_codes))
    label_order = (top["store_code"].fillna("") + " · " + top["store_name"].fillna("")).tolist()

    fig = px.bar(
        pivot, x="Members", y="label", color="plan_tier", orientation="h",
        title=f"Top {n} stores by members (stacked by tier)",
        color_discrete_map=TIER_COLOR_MAP,
        category_orders={"plan_tier": TIER_ORDER, "label": list(reversed(label_order))},
    )
    fig.update_xaxes(title_text="Members")
    fig.update_yaxes(title_text="Store")
    return _apply_layout(fig, height=520)


def top_stores_by_tier_table(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    if df.empty or "store_code" not in df.columns:
        return pd.DataFrame(columns=["Store Code", "Store Name", "Gold Members",
                                     "Platinum Members", "Diamond Members",
                                     "Total Members", "AMS"])
    pivot = (df.pivot_table(index=["store_code", "store_name"], columns="plan_tier",
                            values="msr_number", aggfunc="count", fill_value=0)
             .reindex(columns=TIER_ORDER, fill_value=0))
    pivot["Total Members"] = pivot.sum(axis=1)
    ams = df.groupby(["store_code", "store_name"])["bill_value"].mean().round(2)
    pivot["AMS"] = ams.reindex(pivot.index).fillna(0)
    out = (pivot.reset_index()
           .rename(columns={"store_code": "Store Code", "store_name": "Store Name",
                            "Gold": "Gold Members", "Platinum": "Platinum Members",
                            "Diamond": "Diamond Members"}))
    out = out.sort_values("Total Members", ascending=False).head(n).reset_index(drop=True)
    return out[["Store Code", "Store Name", "Gold Members", "Platinum Members",
                "Diamond Members", "Total Members", "AMS"]]


# ===========================================================================
# E. Channel of Enrollment  (donut)
# ===========================================================================
def channel_of_enrollment(df: pd.DataFrame) -> go.Figure:
    if df.empty or "channel" not in df.columns:
        return _empty_figure()
    ch = (df["channel"].fillna("Unknown").replace("", "Unknown")
          .value_counts().reset_index())
    ch.columns = ["Channel", "Members"]
    fig = px.pie(
        ch, names="Channel", values="Members", hole=0.55,
        title="Channel of enrollment",
        color_discrete_sequence=[BRAND_RED, "#1F1F2E", "#8C95A1", "#FFA17A", "#1F6FEB"],
    )
    fig.update_traces(textinfo="percent+label", textposition="outside",
                      marker=dict(line=dict(color="white", width=2)))
    return _apply_layout(fig, height=380)


def channel_of_enrollment_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "channel" not in df.columns:
        return pd.DataFrame(columns=["Channel", "Members", "Active Members", "% of Total"])
    base = df.copy()
    base["channel"] = base["channel"].fillna("Unknown").replace("", "Unknown")
    g = (base.groupby("channel")
         .agg(Members=("msr_number", "count"),
              **{"Active Members": ("shopper_behaviour",
                                    lambda s: int((s == "Shopped").sum()))})
         .reset_index()
         .rename(columns={"channel": "Channel"}))
    total = g["Members"].sum()
    g["% of Total"] = (g["Members"] / total * 100).round(1) if total else 0
    return g.sort_values("Members", ascending=False).reset_index(drop=True)


# ===========================================================================
# F. Bill Value Slab  (using current_ams_slab — 14-slab AMS Transition buckets)
# ===========================================================================
def bill_value_slab(df: pd.DataFrame) -> go.Figure:
    if df.empty or "current_ams_slab" not in df.columns:
        return _empty_figure()
    slab_order = [s[0] for s in AMS_SLABS]
    counts = df["current_ams_slab"].value_counts().reindex(slab_order, fill_value=0).reset_index()
    counts.columns = ["Slab", "Members"]
    fig = px.bar(
        counts, x="Slab", y="Members",
        title="Bill-value slab distribution (current month)",
        color_discrete_sequence=[BRAND_RED],
    )
    fig.update_traces(marker_line_color="white", marker_line_width=1)
    fig.update_xaxes(title_text="Bill Value Slab (₹)", tickangle=-30)
    fig.update_yaxes(title_text="Members")
    return _apply_layout(fig, height=420)


def bill_value_slab_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "current_ams_slab" not in df.columns:
        return pd.DataFrame(columns=["Bill Value Slab", "Members", "% of Total",
                                     "Gold", "Platinum", "Diamond", "Avg Bill"])
    slab_order = [s[0] for s in AMS_SLABS]
    pivot = (df.pivot_table(index="current_ams_slab", columns="plan_tier",
                            values="msr_number", aggfunc="count", fill_value=0)
             .reindex(index=slab_order, columns=TIER_ORDER, fill_value=0))
    pivot["Members"] = pivot.sum(axis=1)
    total = pivot["Members"].sum()
    pivot["% of Total"] = (pivot["Members"] / total * 100).round(1) if total else 0
    avg = df.groupby("current_ams_slab")["bill_value"].mean().round(2)
    pivot["Avg Bill"] = avg.reindex(pivot.index).fillna(0)
    pivot = pivot.reset_index().rename(columns={"current_ams_slab": "Bill Value Slab"})
    return pivot[["Bill Value Slab", "Members", "% of Total",
                  "Gold", "Platinum", "Diamond", "Avg Bill"]]


# ===========================================================================
# G. Cashback Earn Rate
# ===========================================================================
def cashback_earn_rate_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total_earned": 0, "eligible_bill": 0, "earn_rate_pct": 0.0}
    earned = pd.to_numeric(df.get("mtd_cashback_earned", pd.Series(dtype=float)),
                           errors="coerce").fillna(0).sum()
    eligible = pd.to_numeric(df.get("eligible_bill_value", pd.Series(dtype=float)),
                             errors="coerce").fillna(0).sum()
    rate = (earned / eligible * 100) if eligible > 0 else 0.0
    return {"total_earned": float(earned), "eligible_bill": float(eligible),
            "earn_rate_pct": float(rate)}


def cashback_by_region(df: pd.DataFrame) -> go.Figure:
    """Bar chart of MTD cashback earned vs YTD cashback earned by region —
    used as the "trend" surface for cashback when monthly trend data is not
    available in the cached report."""
    if df.empty or "region" not in df.columns:
        return _empty_figure()
    g = (df.groupby("region")
         .agg(**{"MTD Earned": ("mtd_cashback_earned", "sum"),
                 "YTD Earned": ("ytd_cashback_earned", "sum")})
         .reset_index())
    long = g.melt(id_vars="region", var_name="Metric", value_name="Amount")
    fig = px.bar(long, x="region", y="Amount", color="Metric", barmode="group",
                 title="Cashback earned — MTD vs YTD by region",
                 color_discrete_map={"MTD Earned": BRAND_RED, "YTD Earned": "#1F1F2E"})
    fig.update_xaxes(title_text="Region")
    fig.update_yaxes(title_text="Cashback (₹)")
    return _apply_layout(fig)


def cashback_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Region", "Eligible Bill", "MTD Earned",
                                     "Earn Rate %", "YTD Earned"])
    g = (df.groupby("region")
         .agg(**{"Eligible Bill": ("eligible_bill_value", "sum"),
                 "MTD Earned": ("mtd_cashback_earned", "sum"),
                 "YTD Earned": ("ytd_cashback_earned", "sum")})
         .reset_index().rename(columns={"region": "Region"}))
    g["Earn Rate %"] = (g["MTD Earned"] / g["Eligible Bill"].replace(0, np.nan) * 100).round(2)
    g["Earn Rate %"] = g["Earn Rate %"].fillna(0)
    for col in ("Eligible Bill", "MTD Earned", "YTD Earned"):
        g[col] = g[col].round(2)
    return g.sort_values("MTD Earned", ascending=False).reset_index(drop=True)[
        ["Region", "Eligible Bill", "MTD Earned", "Earn Rate %", "YTD Earned"]
    ]


# ===========================================================================
# H. Redemption Rate
# ===========================================================================
def redemption_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total_earned": 0, "total_redeemed": 0, "redemption_pct": 0.0,
                "redeemers": 0, "non_redeemers": 0}
    earned_ytd = pd.to_numeric(df.get("ytd_cashback_earned", pd.Series(dtype=float)),
                               errors="coerce").fillna(0).sum()
    redeemed_ytd = pd.to_numeric(df.get("ytd_redemption", pd.Series(dtype=float)),
                                 errors="coerce").fillna(0).sum()
    redeemers = int((pd.to_numeric(df.get("ytd_redemption", pd.Series(dtype=float)),
                                   errors="coerce").fillna(0) > 0).sum())
    non = len(df) - redeemers
    pct = (redeemed_ytd / earned_ytd * 100) if earned_ytd > 0 else 0.0
    return {"total_earned": float(earned_ytd), "total_redeemed": float(redeemed_ytd),
            "redemption_pct": float(pct), "redeemers": redeemers, "non_redeemers": non}


def redeemed_vs_unredeemed(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure()
    redeemers = int((pd.to_numeric(df["ytd_redemption"], errors="coerce").fillna(0) > 0).sum())
    non = len(df) - redeemers
    data = pd.DataFrame({"Status": ["Redeemed", "Did Not Redeem"],
                         "Members": [redeemers, non]})
    fig = px.pie(data, names="Status", values="Members", hole=0.55,
                 title="Redeemed vs Not Redeemed (YTD)",
                 color="Status",
                 color_discrete_map={"Redeemed": "#1F6FEB", "Did Not Redeem": "#D8D8E0"})
    fig.update_traces(textinfo="percent+label", textposition="outside",
                      marker=dict(line=dict(color="white", width=2)))
    return _apply_layout(fig, height=360)


def redemption_by_region(df: pd.DataFrame) -> go.Figure:
    if df.empty or "region" not in df.columns:
        return _empty_figure()
    g = (df.groupby("region")
         .agg(**{"YTD Earned": ("ytd_cashback_earned", "sum"),
                 "YTD Redeemed": ("ytd_redemption", "sum")})
         .reset_index())
    long = g.melt(id_vars="region", var_name="Metric", value_name="Amount")
    fig = px.bar(long, x="region", y="Amount", color="Metric", barmode="group",
                 title="YTD Cashback Earned vs Redeemed — by region",
                 color_discrete_map={"YTD Earned": "#1F1F2E", "YTD Redeemed": "#1F6FEB"})
    fig.update_xaxes(title_text="Region")
    fig.update_yaxes(title_text="Amount (₹)")
    return _apply_layout(fig)


def redemption_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Region", "YTD Earned", "YTD Redeemed",
                                     "Redemption %", "Active Users", "Avg Spend"])
    g = (df.groupby("region")
         .agg(**{"YTD Earned": ("ytd_cashback_earned", "sum"),
                 "YTD Redeemed": ("ytd_redemption", "sum"),
                 "Active Users": ("shopper_behaviour",
                                  lambda s: int((s == "Shopped").sum())),
                 "Avg Spend": ("bill_value", "mean")})
         .reset_index().rename(columns={"region": "Region"}))
    g["Redemption %"] = (g["YTD Redeemed"] / g["YTD Earned"].replace(0, np.nan) * 100).round(2)
    g["Redemption %"] = g["Redemption %"].fillna(0)
    for c in ("YTD Earned", "YTD Redeemed", "Avg Spend"):
        g[c] = g[c].round(2)
    return g.sort_values("YTD Earned", ascending=False).reset_index(drop=True)[
        ["Region", "YTD Earned", "YTD Redeemed", "Redemption %", "Active Users", "Avg Spend"]
    ]


# ===========================================================================
# I. Monthly Active Members  (needs raw customer_trend; see helpers below)
# ===========================================================================
def monthly_active_members_chart(monthly_df: pd.DataFrame) -> go.Figure:
    """Caller passes a pre-aggregated frame with columns: Month, Active Members."""
    if monthly_df is None or monthly_df.empty:
        return _empty_figure("Trend data not loaded — upload Customer Trend file.")
    fig = px.area(
        monthly_df, x="Month", y="Active Members",
        title="Monthly active members (members with ≥1 transaction)",
        color_discrete_sequence=[BRAND_RED],
    )
    fig.update_traces(line=dict(width=2.5), opacity=0.85)
    fig.update_xaxes(title_text="Month")
    fig.update_yaxes(title_text="Active Members")
    return _apply_layout(fig)


# ===========================================================================
# J. Average Purchase Frequency
# ===========================================================================
def avg_purchase_frequency(df: pd.DataFrame) -> go.Figure:
    """Distribution of current_nob (visits this month) across customers."""
    if df.empty or "current_nob" not in df.columns:
        return _empty_figure()
    nob = pd.to_numeric(df["current_nob"], errors="coerce").fillna(0)
    bins = [-0.5, 0.5, 1.5, 2.5, 4.5, 7.5, 999]
    labels = ["0", "1", "2", "3–4", "5–7", "8+"]
    binned = pd.cut(nob, bins=bins, labels=labels)
    counts = binned.value_counts().reindex(labels, fill_value=0).reset_index()
    counts.columns = ["Visits", "Members"]
    fig = px.bar(counts, x="Visits", y="Members",
                 title="Visit frequency distribution (current month)",
                 color_discrete_sequence=[BRAND_RED])
    fig.update_xaxes(title_text="Visits this month")
    fig.update_yaxes(title_text="Members")
    return _apply_layout(fig)


def avg_purchase_frequency_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Tier", "Active Members", "Avg Visits (Current)",
                                     "Avg Visits (Past 6M)", "Avg Bill", "AMS"])
    active = df[df["shopper_behaviour"] == "Shopped"]
    g = (active.groupby("plan_tier")
         .agg(**{"Active Members": ("msr_number", "count"),
                 "Avg Visits (Current)": ("current_nob", "mean"),
                 "Avg Visits (Past 6M)": ("past_nob", "mean"),
                 "Avg Bill": ("bill_value", "mean"),
                 "AMS": ("past_ams", "mean")})
         .reset_index().rename(columns={"plan_tier": "Tier"}))
    for c in ("Avg Visits (Current)", "Avg Visits (Past 6M)", "Avg Bill", "AMS"):
        g[c] = g[c].round(2)
    g["Tier"] = pd.Categorical(g["Tier"], categories=TIER_ORDER, ordered=True)
    return g.sort_values("Tier")[["Tier", "Active Members", "Avg Visits (Current)",
                                  "Avg Visits (Past 6M)", "Avg Bill", "AMS"]]


# ===========================================================================
# K. Average Monthly Spend — tier / region / top stores
# ===========================================================================
def ams_by_tier(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure()
    g = (df.groupby("plan_tier")["bill_value"].mean().round(2)
         .reindex(TIER_ORDER).reset_index())
    g.columns = ["Tier", "AMS"]
    fig = px.bar(g, x="Tier", y="AMS", color="Tier",
                 title="Average monthly spend — by tier",
                 color_discrete_map=TIER_COLOR_MAP,
                 text_auto=".0f")
    fig.update_xaxes(title_text="Tier")
    fig.update_yaxes(title_text="Avg Monthly Spend (₹)")
    fig.update_traces(textposition="outside")
    return _apply_layout(fig, showlegend=False)


def ams_by_region(df: pd.DataFrame) -> go.Figure:
    if df.empty or "region" not in df.columns:
        return _empty_figure()
    g = df.groupby("region")["bill_value"].mean().round(2).reset_index()
    g.columns = ["Region", "AMS"]
    fig = px.bar(g.sort_values("AMS", ascending=False), x="Region", y="AMS",
                 title="Average monthly spend — by region",
                 color_discrete_sequence=[BRAND_DARK],
                 text_auto=".0f")
    fig.update_xaxes(title_text="Region")
    fig.update_yaxes(title_text="Avg Monthly Spend (₹)")
    fig.update_traces(textposition="outside")
    return _apply_layout(fig)


def ams_by_top_stores(df: pd.DataFrame, n: int = 15) -> go.Figure:
    if df.empty or "store_code" not in df.columns:
        return _empty_figure()
    g = (df.groupby(["store_code", "store_name"])
         .agg(AMS=("bill_value", "mean"),
              Members=("msr_number", "count"))
         .reset_index())
    g["AMS"] = g["AMS"].round(2)
    g["label"] = g["store_code"].fillna("") + " · " + g["store_name"].fillna("")
    g = g.sort_values("AMS", ascending=False).head(n).sort_values("AMS")
    fig = px.bar(g, x="AMS", y="label", orientation="h",
                 title=f"Top {n} stores by AMS",
                 color_discrete_sequence=[BRAND_RED],
                 hover_data={"Members": True})
    fig.update_xaxes(title_text="AMS (₹)")
    fig.update_yaxes(title_text="Store")
    return _apply_layout(fig, height=520)


def ams_table(df: pd.DataFrame) -> pd.DataFrame:
    """One detailed table aggregating AMS at tier × region × store."""
    if df.empty:
        return pd.DataFrame(columns=["Tier", "Region", "Store Code", "Store Name",
                                     "Members", "Active Members", "AMS"])
    g = (df.groupby(["plan_tier", "region", "store_code", "store_name"])
         .agg(Members=("msr_number", "count"),
              **{"Active Members": ("shopper_behaviour",
                                    lambda s: int((s == "Shopped").sum()))},
              AMS=("bill_value", "mean"))
         .reset_index()
         .rename(columns={"plan_tier": "Tier", "region": "Region",
                          "store_code": "Store Code", "store_name": "Store Name"}))
    g["AMS"] = g["AMS"].round(2)
    g["Tier"] = pd.Categorical(g["Tier"], categories=TIER_ORDER, ordered=True)
    return g.sort_values(["Tier", "AMS"], ascending=[True, False]).reset_index(drop=True)
