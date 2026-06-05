"""Near-Expiry & Upcoming-Renewal report.

Expiry is derived from the member's **original enrolment month** using a clean
cohort rule (a 12-month term, so the term's last month is enrolment-month + 11):

    Enrolled Jul-25  ->  expires Jun-26
    Enrolled Aug-25  ->  expires Jul-26
    Enrolled Sep-25  ->  expires Aug-26
    ... and so on for every month in the data.

A **30-day renewal window** opens before the expiry date. A member is counted
as *due to renew* in their expiry month until they actually renew — once a
member has renewed (enrollment_status == "Renewal", i.e. they took a fresh
term), they are **deducted** from the pending/due count, so the number left to
renew falls as renewals come in.

Everything is built on the AMS report cache (one row per member, original
enrolment month already corrected), so tier / shopping / liquor flags are
joined in already.
"""
from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import DateOffset, MonthEnd

TERM_MONTHS = 12                       # 12-month membership
EXPIRY_OFFSET_MONTHS = TERM_MONTHS - 1  # last month of the term = enrol + 11
RENEWAL_WINDOW_DAYS = 30                # window opens 30 days before expiry


# ---------------------------------------------------------------------------
def _enroll_month_ts(df: pd.DataFrame) -> pd.Series:
    """Month-start timestamp of the ORIGINAL enrolment for each member."""
    if "enroll_month" in df.columns:
        s = pd.to_datetime(df["enroll_month"], errors="coerce")
    else:
        s = pd.to_datetime(df.get("start_date"), errors="coerce")
    return s.dt.to_period("M").dt.to_timestamp()


def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    numeric = {"bill_value", "mtd_redemption", "mtd_cashback_earned",
               "mtd_cashback_earned_liq"}
    for c in ("end_date", "start_date", "plan_tier", "shopper_behaviour",
              "is_existing_liq_buyer", "enrollment_status", "bill_value",
              "store_code", "store_name", "region", "city", "msr_number",
              "customer_name", "mtd_redemption", "mtd_cashback_earned",
              "enroll_month", "enroll_month_label"):
        if c not in df.columns:
            df[c] = 0.0 if c in numeric else ""
    return df


def _augment(df: pd.DataFrame) -> pd.DataFrame:
    """Add cohort expiry / renewal-window / renewed columns to a member frame."""
    df = _ensure_cols(df)
    enr = _enroll_month_ts(df)
    df = df[enr.notna()].copy()
    enr = enr[enr.notna()]

    df["enroll_month_ts"] = enr
    df["enroll_month_label"] = enr.dt.strftime("%b-%y")

    expiry_month = enr + DateOffset(months=EXPIRY_OFFSET_MONTHS)
    df["expiry_month_ts"] = expiry_month
    df["expiry_month_label"] = expiry_month.dt.strftime("%b-%y")
    df["expiry_date"] = (expiry_month + MonthEnd(0))
    df["renewal_window_open"] = df["expiry_date"] - pd.Timedelta(days=RENEWAL_WINDOW_DAYS)

    # A member who already took a fresh term is "renewed" and is deducted from
    # the pending/due count.
    status = df["enrollment_status"].astype(str)
    df["already_renewed"] = status.eq("Renewal")
    df["renewal_state"] = df["already_renewed"].map(
        {True: "Renewed", False: "Pending"}
    )
    return df


# ---------------------------------------------------------------------------
def expiry_months(ams_df: pd.DataFrame) -> list[str]:
    """Chronological list of cohort expiry-month labels (e.g. 'Jun-26')."""
    if ams_df.empty:
        return []
    df = _augment(ams_df)
    months = sorted(df["expiry_month_ts"].dropna().unique())
    return [pd.Timestamp(m).strftime("%b-%y") for m in months]


def build_near_expiry(ams_df: pd.DataFrame,
                      expiry_month_label: str | None = None,
                      pending_only: bool = False) -> pd.DataFrame:
    """Customer-level near-expiry table (one row per member)."""
    if ams_df.empty:
        return pd.DataFrame()

    df = _augment(ams_df)

    if expiry_month_label and expiry_month_label != "All months":
        df = df[df["expiry_month_label"] == expiry_month_label]
    if pending_only:
        df = df[~df["already_renewed"]]

    df["shopped_current_month"] = (df["shopper_behaviour"] == "Shopped").map(
        {True: "Yes", False: "No"}
    )
    df["expiry_date_str"] = df["expiry_date"].dt.strftime("%d-%m-%Y")
    df["renewal_window_str"] = df["renewal_window_open"].dt.strftime("%d-%m-%Y")

    df = df.sort_values(["expiry_month_ts", "plan_tier", "msr_number"])

    cols = [
        "enroll_month_label", "expiry_month_label", "expiry_date_str",
        "renewal_window_str", "renewal_state",
        "msr_number", "customer_name", "plan_tier",
        "store_code", "store_name", "region", "city",
        "start_date", "end_date",
        "shopped_current_month", "bill_value",
        "enrollment_status", "is_existing_liq_buyer",
        "mtd_cashback_earned", "mtd_redemption",
    ]
    out = df[[c for c in cols if c in df.columns]].copy().reset_index(drop=True)
    return out


def build_renewal_pipeline(ams_df: pd.DataFrame,
                           current_period: pd.Timestamp | None = None) -> pd.DataFrame:
    """Month-by-month expiry / renewal summary (the 'Upcoming Renewal' view).

    For each cohort expiry month it reports how many memberships come up for
    renewal, how many have already renewed (deducted) and how many are still
    pending — plus whether the 30-day renewal window is open relative to the
    current data period.
    """
    if ams_df.empty:
        return pd.DataFrame()

    df = _augment(ams_df)
    grp = df.groupby(["expiry_month_ts", "expiry_month_label"], dropna=True)
    summary = grp.agg(
        enroll_month=("enroll_month_label", "first"),
        expiring=("msr_number", "count"),
        renewed=("already_renewed", "sum"),
        expiry_date=("expiry_date", "first"),
        window_open=("renewal_window_open", "first"),
    ).reset_index()

    summary["renewed"] = summary["renewed"].astype(int)
    summary["pending"] = summary["expiring"] - summary["renewed"]
    summary["renewal_pct"] = (
        summary["renewed"] / summary["expiring"].where(summary["expiring"] > 0)
    ).fillna(0.0) * 100.0
    summary["renewal_pct"] = summary["renewal_pct"].round(1)

    if current_period is None:
        current_period = pd.Timestamp.today().normalize()
    summary["window_status"] = summary.apply(
        lambda r: (
            "Expired" if current_period > r["expiry_date"]
            else "Window open" if current_period >= r["window_open"]
            else "Upcoming"
        ),
        axis=1,
    )

    summary = summary.sort_values("expiry_month_ts").reset_index(drop=True)
    summary["expiry_date"] = pd.to_datetime(summary["expiry_date"]).dt.strftime("%d-%m-%Y")
    summary["window_open"] = pd.to_datetime(summary["window_open"]).dt.strftime("%d-%m-%Y")
    return summary[[
        "enroll_month", "expiry_month_label", "expiry_date", "window_open",
        "window_status", "expiring", "renewed", "pending", "renewal_pct",
    ]]


# ---------------------------------------------------------------------------
DISPLAY_MAP = {
    "enroll_month_label": "Enrolment Month",
    "expiry_month_label": "Expiry Month",
    "expiry_date_str": "Expiry Date",
    "renewal_window_str": "Renewal Window Opens",
    "renewal_state": "Renewal State",
    "msr_number": "Mobile Number",
    "customer_name": "Customer Name",
    "plan_tier": "Tier",
    "store_code": "Store Code",
    "store_name": "Store Name",
    "region": "Region",
    "city": "City",
    "start_date": "Start Date",
    "end_date": "End Date",
    "shopped_current_month": "Shopped This Month?",
    "bill_value": "Current Bill Value",
    "enrollment_status": "Status of Enrollment",
    "is_existing_liq_buyer": "Is Existing Liq Buyer",
    "mtd_cashback_earned": "MTD Cashback Earned",
    "mtd_redemption": "MTD Redemption",
}

RENEWAL_DISPLAY_MAP = {
    "enroll_month": "Enrolment Month",
    "expiry_month_label": "Expiry Month",
    "expiry_date": "Expiry Date",
    "window_open": "Renewal Window Opens",
    "window_status": "Status",
    "expiring": "Memberships Expiring",
    "renewed": "Renewed (Deducted)",
    "pending": "Pending Renewal",
    "renewal_pct": "Renewal %",
}


def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    show = df.copy()
    for c in ("start_date", "end_date"):
        if c in show.columns:
            show[c] = pd.to_datetime(show[c], errors="coerce").dt.strftime("%d-%m-%Y")
    return show.rename(columns=DISPLAY_MAP)


def format_renewal_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.rename(columns=RENEWAL_DISPLAY_MAP)
