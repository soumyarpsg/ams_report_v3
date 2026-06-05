"""Loyalty KPI page — comprehensive tier-aware analytics view.

Layout
------
1. Header strip
2. Tier filter cards (same component as Overview)
3. Sidebar-style filter expander (Region / Format / Cluster / Enrolment Month)
4. KPI sections A–K, each with:
     · Plotly chart wrapped in a subtle card
     · Detailed table (st.dataframe)
     · Download row (CSV / Excel / PDF)
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd
import streamlit as st

import db
import chart_loyalty as lc
from ui_exports import render_download_row
from ui_tier_cards import render_tier_cards
from util_filters import (
    apply_tier_filter,
    get_selected_tier,
)


# ---------------------------------------------------------------------------
# Cached lookups for things we read from disk
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_customer_trend(version: str) -> pd.DataFrame:
    """Pull the long-format customer_trend table — used by the Monthly Active
    Members chart. Cached so we read SQLite once per data version."""
    try:
        df = db.fetch_df("SELECT mobile_no, month_start, sales, nob FROM customer_trend")
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["month_start"] = pd.to_datetime(df["month_start"], errors="coerce")
    return df.dropna(subset=["month_start"])


def _monthly_active_members(trend_df: pd.DataFrame,
                            member_mobile_ids: pd.Series) -> pd.DataFrame:
    """Aggregate monthly active members from raw trend data, scoped to the
    set of mobile numbers in the currently filtered membership view."""
    if trend_df.empty or len(member_mobile_ids) == 0:
        return pd.DataFrame(columns=["Month", "Active Members"])
    scoped = trend_df[
        trend_df["mobile_no"].astype(str).isin(member_mobile_ids.astype(str))
        & (pd.to_numeric(trend_df["sales"], errors="coerce").fillna(0) > 0)
    ]
    if scoped.empty:
        return pd.DataFrame(columns=["Month", "Active Members"])
    g = (scoped.groupby(pd.Grouper(key="month_start", freq="MS"))["mobile_no"]
         .nunique()
         .reset_index())
    g.columns = ["MonthDate", "Active Members"]
    g["Month"] = g["MonthDate"].dt.strftime("%b-%y")
    return g[["Month", "Active Members"]]


def _monthly_active_table(trend_df: pd.DataFrame,
                          member_mobile_ids: pd.Series,
                          full_member_df: pd.DataFrame) -> pd.DataFrame:
    """Columns: Month, Active Members, Repeat Members, Frequency, AMS."""
    if trend_df.empty:
        return pd.DataFrame(columns=["Month", "Active Members", "Repeat Members",
                                     "Frequency", "AMS"])
    scoped = trend_df[
        trend_df["mobile_no"].astype(str).isin(member_mobile_ids.astype(str))
        & (pd.to_numeric(trend_df["sales"], errors="coerce").fillna(0) > 0)
    ].copy()
    if scoped.empty:
        return pd.DataFrame(columns=["Month", "Active Members", "Repeat Members",
                                     "Frequency", "AMS"])
    g = (scoped.groupby(pd.Grouper(key="month_start", freq="MS"))
         .agg(**{"Active Members": ("mobile_no", "nunique"),
                 "Frequency": ("nob", "mean"),
                 "AMS": ("sales", "mean")})
         .reset_index())
    # Repeat members = members with >1 transaction that month (nob > 1)
    repeat = (scoped[pd.to_numeric(scoped["nob"], errors="coerce").fillna(0) > 1]
              .groupby(pd.Grouper(key="month_start", freq="MS"))["mobile_no"]
              .nunique()
              .rename("Repeat Members"))
    g = g.merge(repeat, left_on="month_start", right_index=True, how="left")
    g["Repeat Members"] = g["Repeat Members"].fillna(0).astype(int)
    g["Frequency"] = g["Frequency"].round(2)
    g["AMS"] = g["AMS"].round(2)
    g["Month"] = g["month_start"].dt.strftime("%b-%y")
    return g[["Month", "Active Members", "Repeat Members", "Frequency", "AMS"]] \
        .sort_values("Month", key=lambda s: pd.to_datetime(s, format="%b-%y",
                                                           errors="coerce")) \
        .reset_index(drop=True)


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------
def _section_h(num: str, title: str) -> None:
    st.markdown(
        f'<div class="kpi-section-h"><span class="num">{num}</span>'
        f'<span class="title">{title}</span></div>',
        unsafe_allow_html=True,
    )


def _chart_card(fig) -> None:
    st.markdown('<div class="kpi-chart-card">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    st.markdown('</div>', unsafe_allow_html=True)


def _table_with_downloads(title: str, df: pd.DataFrame, base_name: str, key: str,
                          sheet_name: str = "Data",
                          height: int = 320) -> None:
    """Title strip → 3 download buttons → dataframe."""
    st.markdown(
        f'<div class="table-title-row"><span class="lbl">📋 {title}</span></div>',
        unsafe_allow_html=True,
    )
    render_download_row(df, base_name=base_name, key=key, sheet_name=sheet_name,
                        pdf_title=title)
    if df is None or df.empty:
        st.info("No rows match the current filters.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


# ---------------------------------------------------------------------------
# Filter expander (shared scope: region / format / cluster / month)
# ---------------------------------------------------------------------------
def _filter_expander(df: pd.DataFrame) -> pd.DataFrame:
    """Reusable Region/Format/Cluster/Enrolment-Month filter. Plan tier is
    deliberately NOT here — that lives on the tier-cards row above."""
    with st.expander("Filters", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        regions = sorted(r for r in df["region"].dropna().unique() if r)
        formats = sorted(f for f in df["format"].dropna().unique() if f)
        clusters = sorted(c for c in df["cluster"].dropna().unique() if c)
        months_df = (df.dropna(subset=["enroll_month"])
                       .drop_duplicates("enroll_month")
                       .sort_values("enroll_month")[
                           ["enroll_month", "enroll_month_label"]])
        month_options = months_df["enroll_month_label"].tolist()

        sel_regions = f1.multiselect("Region", regions, default=regions,
                                     key="lk_regions")
        sel_formats = f2.multiselect("Format", formats, default=formats,
                                     key="lk_formats")
        sel_clusters = f3.multiselect("Cluster", clusters, default=clusters,
                                      key="lk_clusters")
        sel_months = f4.multiselect("Enrolment Month", month_options,
                                    default=month_options, key="lk_months")

    fdf = df[
        df["region"].isin(sel_regions)
        & df["format"].isin(sel_formats)
        & df["cluster"].isin(sel_clusters)
        & df["enroll_month_label"].isin(sel_months)
    ]
    return fdf


# ---------------------------------------------------------------------------
# Main page entry point — called by app.py router
# ---------------------------------------------------------------------------
def render_loyalty_kpi_page(
    header_fn: Callable[[str, str], None],
    has_data_fn: Callable[[], bool],
    cached_ams_report_fn: Callable[[str], pd.DataFrame],
    report_version_fn: Callable[[], str],
    current_period_label_fn: Callable[[], str],
) -> None:
    """Render the Loyalty KPI page. Callbacks are passed in so this page
    stays decoupled from app.py's internals."""
    header_fn(
        "Loyalty KPI",
        f"Tier-level membership & spend KPIs · current period {current_period_label_fn()}",
    )

    if not has_data_fn():
        st.info("No data has been uploaded yet. An admin can upload files via the **Upload Data** menu.")
        return

    df = cached_ams_report_fn(report_version_fn())
    if df.empty:
        st.warning("Report cache is empty. Trigger a rebuild from the Upload page.")
        return

    # ---- Sidebar-style filters (region / format / cluster / month) -------
    base_filtered = _filter_expander(df)
    if base_filtered.empty:
        st.warning("No customers match the selected filters.")
        return

    # ---- Tier cards (computed on region/format/cluster-filtered slice) ---
    st.markdown("### Tier filter")
    render_tier_cards(base_filtered, key_prefix="lk")

    # Apply tier filter to get the working frame for charts/tables.
    fdf = apply_tier_filter(base_filtered)
    selected_tier = get_selected_tier()

    if fdf.empty:
        st.warning(f"No {selected_tier} members match the selected filters.")
        return

    # ---- Pre-load trend data (used by Section I) -------------------------
    trend = _load_customer_trend(report_version_fn())

    # =====================================================================
    # A. Enrolment Trend by Month
    # =====================================================================
    _section_h("A", "Enrolment trend by month")
    fig = lc.enrolment_trend_by_month(fdf, single_tier=selected_tier)
    _chart_card(fig)
    _table_with_downloads(
        "Enrolment trend — monthly breakdown",
        lc.enrolment_trend_by_month_table(fdf),
        base_name="Enrolment_Trend_By_Month",
        key="a_month",
        sheet_name="Enrolment by Month",
    )

    # =====================================================================
    # B. Enrolment Trend by Region
    # =====================================================================
    _section_h("B", "Enrolment by region")
    _chart_card(lc.enrolment_by_region(fdf))
    _table_with_downloads(
        "Region-wise enrolment",
        lc.enrolment_by_region_table(fdf),
        base_name="Enrolment_By_Region",
        key="b_region",
        sheet_name="Enrolment by Region",
    )

    # =====================================================================
    # C. Shopped vs Not Shopped (current month)
    # =====================================================================
    _section_h("C", "Shopped vs Not Shopped (current month)")
    _chart_card(lc.shopped_vs_not_shopped(fdf))
    _table_with_downloads(
        "Shopped vs not shopped — by tier",
        lc.shopped_vs_not_shopped_table(fdf),
        base_name="Shopped_vs_Not_Shopped",
        key="c_shop",
        sheet_name="Shopped vs Not",
    )

    # =====================================================================
    # D. Top 15 Stores by Members (stacked by tier)
    # =====================================================================
    _section_h("D", "Top 15 stores by members (tier breakdown)")
    _chart_card(lc.top_stores_by_tier(fdf, n=15))
    _table_with_downloads(
        "Top stores",
        lc.top_stores_by_tier_table(fdf, n=15),
        base_name="Top_15_Stores_By_Tier",
        key="d_stores",
        sheet_name="Top Stores",
        height=420,
    )

    # =====================================================================
    # E. Channel of Enrollment
    # =====================================================================
    _section_h("E", "Channel of enrollment")
    _chart_card(lc.channel_of_enrollment(fdf))
    _table_with_downloads(
        "Channel breakdown",
        lc.channel_of_enrollment_table(fdf),
        base_name="Channel_Of_Enrollment",
        key="e_channel",
        sheet_name="Channel",
    )

    # =====================================================================
    # F. Bill Value Slab (14-bucket AMS Transition slabs)
    # =====================================================================
    _section_h("F", "Bill-value slab distribution")
    _chart_card(lc.bill_value_slab(fdf))
    _table_with_downloads(
        "Bill-value slab — members & tier breakdown",
        lc.bill_value_slab_table(fdf),
        base_name="Bill_Value_Slab",
        key="f_slab",
        sheet_name="Bill Value Slabs",
        height=420,
    )

    # =====================================================================
    # G. Cashback Earn Rate
    # =====================================================================
    _section_h("G", "Cashback earn rate")
    cb = lc.cashback_earn_rate_metrics(fdf)
    g1, g2, g3 = st.columns(3)
    g1.metric("Total Cashback Earned (MTD)", f"₹{cb['total_earned']:,.0f}")
    g2.metric("Eligible Bill (MTD)", f"₹{cb['eligible_bill']:,.0f}")
    g3.metric("Earn Rate %", f"{cb['earn_rate_pct']:.2f}%")
    _chart_card(lc.cashback_by_region(fdf))
    _table_with_downloads(
        "Cashback earn — by region",
        lc.cashback_table(fdf),
        base_name="Cashback_Earn_Rate",
        key="g_cb",
        sheet_name="Cashback Earn",
    )

    # =====================================================================
    # H. Redemption Rate
    # =====================================================================
    _section_h("H", "Redemption rate")
    rm = lc.redemption_metrics(fdf)
    h1, h2, h3 = st.columns(3)
    h1.metric("Redemption %", f"{rm['redemption_pct']:.2f}%",
              help="YTD Redeemed ÷ YTD Earned")
    h2.metric("Members Redeemed", f"{rm['redeemers']:,}")
    h3.metric("YTD Redeemed", f"₹{rm['total_redeemed']:,.0f}")
    rh1, rh2 = st.columns(2)
    with rh1:
        _chart_card(lc.redeemed_vs_unredeemed(fdf))
    with rh2:
        _chart_card(lc.redemption_by_region(fdf))
    _table_with_downloads(
        "Redemption — by region",
        lc.redemption_table(fdf),
        base_name="Redemption_Rate",
        key="h_rd",
        sheet_name="Redemption",
    )

    # =====================================================================
    # I. Monthly Active Members
    # =====================================================================
    _section_h("I", "Monthly active members")
    monthly = _monthly_active_members(trend, fdf["msr_number"])
    _chart_card(lc.monthly_active_members_chart(monthly))
    _table_with_downloads(
        "Monthly active members",
        _monthly_active_table(trend, fdf["msr_number"], fdf),
        base_name="Monthly_Active_Members",
        key="i_active",
        sheet_name="Monthly Active",
    )

    # =====================================================================
    # J. Average Purchase Frequency
    # =====================================================================
    _section_h("J", "Average purchase frequency")
    j1, j2 = st.columns(2)
    if "current_nob" in fdf.columns:
        avg_visits = pd.to_numeric(
            fdf.loc[fdf["shopper_behaviour"] == "Shopped", "current_nob"],
            errors="coerce"
        ).fillna(0).mean()
    else:
        avg_visits = 0.0
    active_count = int((fdf["shopper_behaviour"] == "Shopped").sum())
    j1.metric("Avg visits per active member", f"{avg_visits:.2f}")
    j2.metric("Active members", f"{active_count:,}")
    _chart_card(lc.avg_purchase_frequency(fdf))
    _table_with_downloads(
        "Visit frequency — by tier",
        lc.avg_purchase_frequency_table(fdf),
        base_name="Avg_Purchase_Frequency",
        key="j_freq",
        sheet_name="Visit Frequency",
    )

    # =====================================================================
    # K. Average Monthly Spend
    # =====================================================================
    _section_h("K", "Average monthly spend (AMS)")
    k1, k2 = st.columns(2)
    with k1:
        _chart_card(lc.ams_by_tier(fdf))
    with k2:
        _chart_card(lc.ams_by_region(fdf))
    _chart_card(lc.ams_by_top_stores(fdf, n=15))
    _table_with_downloads(
        "AMS detail — tier × region × store",
        lc.ams_table(fdf),
        base_name="Average_Monthly_Spend",
        key="k_ams",
        sheet_name="AMS Detail",
        height=480,
    )
