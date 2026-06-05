"""Renewal & New-Acquisition report.

Driven directly by the membership file. A member can appear multiple times:
the *earliest* record is the original New Acquisition; every later record is a
Renewal / Existing-Upgrade / Force-Upgrade of the SAME member.

Bucketing rules (corrected):
    • New Acquisition (N)  -> bucketed by the ORIGINAL Start-Date month
                              (the true enrolment cohort). The Transaction
                              Date is NOT used as the enrolment month.
    • Renewal              -> any *later* membership term (a fresh term that
                              begins after the previous one) excluding pure
                              Existing-Upgrades. Bucketed by the renewal
                              term's Start-Date month = the month the old
                              term came up for renewal.
    • Existing Upgrade (EU)-> tier raised mid-term, validity unchanged.
                              Bucketed by Transaction-Date month.
    • Force Upgrade (FE)   -> mid-term upgrade, fresh validity. Bucketed by
                              Transaction-Date month.

"Previously Registered" (a.k.a. memberships *due* to renew) for a store/month
= number of memberships whose End Date falls in that month — i.e. terms coming
up for renewal that month.

Renewal % (per store-month) = renewals / previously_registered × 100.

Because the programme is young, most 1-year terms have not yet expired; the
big expiry waves are in the future. The dashboard's *overall* renewal % is
therefore computed only over months that have already occurred (≤ the current
data period), so early renewals of future-dated terms don't make the headline
exceed 100%. Those early renewals are reported separately as "Early Renewals".
"""
from __future__ import annotations

import pandas as pd
import numpy as np

import db


def build_renewal_report() -> pd.DataFrame:
    membership = db.fetch_df("SELECT * FROM membership")
    stores = db.fetch_df(
        "SELECT store_code, store_name, region, cluster, city, format FROM stores"
    )
    if membership.empty:
        return pd.DataFrame()

    m = membership.copy()
    m["start_dt"] = pd.to_datetime(m["start_date"], errors="coerce")
    m["end_dt"] = pd.to_datetime(m["end_date"], errors="coerce")
    m["txn_dt"] = pd.to_datetime(m["transaction_date"], errors="coerce")
    m = m.dropna(subset=["start_dt"]).reset_index(drop=True)

    if "registration_type" not in m.columns:
        m["registration_type"] = "N"
    m["registration_type"] = m["registration_type"].fillna("N").astype(str).str.upper()
    m["plan_tier"] = m.get("plan_tier", "Other").fillna("Other")

    store_key = "registered_store_code"

    # Rank each member's records by start date: 0 = original enrolment.
    m = m.sort_values(["mobile_no", "start_dt"], na_position="last")
    m["rank"] = m.groupby("mobile_no").cumcount()

    # Month helpers (month-start timestamps)
    def _mstart(s: pd.Series) -> pd.Series:
        return s.dt.to_period("M").dt.to_timestamp()

    m["start_month"] = _mstart(m["start_dt"])
    m["end_month"] = _mstart(m["end_dt"])
    m["txn_month_ts"] = _mstart(m["txn_dt"]).fillna(m["start_month"])

    # ---- Event slices ---------------------------------------------------
    # New Acquisition = first record of each member, by ORIGINAL start month.
    new_recs = m[m["rank"] == 0]
    # Renewals = later terms that are NOT pure existing-upgrades.
    ren_recs = m[(m["rank"] >= 1) & (m["registration_type"] != "EU")]
    eu_recs = m[m["registration_type"] == "EU"]
    fe_recs = m[m["registration_type"] == "FE"]

    def _count(df: pd.DataFrame, month_col: str, name: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=[store_key, "activity_month", name])
        return (
            df.groupby([store_key, month_col])
            .size().reset_index(name=name)
            .rename(columns={month_col: "activity_month"})
        )

    new_agg = _count(new_recs, "start_month", "new_acquisitions")
    ren_total = _count(ren_recs, "start_month", "renewals")
    eu_agg = _count(eu_recs, "txn_month_ts", "existing_upgrades")
    fe_agg = _count(fe_recs, "txn_month_ts", "force_upgrades")

    # Tier breakdown of renewals (by the renewal term's tier)
    if not ren_recs.empty:
        ren_tier = (
            ren_recs.groupby([store_key, "start_month", "plan_tier"])
            .size().unstack(fill_value=0).reset_index()
            .rename(columns={"start_month": "activity_month"})
        )
    else:
        ren_tier = pd.DataFrame(columns=[store_key, "activity_month"])
    for col in ("Gold", "Platinum", "Diamond"):
        if col not in ren_tier.columns:
            ren_tier[col] = 0
    ren_tier = ren_tier.rename(columns={
        "Gold": "gold_renewals",
        "Platinum": "platinum_renewals",
        "Diamond": "diamond_renewals",
    })

    # Previously Registered = memberships whose term EXPIRES that month
    # (every term that has an End Date), bucketed by end month. This is the
    # "due to renew" base. We do NOT pre-filter to <= current period here;
    # the bounded *overall* % is computed in the UI over occurred months only.
    prev_agg = _count(m.dropna(subset=["end_month"]), "end_month", "previously_registered")

    # ---- Combine on (store, activity_month) -----------------------------
    out = new_agg
    for d in (ren_total, eu_agg, fe_agg, prev_agg, ren_tier):
        out = out.merge(d, on=[store_key, "activity_month"], how="outer")

    for col in ("new_acquisitions", "renewals", "existing_upgrades",
                "force_upgrades", "previously_registered",
                "gold_renewals", "platinum_renewals", "diamond_renewals"):
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0).astype(int)

    out["renewal_pct"] = np.where(
        out["previously_registered"] > 0,
        (out["renewals"] / out["previously_registered"]) * 100.0,
        0.0,
    ).round(2)

    out = out.dropna(subset=["activity_month"]).copy()
    out["period"] = pd.to_datetime(out["activity_month"]).dt.strftime("%Y-%m-%d")
    out["period_label"] = pd.to_datetime(out["activity_month"]).dt.strftime("%b-%y")

    out = out.merge(stores, left_on=store_key, right_on="store_code", how="left")
    out = out.rename(columns={store_key: "store_code_in"})
    out["store_code"] = out["store_code"].fillna(out["store_code_in"])
    out = out.drop(columns=["store_code_in", "activity_month"])

    out = out[[
        "store_code", "store_name", "region", "cluster", "city", "format",
        "period", "period_label",
        "new_acquisitions", "renewals", "existing_upgrades", "force_upgrades",
        "previously_registered", "renewal_pct",
        "gold_renewals", "platinum_renewals", "diamond_renewals",
    ]].fillna({"store_name": "", "region": "", "cluster": "", "city": "", "format": ""})

    out = out.sort_values(["store_code", "period"]).reset_index(drop=True)

    db.replace_table("renewal_cache", out)
    return out


DISPLAY_RENEWAL_MAP = {
    "store_code": "Store Code",
    "store_name": "Store Name",
    "region": "Region",
    "cluster": "Cluster",
    "city": "City",
    "format": "Format",
    "period_label": "Month",
    "new_acquisitions": "New Acquisitions",
    "renewals": "Renewals",
    "existing_upgrades": "Existing Upgrades",
    "force_upgrades": "Force Upgrades",
    "previously_registered": "Previously Registered",
    "renewal_pct": "Renewal %",
    "gold_renewals": "Gold Renewals",
    "platinum_renewals": "Platinum Renewals",
    "diamond_renewals": "Diamond Renewals",
}


def format_renewal_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    show = df.copy()
    if "period" in show.columns:
        show = show.drop(columns=["period"])
    return show.rename(columns=DISPLAY_RENEWAL_MAP)
