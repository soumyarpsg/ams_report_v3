"""Native (Plotly + Streamlit) Rewards Intelligence dashboard.

Light theme · gold + silver palette. Every chart is **clickable**: select a
bar / slice / segment and a download button appears to export just that
portion of the data (mobile number, store code, store name, region, tier, etc.).
Filters also drive a full filtered-CSV export.

Reads straight from ``ams_report_cache`` so it stays fast on 100K+ rows.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Light / gold-silver palette
# ---------------------------------------------------------------------------
GOLD = "#C9A227"
GOLD_SOFT = "#E6C766"
GOLD_DEEP = "#9C7A18"
SILVER = "#9AA3AD"
SILVER_SOFT = "#C7CDD4"
PLATINUM = "#7E8B99"
DIAMOND = "#6FA8C7"
INK = "#2A2410"
GRID = "#EAE2C8"
SEQ = [GOLD, SILVER, GOLD_DEEP, PLATINUM, GOLD_SOFT, DIAMOND, "#8A7320"]
TIER_COLORS = {"Gold": GOLD, "Platinum": PLATINUM, "Diamond": DIAMOND, "Other": SILVER}

EXPORT_COLS = [
    "msr_number", "customer_name", "plan_tier", "enrollment_status",
    "store_code", "store_name", "region", "city",
    "enroll_month_label", "channel", "shopper_behaviour",
    "bill_value", "mtd_cashback_earned", "mtd_cashback_earned_liq",
    "mtd_redemption", "liq_gross_sales",
]


def _style(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK, size=13), title=dict(font=dict(color=INK, size=15)),
        colorway=SEQ, margin=dict(l=10, r=10, t=44, b=10), height=height,
        xaxis=dict(gridcolor=GRID, linecolor="#D9CFB0", tickfont=dict(color=INK)),
        yaxis=dict(gridcolor=GRID, linecolor="#D9CFB0", tickfont=dict(color=INK)),
        legend=dict(font=dict(color=INK)),
    )
    return fig


_MONTH_FMT = "%b-%y"


def _msort(labels: pd.Series) -> pd.Series:
    return pd.to_datetime(labels, format=_MONTH_FMT, errors="coerce")


# ---------------------------------------------------------------------------
# Click-to-download plumbing
# ---------------------------------------------------------------------------
def _points(event):
    try:
        sel = getattr(event, "selection", None) or event.get("selection", {})
        return sel.get("points", []) if sel else []
    except Exception:
        return []


def _seg_download(st, event, source_df, col, key, fname_prefix, value_from="x"):
    """If a chart point was clicked, filter source_df[col]==clicked value and
    offer a CSV of the standard export fields for just that segment."""
    pts = _points(event)
    if not pts:
        st.caption("💡 Click a segment above to download only that portion.")
        return
    val = pts[0].get(value_from) or pts[0].get("label") or pts[0].get("x")
    if val is None:
        return
    rows = source_df[source_df[col].astype(str) == str(val)]
    cols = [c for c in EXPORT_COLS if c in rows.columns]
    out = rows[cols] if cols else rows
    st.info(f"🔎 Selected **{col} = {val}** — {len(out):,} records.")
    st.download_button(
        f"⬇️ Download '{val}' segment ({len(out):,} rows)",
        data=out.to_csv(index=False).encode("utf-8"),
        file_name=f"{fname_prefix}_{str(val).replace(' ','_').replace('/','-')}"
                  f"_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv", key=key)


# ---------------------------------------------------------------------------
def render(st, df: pd.DataFrame, kpi_card, fmt_int, fmt_inr,
           reporting_month: str | None = None) -> None:
    if df is None or df.empty:
        st.warning("Report cache is empty. Trigger a rebuild from the Upload page.")
        return

    df = df.copy()
    for c in ["bill_value", "eligible_bill_value", "mtd_cashback_earned",
              "mtd_cashback_earned_liq", "mtd_redemption", "ytd_cashback_earned",
              "ytd_redemption", "incremental_sales", "lost_sales", "current_nob",
              "past_nob", "past_ams", "liq_gross_sales"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    reporting_month = reporting_month or _latest_month(df)

    with st.expander("Filters", expanded=False):
        c1, c2, c3 = st.columns(3)
        regions = sorted([r for r in df.get("region", pd.Series(dtype=str)).dropna().unique() if r])
        sel_regions = c1.multiselect("Region", regions, default=regions, key="ri_region")
        tiers = sorted([t for t in df.get("plan_tier", pd.Series(dtype=str)).dropna().unique() if t])
        sel_tiers = c2.multiselect("Tier", tiers, default=tiers, key="ri_tier")
        months = sorted([m for m in df.get("enroll_month_label", pd.Series(dtype=str)).dropna().unique() if m],
                        key=lambda x: pd.to_datetime(x, format=_MONTH_FMT, errors="coerce"))
        sel_months = c3.multiselect("Enrolment Month", months, default=months, key="ri_month")

    fdf = df
    if sel_regions:
        fdf = fdf[fdf["region"].isin(sel_regions)]
    if sel_tiers:
        fdf = fdf[fdf["plan_tier"].isin(sel_tiers)]
    if sel_months:
        fdf = fdf[fdf["enroll_month_label"].isin(sel_months)]
    if fdf.empty:
        st.warning("No rows match the selected filters.")
        return

    # Filtered export
    exp_cols = [c for c in EXPORT_COLS if c in fdf.columns]
    st.download_button(
        f"⬇️ Download current filtered data ({len(fdf):,} rows)",
        data=fdf[exp_cols].to_csv(index=False).encode("utf-8"),
        file_name=f"rewards_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv", key="ri_filtered_dl")

    total_cust = len(fdf)
    shopped = int((fdf["shopper_behaviour"] == "Shopped").sum()) if "shopper_behaviour" in fdf else 0
    shopped_pct = (shopped / total_cust * 100) if total_cust else 0
    bill = float(fdf["bill_value"].sum()) if "bill_value" in fdf else 0
    cb = float(fdf["mtd_cashback_earned"].sum()) if "mtd_cashback_earned" in fdf else 0
    liq_cb = float(fdf["mtd_cashback_earned_liq"].sum()) if "mtd_cashback_earned_liq" in fdf else 0
    incr = float(fdf["incremental_sales"].sum()) if "incremental_sales" in fdf else 0

    r1 = st.columns(4)
    r1[0].markdown(kpi_card("Enrolled Customers", fmt_int(total_cust), accent=True), unsafe_allow_html=True)
    r1[1].markdown(kpi_card("Shopped This Month", fmt_int(shopped), f"{shopped_pct:.1f}% of base"), unsafe_allow_html=True)
    r1[2].markdown(kpi_card("MTD Bill Value", fmt_inr(bill)), unsafe_allow_html=True)
    r1[3].markdown(kpi_card("MTD Incremental Sales", fmt_inr(incr)), unsafe_allow_html=True)
    st.markdown("&nbsp;")
    r2 = st.columns(4)
    r2[0].markdown(kpi_card("MTD Cashback", fmt_inr(cb), accent=True), unsafe_allow_html=True)
    r2[1].markdown(kpi_card("MTD Liquor Cashback", fmt_inr(liq_cb), delta="Diamond · 1% of liq sales"), unsafe_allow_html=True)
    r2[2].markdown(kpi_card("MTD Redemption", fmt_inr(float(fdf.get("mtd_redemption", pd.Series([0])).sum()))), unsafe_allow_html=True)
    r2[3].markdown(kpi_card("Reporting Month", reporting_month or "—"), unsafe_allow_html=True)
    st.markdown("&nbsp;")

    t_over, t_return, t_store, t_cash, t_geo, t_slab, t_data = st.tabs(
        ["📈 Overview", "🔁 Return Rate", "🏬 Stores", "💰 Cashback & Sales",
         "🗺️ Geography", "📊 Slab Matrix", "🔎 Data Explorer"])

    with t_over:
        _overview(st, fdf)
    with t_return:
        _return_rate(st, fdf, reporting_month, kpi_card, fmt_int)
    with t_store:
        _stores(st, fdf, fmt_inr)
    with t_cash:
        _cashback(st, fdf)
    with t_geo:
        _geography(st, fdf)
    with t_slab:
        _slab_matrix(st, fdf, kpi_card, fmt_int)
    with t_data:
        _data_explorer(st, fdf)


def _latest_month(df: pd.DataFrame) -> str:
    if "enroll_month_label" not in df.columns:
        return ""
    m = pd.to_datetime(df["enroll_month_label"], format=_MONTH_FMT, errors="coerce").dropna()
    return m.max().strftime(_MONTH_FMT) if not m.empty else ""


def _overview(st, df) -> None:
    st.caption("Every chart below is clickable — select a bar or slice to export just that group.")
    c1, c2 = st.columns(2)
    with c1:
        g = df.groupby("enroll_month_label").size().reset_index(name="customers")
        g["k"] = _msort(g["enroll_month_label"]); g = g.sort_values("k")
        fig = px.bar(g, x="enroll_month_label", y="customers", title="Enrolments by Month")
        fig.update_traces(marker_color=GOLD)
        ev = st.plotly_chart(_style(fig), use_container_width=True, on_select="rerun", key="ov_month")
        _seg_download(st, ev, df, "enroll_month_label", "ov_month_dl", "enrolments")
    with c2:
        if "channel" in df.columns:
            ch = df["channel"].replace("", "Unknown").value_counts().reset_index()
            ch.columns = ["channel", "count"]
            fig2 = px.pie(ch, names="channel", values="count", title="Channel Mix", hole=0.55)
            fig2.update_traces(marker=dict(colors=SEQ))
            ev2 = st.plotly_chart(_style(fig2), use_container_width=True, on_select="rerun", key="ov_channel")
            _seg_download(st, ev2, df, "channel", "ov_channel_dl", "channel", value_from="label")

    c3, c4 = st.columns(2)
    with c3:
        if "plan_tier" in df.columns:
            tg = df["plan_tier"].value_counts().reset_index(); tg.columns = ["tier", "count"]
            fig3 = px.bar(tg, x="tier", y="count", color="tier", color_discrete_map=TIER_COLORS, title="Members by Tier")
            fig3.update_layout(showlegend=False)
            ev3 = st.plotly_chart(_style(fig3), use_container_width=True, on_select="rerun", key="ov_tier")
            _seg_download(st, ev3, df, "plan_tier", "ov_tier_dl", "tier")
    with c4:
        if "bill_slab" in df.columns:
            bs = df["bill_slab"].value_counts().reset_index(); bs.columns = ["slab", "count"]
            fig4 = px.bar(bs, x="slab", y="count", title="Bill Slab Distribution")
            fig4.update_traces(marker_color=SILVER)
            ev4 = st.plotly_chart(_style(fig4), use_container_width=True, on_select="rerun", key="ov_slab")
            _seg_download(st, ev4, df, "bill_slab", "ov_slab_dl", "bill_slab")


def _return_rate(st, df, reporting_month, kpi_card, fmt_int) -> None:
    st.caption("**Existing** = enrolled before the reporting month · **Return Rate** = existing who shopped ÷ existing.")
    rm = pd.to_datetime(reporting_month, format=_MONTH_FMT, errors="coerce")
    enr = pd.to_datetime(df.get("enroll_month_label"), format=_MONTH_FMT, errors="coerce")
    existing_mask = (enr < rm) if pd.notna(rm) else pd.Series(False, index=df.index)
    existing = df[existing_mask]
    n_exist = len(existing)
    returned = int((existing.get("shopper_behaviour") == "Shopped").sum()) if n_exist else 0
    rate = (returned / n_exist * 100) if n_exist else 0
    new_cust = int((enr == rm).sum()) if pd.notna(rm) else 0

    k = st.columns(4)
    k[0].markdown(kpi_card("Existing Customers", fmt_int(n_exist), accent=True), unsafe_allow_html=True)
    k[1].markdown(kpi_card("Returned (Shopped)", fmt_int(returned)), unsafe_allow_html=True)
    k[2].markdown(kpi_card("Return Rate", f"{rate:.1f}%"), unsafe_allow_html=True)
    k[3].markdown(kpi_card("New Customers", fmt_int(new_cust)), unsafe_allow_html=True)

    if "shopper_behaviour" in df.columns:
        beh = df["shopper_behaviour"].replace("", "Unknown").value_counts().reset_index()
        beh.columns = ["behaviour", "count"]
        fig = px.pie(beh, names="behaviour", values="count", hole=0.5,
                     title="Shopped vs Not Shopped (click a slice to download)",
                     color="behaviour",
                     color_discrete_map={"Shopped": GOLD, "Not Shopped": SILVER, "Unknown": SILVER_SOFT})
        ev = st.plotly_chart(_style(fig, 360), use_container_width=True, on_select="rerun", key="rr_beh")
        _seg_download(st, ev, df, "shopper_behaviour", "rr_beh_dl", "behaviour", value_from="label")


def _stores(st, df, fmt_inr) -> None:
    if "store_name" not in df.columns:
        return
    g = (df.groupby(["store_code", "store_name"])
         .agg(customers=("msr_number", "count"), bill=("bill_value", "sum"),
              cashback=("mtd_cashback_earned", "sum")).reset_index()
         .sort_values("bill", ascending=False).head(20))
    g["label"] = g["store_name"].where(g["store_name"] != "", g["store_code"])
    fig = px.bar(g.sort_values("bill"), x="bill", y="label", orientation="h",
                 title="Top 20 Stores by MTD Bill Value (click a bar to download that store)")
    fig.update_traces(marker_color=GOLD)
    ev = st.plotly_chart(_style(fig, 560), use_container_width=True, on_select="rerun", key="st_store")
    # store chart click -> map label back to store rows
    pts = _points(ev)
    if pts:
        lbl = pts[0].get("y") or pts[0].get("label")
        rows = df[(df["store_name"] == lbl) | (df["store_code"] == lbl)]
        cols = [c for c in EXPORT_COLS if c in rows.columns]
        st.info(f"🔎 Store **{lbl}** — {len(rows):,} members.")
        st.download_button(f"⬇️ Download store '{lbl}' ({len(rows):,} rows)",
                           data=rows[cols].to_csv(index=False).encode("utf-8"),
                           file_name=f"store_{str(lbl).replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv", key="st_store_dl")
    else:
        st.caption("💡 Click a store bar to download that store's members.")
    show = g[["store_code", "store_name", "customers", "bill", "cashback"]].copy()
    show.columns = ["Store Code", "Store Name", "Customers", "MTD Bill", "MTD Cashback"]
    st.dataframe(show, use_container_width=True, hide_index=True)


def _cashback(st, df) -> None:
    c1, c2 = st.columns(2)
    with c1:
        g = (df.groupby("enroll_month_label")
             .agg(cashback=("mtd_cashback_earned", "sum"), redemption=("mtd_redemption", "sum")).reset_index())
        g["k"] = _msort(g["enroll_month_label"]); g = g.sort_values("k")
        fig = go.Figure()
        fig.add_bar(x=g["enroll_month_label"], y=g["cashback"], name="Cashback", marker_color=GOLD)
        fig.add_bar(x=g["enroll_month_label"], y=g["redemption"], name="Redemption", marker_color=SILVER)
        fig.update_layout(barmode="group", title="Cashback vs Redemption by Month")
        st.plotly_chart(_style(fig), use_container_width=True)
    with c2:
        if "mtd_cashback_earned_liq" in df.columns:
            gl = df.groupby("enroll_month_label")["mtd_cashback_earned_liq"].sum().reset_index()
            gl["k"] = _msort(gl["enroll_month_label"]); gl = gl.sort_values("k")
            fig2 = px.bar(gl, x="enroll_month_label", y="mtd_cashback_earned_liq",
                          title="Liquor Cashback (Diamond, 1% of Liq Sales)")
            fig2.update_traces(marker_color=DIAMOND)
            st.plotly_chart(_style(fig2), use_container_width=True)
    if {"incremental_sales", "lost_sales"}.issubset(df.columns):
        fig3 = go.Figure(go.Bar(x=["Incremental Sales", "Lost Sales"],
                                y=[float(df["incremental_sales"].sum()), float(df["lost_sales"].sum())],
                                marker_color=[GOLD, SILVER]))
        fig3.update_layout(title="Incremental vs Lost Sales (MTD)")
        st.plotly_chart(_style(fig3), use_container_width=True)


def _geography(st, df) -> None:
    if "region" not in df.columns:
        return
    g = (df.groupby("region").agg(customers=("msr_number", "count"),
                                  cashback=("mtd_cashback_earned", "sum"),
                                  bill=("bill_value", "sum")).reset_index())
    g = g[g["region"] != ""].sort_values("bill", ascending=False)
    fig = px.bar(g.sort_values("bill"), x="bill", y="region", orientation="h",
                 title="MTD Bill Value by Region (click a bar to download that region)")
    fig.update_traces(marker_color=GOLD)
    ev = st.plotly_chart(_style(fig, 460), use_container_width=True, on_select="rerun", key="geo_region")
    _seg_download(st, ev, df, "region", "geo_region_dl", "region", value_from="y")


def _slab_matrix(st, df, kpi_card, fmt_int) -> None:
    if not {"past_ams_slab", "current_ams_slab"}.issubset(df.columns):
        st.info("Slab columns not available."); return
    from config import AMS_SLABS
    order = [s[0] for s in AMS_SLABS]; idx = {s: i for i, s in enumerate(order)}
    sub = df[df["past_ams_slab"].isin(order) & df["current_ams_slab"].isin(order)]
    pi = sub["past_ams_slab"].map(idx); ci = sub["current_ams_slab"].map(idx)
    upgraded = int((ci > pi).sum()); downgraded = int((ci < pi).sum()); stayed = int((ci == pi).sum())
    total = max(upgraded + downgraded + stayed, 1)
    k = st.columns(3)
    k[0].markdown(kpi_card("Upgraded", fmt_int(upgraded), f"{upgraded/total*100:.1f}%", accent=True), unsafe_allow_html=True)
    k[1].markdown(kpi_card("Stayed Same", fmt_int(stayed), f"{stayed/total*100:.1f}%"), unsafe_allow_html=True)
    k[2].markdown(kpi_card("Downgraded", fmt_int(downgraded), f"{downgraded/total*100:.1f}%"), unsafe_allow_html=True)
    mat = pd.crosstab(df["past_ams_slab"], df["current_ams_slab"]).reindex(index=order, columns=order, fill_value=0)
    fig = px.imshow(mat, text_auto=True, aspect="auto", color_continuous_scale="YlOrBr",
                    labels=dict(x="Current Slab", y="Past 6M Slab", color="Members"),
                    title="AMS Slab Transition Matrix")
    st.plotly_chart(_style(fig, 560), use_container_width=True)


def _data_explorer(st, df) -> None:
    st.caption(f"{len(df):,} rows · paginated for speed.")
    page_size = st.selectbox("Rows per page", [50, 100, 250, 500], index=1, key="ri_pagesize")
    n_pages = max(1, (len(df) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=n_pages, value=1, step=1, key="ri_page")
    start = (int(page) - 1) * page_size
    view_cols = list(dict.fromkeys([c for c in EXPORT_COLS if c in df.columns]))
    st.dataframe(df[view_cols].iloc[start:start + page_size], use_container_width=True, hide_index=True)
