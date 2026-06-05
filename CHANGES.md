# Change log — corrected logic + dark/blue dashboard

## Data-logic fixes

### 1. Enrolment month & duplicate members (AMS Migration Report)
`processing.py` no longer keeps the *latest* membership record per mobile.
Members are now **collapsed to one row each**:
- **Month of Enrolment** = month of the member's **earliest** Start Date (the
  original enrolment). This removes the phantom **Jul-26 / Aug-26** enrolment
  months, which were actually renewal terms beginning the day after the first
  term expired.
- **Tier** = the tier of the member's **latest** record — i.e. the tier they
  renewed / upgraded into ("just change the tier name").
- **Status** = New Acquisition for single-record members, else Renewal /
  Existing Upgrade / Force Upgrade based on their most recent action.
- Start Date = original; End Date / Transaction Date = latest (current validity).

Verified on the supplied file: 119,616 member rows, **0** Jul-26/Aug-26
enrolments (was non-zero before).

### 2. Renewal % (Renewals page) — no longer 643%
`renewal.py` + the Renewals page were corrected:
- Renewals are bucketed by the **renewal term's start month** (= the month the
  old term came up for renewal), **not** the Transaction Date.
- New Acquisitions are bucketed by the **original** enrolment month.
- The headline **Overall Renewal %** only counts months that have **already
  occurred** (≤ current data period), so early renewals of future-dated terms
  can't push it past 100%. Early renewals are shown in a separate
  **"Early Renewals"** tile.
- "Memberships Expired" tile renamed **"Memberships Due (Expired)"**.

Result on the supplied file: matured renewals 57 / due 57 → **100.0%**, with
**585 early renewals** surfaced separately.

### 3. Liquor cashback — computed, Diamond-only
Liquor cashback is **no longer read from the redemption file**. It is computed
as **1% of Liquor Gross Sales** and earned by **Diamond members only**
(Gold / Platinum = ₹0), for both MTD and YTD. See `LIQ_CASHBACK_RATE` in
`config.py`. Verified: Diamond ₹10,000 liq sales → ₹100 cashback; Gold → ₹0.

## UI

- **Dark mode only** with an **animated blue light** travelling around KPI
  cards and pulsing on buttons (`app.py` CSS + `.streamlit/config.toml`).
- **All fonts forced to light** (white / light-blue) so nothing is invisible.
- **Tables are dark with white text** (st.dataframe inherits the dark base;
  HTML-table fallback themed in CSS).

## Rewards Intelligence → native Python dashboard
`rewards_native.py` (new) replaces the slow embedded HTML with a native
Streamlit + Plotly dashboard (dark template): KPI tiles, Overview, Return
Rate, Stores, Cashback & Sales, Geography, AMS Slab Matrix and a **paginated**
Data Explorer — fast even with 100K+ rows. The standalone HTML export is still
available on demand via a download button.

---

# Update 2 — expiry logic, light/gold theme, top navbar, click-to-download

## Near Expiry & Upcoming Renewals (`near_expiry.py`, Near Expiry page)
- **Cohort expiry rule**: expiry month = **enrolment month + 11** (12-month
  term). Jul-25 → **Jun-26**, Aug-25 → **Jul-26**, and so on for the whole base
  — clean and consistent, no day-level noise.
- **30-day renewal window** before each expiry date; each cohort is tagged
  *Upcoming / Window open / Expired* relative to the current data period.
- **Upcoming Renewal pipeline** view: per expiry month it shows memberships
  expiring, **renewed (deducted)**, **pending**, and renewal %. As members
  renew, they are removed from the pending count automatically.
- A **next-month focus banner** highlights the cohort expiring next month.
- Members tab adds a **Renewal state** filter (Pending / Renewed).

## Theme — light + gold/silver
- Switched from dark/blue to a **light** theme with a **gold + silver**
  gradient palette (`.streamlit/config.toml`, app CSS, `ui_styles.py`,
  all inline + native charts).

## Buttons & cards — golden comet border
- A **moving golden light-ray with a fading tail** circles every button and
  card (conic-gradient "comet" animation). Active nav tab fills solid gold.

## Navigation — top navbar (sidebar removed)
- The sidebar is **hidden**; navigation is a **top bar of tab buttons**.
- Tabs are **texture-coded**: gold, silver, platinum and diamond finishes.
- Admin login/logout moved into the top bar (popover).

## Click-to-download on charts & filters
- Every chart is **clickable**: select a bar / slice / segment and a
  **download button** appears exporting only that portion. Example: clicking
  **Shopped / Not Shopped** exports just that segment.
- Exports include **mobile number, store code, store name, region, city,
  tier, channel, bill value, cashback** and related fields.
- The Rewards filters also drive a **full filtered-CSV** export, and the
  renewal pipeline supports per-cohort downloads.
