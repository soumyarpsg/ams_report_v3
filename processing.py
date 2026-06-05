"""AMS Migration Report computation.

Produces the wide table requested by the analyst: for every enrolled customer,
join Membership ↔ Shopping ↔ Customer Trend ↔ Redemption with the lookup, and
derive past / current / post-loyalty KPIs and slabs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Tuple

import numpy as np
import pandas as pd

from config import AMS_SLABS, BILL_SLABS, LOYALTY_START_YEAR, LOYALTY_START_MONTH
import db


# ---------------------------------------------------------------------------
# Slab helpers
# ---------------------------------------------------------------------------
def _bill_slab(value: float) -> str:
    if pd.isna(value) or value <= 0:
        return "<=25K"
    for label, lo, hi in BILL_SLABS:
        lo_ok = lo is None or value > lo
        hi_ok = hi is None or value <= hi
        if lo_ok and hi_ok:
            return label
    return BILL_SLABS[-1][0]


def _ams_slab(value: float) -> str:
    # Treat blanks, zeros and negatives (returns / reversals) as the lowest
    # slab — otherwise negatives fall through every range check and end up
    # bucketed as "No Data", which is misleading on the dashboard.
    if pd.isna(value) or value <= 0:
        return "0 to 500"
    for label, lo, hi in AMS_SLABS:
        lo_ok = (lo is None) or value > lo
        hi_ok = (hi is None) or value <= hi
        # The first slab "0 to 500" should include 0 — special-case
        if label == "0 to 500" and value <= 500:
            return label
        if lo_ok and hi_ok:
            return label
    return "No Data"


def _mtd_cashback(eligible_bill_value: float) -> float:
    if pd.isna(eligible_bill_value) or eligible_bill_value <= 0:
        return 0.0
    v = eligible_bill_value
    if 3301 <= v <= 4000:
        return 100.0
    if 4001 <= v <= 5000:
        return round(v * 0.04, 2)
    if 5001 <= v <= 10000:
        return min(round(v * 0.06, 2), 600.0)
    if v > 10000:
        return 600.0
    return 0.0


# ---------------------------------------------------------------------------
# Past-window helpers
# ---------------------------------------------------------------------------
def _past_window(enroll_period: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) of the 6-month window strictly *before* enrollment."""
    end = enroll_period - pd.offsets.MonthBegin(1)        # month before enrol
    start = end - pd.offsets.MonthBegin(5)                 # 5 months before that
    return start, end


# ---------------------------------------------------------------------------
# Period discovery helpers (used by the UI to populate the month picker)
# ---------------------------------------------------------------------------
def available_periods() -> list[pd.Timestamp]:
    """Return a sorted list of unique month-start Timestamps present in any
    of the loaded source tables (shopping / customer trend / redemption).

    The UI uses this to populate the "Report Month" selector so the analyst
    can choose which month to build the report for, instead of defaulting to
    the auto-detected max across all files (which can be off by one if, e.g.,
    redemption credits for April land on 1-May).
    """
    periods: set[pd.Timestamp] = set()
    try:
        shopping = db.fetch_df("SELECT DISTINCT period FROM shopping")
        if not shopping.empty:
            periods.update(pd.to_datetime(shopping["period"], errors="coerce").dropna())
    except Exception:
        pass
    try:
        trend = db.fetch_df("SELECT DISTINCT month_start FROM customer_trend")
        if not trend.empty:
            periods.update(pd.to_datetime(trend["month_start"], errors="coerce").dropna())
    except Exception:
        pass
    try:
        redemption = db.fetch_df("SELECT DISTINCT txn_period FROM redemption")
        if not redemption.empty:
            periods.update(pd.to_datetime(redemption["txn_period"], errors="coerce").dropna())
    except Exception:
        pass

    return sorted(periods)


def smart_default_period() -> pd.Timestamp | None:
    """Pick a sensible default report month.

    Preference order:
      1. Latest month for which Shopping has data (this is what an analyst
         actually means by "the month I'm reporting on").
      2. Latest month for which Customer Trend has data.
      3. Latest month for which Redemption has data.
    """
    for table, col in (("shopping", "period"),
                       ("customer_trend", "month_start"),
                       ("redemption", "txn_period")):
        try:
            df = db.fetch_df(f"SELECT MAX({col}) AS m FROM {table}")
            if not df.empty and pd.notna(df["m"].iloc[0]):
                return pd.to_datetime(df["m"].iloc[0])
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Core build
# ---------------------------------------------------------------------------
def build_ams_report(report_period: str | pd.Timestamp | None = None) -> pd.DataFrame:
    """Compute the full AMS Migration Report by joining the five data sources.

    Args:
        report_period: Optional override for the "current" period the report
            covers. Accepts a ``YYYY-MM-DD`` string or a ``pd.Timestamp`` (any
            day in the target month — it's normalised to month-start). If
            ``None``, falls back to the legacy behaviour of taking the max
            period across shopping / trend / redemption.

    Returns a DataFrame with the canonical column names listed in the spec, in
    the order requested. Stores it back in ``ams_report_cache`` for fast reads.
    """
    membership = db.fetch_df("SELECT * FROM membership")
    shopping = db.fetch_df("SELECT * FROM shopping")
    redemption = db.fetch_df("SELECT * FROM redemption")
    trend = db.fetch_df("SELECT * FROM customer_trend")
    stores = db.fetch_df(
        "SELECT store_code, store_name, region, cluster, city, format FROM stores"
    )

    if membership.empty:
        return pd.DataFrame()

    # Safety: tolerate membership rows that pre-date the new columns.
    for col, default in (("registration_type", "N"),
                         ("enrollment_status", "New Acquisition"),
                         ("transaction_date", ""),
                         ("txn_month", "")):
        if col not in membership.columns:
            membership[col] = default

    # ----- Determine the "current" period -------------------------------
    if report_period is not None:
        # User-supplied — normalise to first-of-month timestamp.
        current_period = pd.to_datetime(report_period).to_period("M").to_timestamp()
    else:
        # Legacy auto-detect: latest period across all loaded sources.
        candidate_periods: list[pd.Timestamp] = []
        if not shopping.empty:
            candidate_periods.append(pd.to_datetime(shopping["period"]).max())
        if not trend.empty:
            candidate_periods.append(pd.to_datetime(trend["month_start"]).max())
        if not redemption.empty:
            candidate_periods.append(pd.to_datetime(redemption["txn_period"]).max())
        if not candidate_periods:
            return pd.DataFrame()
        current_period = max(candidate_periods)
    current_period_str = current_period.strftime("%Y-%m-%d")

    db.set_meta("current_period", current_period_str)
    db.set_meta(
        "current_period_label",
        current_period.strftime("%b-%y"),
    )
    db.set_meta(
        "report_built_at",
        datetime.utcnow().isoformat(timespec="seconds"),
    )

    # ----- Membership: collapse to ONE row per member (mobile) ----------
    # A member can appear several times in the membership file: the first
    # (earliest Start Date) record is the *original* enrolment; every later
    # record is a Renewal / Existing-Upgrade / Force-Upgrade of the SAME
    # member. We must NOT treat those later records as fresh enrolments —
    # doing so produced phantom "Jul-26 / Aug-26" enrolment months in the AMS
    # table (those are renewal terms that begin the day after the original
    # term ends).
    #
    # Collapse rule (per the analyst's spec):
    #   • Month of Enrolment  = month of the *earliest* Start Date (the old
    #     date), for everyone — renewers/upgraders keep their original month.
    #   • Tier                = the tier of the *latest* record (the tier they
    #     renewed / upgraded INTO) — "just change the tier name".
    #   • Start / End / Txn   = original Start Date, latest End Date (current
    #     validity), latest Transaction Date.
    #   • Status              = New Acquisition if the member has a single
    #     record, otherwise the registration type of their most recent
    #     renewal/upgrade action (R / EU / FE).
    membership = membership.copy()
    membership["start_date_dt"] = pd.to_datetime(membership["start_date"], errors="coerce")
    membership["end_date_dt"] = pd.to_datetime(membership["end_date"], errors="coerce")
    membership["txn_date_dt"] = pd.to_datetime(membership["transaction_date"], errors="coerce")

    # Stable order: by mobile then by start date (NaT start dates last).
    membership = membership.sort_values(
        ["mobile_no", "start_date_dt"], na_position="last"
    ).reset_index(drop=True)

    grp = membership.groupby("mobile_no", sort=False)
    n_records = grp["mobile_no"].transform("size")

    first_rows = grp.head(1).set_index("mobile_no")   # earliest = original
    last_rows = grp.tail(1).set_index("mobile_no")     # latest   = current

    # Most-recent renewal/upgrade action (any record after the first). A
    # later record tagged "N" is a fresh term begun after the previous one
    # expired — i.e. a Renewal — so we translate it to "R".
    later = membership[membership.groupby("mobile_no").cumcount() >= 1].copy()
    later["action_type"] = later["registration_type"].replace({"N": "R"})
    last_action = (
        later.dropna(subset=["action_type"])
        .groupby("mobile_no")
        .tail(1)
        .set_index("mobile_no")["action_type"]
    )

    # Build the collapsed per-member frame on the ORIGINAL (first) record so
    # store / channel / name reflect the enrolment, then overlay current tier
    # and validity from the latest record.
    latest = first_rows.copy()
    latest["plan_tier"] = last_rows["plan_tier"]          # renewed/upgraded tier
    latest["plan_cost"] = last_rows.get("plan_cost", latest.get("plan_cost"))
    if "plan_name" in last_rows.columns:
        latest["plan_name"] = last_rows["plan_name"]      # latest plan name
    latest["end_date"] = last_rows["end_date"]            # current validity end
    latest["end_date_dt"] = last_rows["end_date_dt"]
    latest["transaction_date"] = last_rows["transaction_date"]

    # Enrolment month always comes from the ORIGINAL start date.
    latest["enroll_month_dt"] = (
        latest["start_date_dt"].dt.to_period("M").dt.to_timestamp()
    )
    latest["enroll_month"] = latest["enroll_month_dt"].dt.strftime("%Y-%m-%d")

    # Registration tagging / status for the collapsed member.
    n_records_idx = n_records.groupby(membership["mobile_no"]).first()
    latest["n_records"] = n_records_idx
    has_action = last_action.reindex(latest.index)
    latest["registration_type"] = np.where(
        latest["n_records"].fillna(1) > 1,
        has_action.fillna("R").values,            # renewed/upgraded
        latest["registration_type"].values,       # single record -> keep (N)
    )
    from config import REGISTRATION_STATUS_MAP
    latest["enrollment_status"] = (
        pd.Series(latest["registration_type"], index=latest.index)
        .map(REGISTRATION_STATUS_MAP)
        .fillna("New Acquisition")
    )

    latest = latest.reset_index()  # bring mobile_no back as a column

    # ----- Current-month shopping aggregated per mobile -----------------
    if not shopping.empty:
        cur_shop = shopping[shopping["period"] == current_period_str]
        cur_shop = (
            cur_shop.groupby("mobile_no", as_index=False)
            .agg(bill_value=("total_bill_value", "sum"),
                 eligible_bill_value=("eligible_bill_value", "sum"))
        )
    else:
        cur_shop = pd.DataFrame(columns=["mobile_no", "bill_value", "eligible_bill_value"])

    # ----- Trend pivots --------------------------------------------------
    if not trend.empty:
        trend = trend.copy()
        trend["month_start_dt"] = pd.to_datetime(trend["month_start"])
    else:
        trend = pd.DataFrame(columns=["mobile_no", "month_start", "month_start_dt",
                                      "nob", "sales", "abv", "qty", "qpb"])

    # Current month trend stats per mobile
    cur_trend = trend[trend["month_start"] == current_period_str]
    cur_trend = cur_trend[["mobile_no", "nob", "qty"]].rename(
        columns={"nob": "current_nob", "qty": "current_qty"}
    )

    # ----- Redemption aggregates ----------------------------------------
    redemption = redemption.copy()
    if not redemption.empty:
        redemption["txn_period_dt"] = pd.to_datetime(redemption["txn_period"], errors="coerce")
        loyalty_start = pd.Timestamp(year=LOYALTY_START_YEAR, month=LOYALTY_START_MONTH, day=1)

        if "cashback_for" not in redemption.columns:
            redemption["cashback_for"] = "NON-LIQ"
        is_liq = redemption["cashback_for"].astype(str).str.upper() == "LIQ"

        ytd_mask = (redemption["txn_period_dt"] >= loyalty_start) & \
                   (redemption["txn_period_dt"] <= current_period)
        mtd_mask = redemption["txn_period_dt"] == current_period
        credit = redemption["transaction_type"] == "BALANCE CREDIT"
        redeem = redemption["transaction_type"] == "REDEMPTION"

        def _sum_by_mobile(mask, colname, make_abs=False):
            g = (
                redemption.loc[mask]
                .groupby("mobile_no", as_index=False)["transaction_amt"].sum()
                .rename(columns={"transaction_amt": colname})
            )
            if make_abs:
                g[colname] = g[colname].abs()
            return g

        # Cashback earned (BALANCE CREDIT) split LIQ vs NON-LIQ
        ytd_cashback = _sum_by_mobile(ytd_mask & credit & ~is_liq, "ytd_cashback_earned")
        ytd_cashback_liq = _sum_by_mobile(ytd_mask & credit & is_liq, "ytd_cashback_earned_liq")
        # Redemption split LIQ vs NON-LIQ (made positive)
        ytd_redemp = _sum_by_mobile(ytd_mask & redeem & ~is_liq, "ytd_redemption", make_abs=True)
        ytd_redemp_liq = _sum_by_mobile(ytd_mask & redeem & is_liq, "ytd_redemption_liq", make_abs=True)
        mtd_redemp = _sum_by_mobile(mtd_mask & redeem & ~is_liq, "mtd_redemption", make_abs=True)
        mtd_redemp_liq = _sum_by_mobile(mtd_mask & redeem & is_liq, "mtd_redemption_liq", make_abs=True)
        # MTD cashback earned LIQ (from the redemption file's tagged credits)
        mtd_cashback_liq = _sum_by_mobile(mtd_mask & credit & is_liq, "mtd_cashback_earned_liq")
    else:
        ytd_cashback = pd.DataFrame(columns=["mobile_no", "ytd_cashback_earned"])
        ytd_cashback_liq = pd.DataFrame(columns=["mobile_no", "ytd_cashback_earned_liq"])
        ytd_redemp = pd.DataFrame(columns=["mobile_no", "ytd_redemption"])
        ytd_redemp_liq = pd.DataFrame(columns=["mobile_no", "ytd_redemption_liq"])
        mtd_redemp = pd.DataFrame(columns=["mobile_no", "mtd_redemption"])
        mtd_redemp_liq = pd.DataFrame(columns=["mobile_no", "mtd_redemption_liq"])
        mtd_cashback_liq = pd.DataFrame(columns=["mobile_no", "mtd_cashback_earned_liq"])

    # ----- Past / Post-loyalty KPI calculation per mobile ---------------
    # We compute these in a vectorised way per enrollment month to avoid
    # walking 100K customers row-by-row.
    enroll_months = sorted(latest["enroll_month_dt"].dropna().unique())

    # Pre-bucket trend by mobile so we can slice fast
    if not trend.empty:
        trend_idx = trend.set_index(["mobile_no", "month_start_dt"]).sort_index()
    else:
        trend_idx = None

    past_records = []
    for em in enroll_months:
        em_ts = pd.Timestamp(em)
        win_start, win_end = _past_window(em_ts)
        post_start, post_end = em_ts, current_period

        members_em = latest.loc[latest["enroll_month_dt"] == em_ts, "mobile_no"]
        if members_em.empty or trend_idx is None:
            continue

        # Past window slice
        past_slice = trend.loc[
            (trend["month_start_dt"] >= win_start)
            & (trend["month_start_dt"] <= win_end)
            & (trend["mobile_no"].isin(members_em))
        ]
        # mean() over each metric ignores NaN — exactly what the user asked for
        past_g = (
            past_slice.groupby("mobile_no", as_index=False)
            .agg(past_ams=("sales", "mean"),
                 past_qty=("qty", "mean"),
                 past_nob=("nob", "mean"))
        )

        # Post-loyalty window slice (enrollment month → current month inclusive)
        post_slice = trend.loc[
            (trend["month_start_dt"] >= post_start)
            & (trend["month_start_dt"] <= post_end)
            & (trend["mobile_no"].isin(members_em))
        ]
        post_g = (
            post_slice.groupby("mobile_no", as_index=False)
            .agg(post_loyalty_ams=("sales", "mean"))
        )

        merged = past_g.merge(post_g, on="mobile_no", how="outer")
        past_records.append(merged)

    if past_records:
        past_df = pd.concat(past_records, ignore_index=True)
    else:
        past_df = pd.DataFrame(columns=["mobile_no", "past_ams", "past_qty", "past_nob",
                                        "post_loyalty_ams"])

    # ----- Stitch everything together -----------------------------------
    if "plan_name" not in latest.columns:
        latest["plan_name"] = ""
    out = latest[[
        "mobile_no", "name", "registered_store_code", "purchased_platform",
        "enroll_month", "plan_tier", "plan_name", "start_date", "end_date",
        "enrollment_status", "registration_type", "transaction_date",
    ]].rename(columns={
        "mobile_no": "msr_number",
        "name": "customer_name",
        "registered_store_code": "store_code",
        "purchased_platform": "channel",
    })

    out["enroll_month_dt"] = pd.to_datetime(out["enroll_month"], errors="coerce")
    out["enroll_month_label"] = out["enroll_month_dt"].dt.strftime("%b-%y")

    # Merge store master
    stores_ren = stores.rename(columns={
        "store_code": "store_code", "store_name": "store_name",
        "region": "region", "cluster": "cluster",
        "city": "city", "format": "format",
    })
    out = out.merge(stores_ren, on="store_code", how="left")

    # Merge current shopping
    out = out.merge(cur_shop, left_on="msr_number", right_on="mobile_no", how="left")
    out.drop(columns=["mobile_no"], inplace=True, errors="ignore")
    out["bill_value"] = out["bill_value"].fillna(0.0)
    out["eligible_bill_value"] = out["eligible_bill_value"].fillna(0.0)

    # Merge current trend (NOB / Qty)
    out = out.merge(cur_trend, left_on="msr_number", right_on="mobile_no", how="left")
    out.drop(columns=["mobile_no"], inplace=True, errors="ignore")
    out["current_nob"] = out["current_nob"].fillna(0.0)
    out["current_qty"] = out["current_qty"].fillna(0.0)

    # Merge past KPIs
    out = out.merge(past_df, left_on="msr_number", right_on="mobile_no", how="left")
    out.drop(columns=["mobile_no"], inplace=True, errors="ignore")
    for c in ("past_ams", "past_qty", "past_nob", "post_loyalty_ams"):
        if c in out.columns:
            out[c] = out[c].fillna(0.0)

    # Merge redemption KPIs (liq + non-liq)
    for d in (ytd_cashback, ytd_cashback_liq, ytd_redemp, ytd_redemp_liq,
              mtd_redemp, mtd_redemp_liq, mtd_cashback_liq):
        out = out.merge(d, left_on="msr_number", right_on="mobile_no", how="left")
        out.drop(columns=["mobile_no"], inplace=True, errors="ignore")
    for c in ("ytd_cashback_earned", "ytd_cashback_earned_liq",
              "ytd_redemption", "ytd_redemption_liq",
              "mtd_redemption", "mtd_redemption_liq", "mtd_cashback_earned_liq"):
        if c not in out.columns:
            out[c] = 0.0
        out[c] = out[c].fillna(0.0)

    # ----- Liquor sales (current month + YTD) per mobile ----------------
    liq_sales = db.fetch_df("SELECT * FROM liq_sales") if db.has_data("liq_sales") else pd.DataFrame()
    if not liq_sales.empty:
        liq_sales = liq_sales.copy()
        liq_sales["period_dt"] = pd.to_datetime(liq_sales["period"], errors="coerce")
        loyalty_start = pd.Timestamp(year=LOYALTY_START_YEAR, month=LOYALTY_START_MONTH, day=1)

        # Current-month liquor stats
        liq_cur = liq_sales[liq_sales["period"] == current_period_str]
        liq_g = (
            liq_cur.groupby("mobile_no", as_index=False)
            .agg(liq_gross_sales=("gross_sales", "sum"),
                 liq_nob=("nob", "sum"),
                 liq_qty=("billed_qty", "sum"))
        )
        out = out.merge(liq_g, left_on="msr_number", right_on="mobile_no", how="left")
        out.drop(columns=["mobile_no"], inplace=True, errors="ignore")

        # YTD liquor gross sales (loyalty start → current month inclusive)
        liq_ytd = liq_sales[(liq_sales["period_dt"] >= loyalty_start)
                            & (liq_sales["period_dt"] <= current_period)]
        liq_ytd_g = (
            liq_ytd.groupby("mobile_no", as_index=False)
            .agg(liq_gross_sales_ytd=("gross_sales", "sum"))
        )
        out = out.merge(liq_ytd_g, left_on="msr_number", right_on="mobile_no", how="left")
        out.drop(columns=["mobile_no"], inplace=True, errors="ignore")
    for c in ("liq_gross_sales", "liq_nob", "liq_qty", "liq_gross_sales_ytd"):
        if c not in out.columns:
            out[c] = 0.0
        out[c] = out[c].fillna(0.0)

    # ----- Liquor cashback = 1% of Liquor Gross Sales, DIAMOND members ONLY
    # Per the analyst spec, liquor cashback is NOT read from the redemption
    # file. It is computed as 1% of the member's liquor gross sales, and only
    # Diamond members earn it (Gold / Platinum get ₹0). MTD uses the current
    # month's liquor gross sales; YTD uses the loyalty-to-date liquor gross
    # sales.
    from config import LIQ_CASHBACK_RATE  # 0.01
    is_diamond = out["plan_tier"] == "Diamond"
    out["mtd_cashback_earned_liq"] = np.where(
        is_diamond,
        (pd.to_numeric(out["liq_gross_sales"], errors="coerce").fillna(0.0)
         * LIQ_CASHBACK_RATE).round(2),
        0.0,
    )
    out["ytd_cashback_earned_liq"] = np.where(
        is_diamond,
        (pd.to_numeric(out["liq_gross_sales_ytd"], errors="coerce").fillna(0.0)
         * LIQ_CASHBACK_RATE).round(2),
        0.0,
    )

    # ----- Liquor-buyer flag (mobile present in the 1-year base) --------
    liq_base = db.liq_base_mobiles()
    if liq_base:
        in_base = out["msr_number"].astype(str).isin(liq_base)
    else:
        in_base = pd.Series(False, index=out.index)
    out["is_existing_liq_buyer"] = np.where(in_base, "Yes", "No")
    # Diamond-only descriptive label (Existing vs New liquor buyer).
    out["liq_buyer_type"] = np.where(
        out["plan_tier"] == "Diamond",
        np.where(in_base, "Existing Liq Buyer", "New Liq Buyer"),
        "",
    )

    # ----- Derived fields ----------------------------------------------
    out["shopper_behaviour"] = np.where(out["bill_value"] > 0, "Shopped", "Not Shopped")
    out["bill_slab"] = out["bill_value"].apply(_bill_slab)

    out["mtd_cashback_earned"] = out["eligible_bill_value"].apply(_mtd_cashback)

    # Retail vs B2B: current-month bill value <= 25K -> Retail else B2B
    from config import RETAIL_B2B_THRESHOLD
    out["retail_b2b"] = np.where(
        out["bill_value"].fillna(0) <= RETAIL_B2B_THRESHOLD, "Retail", "B2B"
    )

    # Ratio fields with safe division (avoid eager numerator/0 in np.where)
    def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
        n = pd.to_numeric(num, errors="coerce")
        d = pd.to_numeric(den, errors="coerce")
        d_safe = d.where(d > 0, np.nan)
        return n / d_safe

    out["current_asp"] = _safe_div(out["bill_value"], out["current_qty"]).fillna(0.0)
    out["past_asp"] = _safe_div(out["past_ams"], out["past_qty"]).fillna(0.0)
    out["current_qpb"] = _safe_div(out["current_qty"], out["current_nob"]).fillna(0.0)
    out["past_qpb"] = _safe_div(out["past_qty"], out["past_nob"]).fillna(0.0)

    # Past / current AMS slabs
    out["past_ams_slab"] = out["past_ams"].apply(_ams_slab)
    # Current AMS slab is based on current month bill value
    out["current_ams_slab"] = out["bill_value"].apply(_ams_slab)

    # Customer type: past AMS == 0 -> New Buyer else Existing Buyer
    out["customer_type"] = np.where(
        pd.to_numeric(out["past_ams"], errors="coerce").fillna(0) == 0,
        "New Buyer", "Existing Buyer",
    )

    # Incremental / lost
    delta_sales = out["bill_value"] - out["past_ams"].fillna(0)
    out["incremental_sales"] = np.where(out["shopper_behaviour"] == "Shopped", delta_sales, 0.0)
    out["lost_sales"] = np.where(out["shopper_behaviour"] == "Not Shopped", delta_sales, 0.0)

    delta_nob = out["current_nob"] - out["past_nob"].fillna(0)
    out["incremental_nob"] = np.where(out["shopper_behaviour"] == "Shopped", delta_nob, 0.0)
    out["lost_nob"] = np.where(out["shopper_behaviour"] == "Not Shopped", delta_nob, 0.0)

    # Fill missing store-master fields with empty strings
    for c in ("store_name", "region", "cluster", "city", "format"):
        if c not in out.columns:
            out[c] = ""
        out[c] = out[c].fillna("")

    # ----- Order columns -----------------------------------------------
    out_cols = [
        "store_code", "store_name", "msr_number", "customer_name",
        "plan_name",
        "enroll_month", "enroll_month_label",
        "channel", "enrollment_status", "registration_type",
        "shopper_behaviour",
        "region", "city", "cluster",
        "retail_b2b", "customer_type", "format",
        "bill_value", "eligible_bill_value",
        "bill_slab", "is_existing_liq_buyer", "liq_buyer_type",
        "past_ams", "past_qty", "current_qty",
        "current_asp", "past_asp", "current_qpb", "past_qpb",
        "post_loyalty_ams", "past_ams_slab", "current_ams_slab",
        "mtd_cashback_earned", "mtd_cashback_earned_liq",
        "mtd_redemption", "mtd_redemption_liq",
        "ytd_cashback_earned", "ytd_cashback_earned_liq",
        "ytd_redemption", "ytd_redemption_liq",
        "liq_gross_sales", "liq_nob", "liq_qty",
        "incremental_sales", "incremental_nob", "past_nob", "current_nob",
        "lost_sales", "lost_nob",
        "plan_tier", "start_date", "end_date", "transaction_date",
    ]
    out = out[out_cols].copy()

    # ----- Persist cache -----------------------------------------------
    db.replace_table("ams_report_cache", out)

    return out


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------
# The analyst's required output template (format.csv). Each tuple is
# (internal_column, exact_display_header). The header strings — including the
# embedded line breaks and quirky spellings ("Eligable", trailing spaces) — are
# reproduced verbatim so the downloaded CSV is byte-compatible with the
# downstream process. "Liq Cashback" is inserted right after "Redemption Value"
# as requested; every remaining (liquor / YTD / date) column follows the
# template block.
_FORMAT_LAYOUT = [
    ("store_code", "Store_Code"),
    ("store_name", "Store Name"),
    ("msr_number", "Subscription\nSold"),
    ("customer_name", "C_NAME"),
    ("enroll_month_label", "Month of Purchase"),
    ("channel", "Channel"),
    ("plan_tier", "Tier"),
    ("registration_type", "Tagging"),
    ("enrollment_status", "R_Status"),
    ("retail_b2b", "B2B"),
    ("customer_type", "Customer\nType"),
    ("shopper_behaviour", "Shopper_Behaviour"),
    ("bill_slab", "Bill Slab"),
    ("region", "Region"),
    ("city", "City"),
    ("cluster", "Cluster"),
    ("format", "Format"),
    ("bill_value", "Bill Value"),
    ("eligible_bill_value", " Eligable Bill Value"),
    ("past_ams", "Past AMS"),
    ("past_qty", "Past\nBilled_Qty"),
    ("current_qty", "Current \nBilled_Qty"),
    ("current_asp", "Current \nASP"),
    ("past_asp", "Past \nASP"),
    ("current_qpb", "Current \nQPB"),
    ("past_qpb", "Past \nQPB"),
    ("post_loyalty_ams", "Post Loyalty AMS"),
    ("past_ams_slab", "Past AMS Slab"),
    ("current_ams_slab", "Current AMS Slab"),
    ("mtd_cashback_earned", "Cashback"),
    ("mtd_redemption", "Redemption\nValue"),
    # --- inserted right after MTD Redemption ---
    ("mtd_cashback_earned_liq", "Liq Cashback"),
    ("incremental_sales", "Incremental sales"),
    ("incremental_nob", "Incremental NOB"),
    ("past_nob", "NOB Past Trends"),
    ("current_nob", "Current NOB"),
    # --- the rest of the columns, after the template block ends ---
    ("is_existing_liq_buyer", "Is Existing Liq Buyer"),
    ("liq_buyer_type", "Liq Buyer Type"),
    ("mtd_redemption_liq", "Liq Redemption"),
    ("ytd_cashback_earned", "YTD Cashback Earned"),
    ("ytd_cashback_earned_liq", "YTD Liq Cashback"),
    ("ytd_redemption", "YTD Redemption"),
    ("ytd_redemption_liq", "YTD Liq Redemption"),
    ("liq_gross_sales", "Liq Gross Sales"),
    ("liq_nob", "Liq NOB"),
    ("liq_qty", "Liq Qty"),
    ("lost_sales", "Lost Sales"),
    ("lost_nob", "Lost NOB"),
    ("plan_tier_dup", "Plan Tier"),  # placeholder, skipped (Tier already shown)
    ("start_date", "Start Date"),
    ("end_date", "End Date"),
    ("transaction_date", "Transaction Date"),
]
# Drop the placeholder used only to keep Plan Tier from duplicating.
_FORMAT_LAYOUT = [(c, h) for (c, h) in _FORMAT_LAYOUT if c != "plan_tier_dup"]

# Numeric columns that should be rounded to 2 dp for display/download.
_ROUND_2DP_INTERNAL = {
    "bill_value", "eligible_bill_value", "past_ams", "past_qty", "current_qty",
    "current_asp", "past_asp", "current_qpb", "past_qpb", "post_loyalty_ams",
    "mtd_cashback_earned", "mtd_cashback_earned_liq", "mtd_redemption",
    "mtd_redemption_liq", "ytd_cashback_earned", "ytd_cashback_earned_liq",
    "ytd_redemption", "ytd_redemption_liq", "liq_gross_sales", "liq_nob",
    "liq_qty", "incremental_sales", "incremental_nob", "past_nob",
    "current_nob", "lost_sales", "lost_nob",
}

# Backwards-compatible alias kept for any external imports.
DISPLAY_COLUMN_MAP = {c: h for c, h in _FORMAT_LAYOUT}


def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Return the AMS report in the analyst's required template layout.

    Produces columns in the exact order / with the exact header names of
    format.csv (plus the trailing extra columns), formats dates dd-mm-yyyy and
    rounds numeric columns to 2 dp. Used for both the on-screen table and the
    CSV download so the two always match.
    """
    if df.empty:
        # Still return an empty frame with the right headers so the UI/download
        # show the correct columns even before data is loaded.
        return pd.DataFrame(columns=[h for _, h in _FORMAT_LAYOUT])

    src = df.copy()
    # dd-mm-yyyy for date columns
    for c in ("start_date", "end_date", "transaction_date"):
        if c in src.columns:
            src[c] = pd.to_datetime(src[c], errors="coerce").dt.strftime("%d-%m-%Y")
    # round numerics
    for c in _ROUND_2DP_INTERNAL:
        if c in src.columns:
            src[c] = pd.to_numeric(src[c], errors="coerce").round(2)

    out = pd.DataFrame()
    for internal, header in _FORMAT_LAYOUT:
        out[header] = src[internal] if internal in src.columns else ""
    return out
