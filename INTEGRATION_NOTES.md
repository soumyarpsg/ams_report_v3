# Rewards Intelligence integration — change notes

## What's new

A new sidebar page **🎯 Rewards Intelligence** is added to the Spencer's MSR
Dashboard. It embeds the full Rewards Intelligence dashboard (charts, KPIs,
filters, exports) directly inside Streamlit and is **auto-fed** from the AMS
Migration Report — no separate CSV upload is needed.

When you upload data via **Upload Data** and click *Process uploaded files &
rebuild reports*, the embedded dashboard refreshes on the next page view.

## Latest changes (v2)

### 1. Memberships Expired — bug fix

Previously, the Renewals page counted **every** membership's expiry month —
including memberships that hadn't expired yet — so the "Memberships Expired"
KPI showed the same number as lifetime acquisitions (e.g. 105,158).

**Fix:** in `renewal.py`, `previously_registered` is now filtered to only
include memberships whose `end_date` falls on or before the last day of the
current data period. So if you uploaded data through April 2026 and the
loyalty programme started in July 2025 with 12-month plans, no plans have
yet expired and the KPI correctly shows **0**. As time passes and plans
actually expire, the count grows month-by-month.

Verified with 4 cutoff scenarios (Jul-25, Sep-25, Apr-26, Oct-26) using a
synthetic membership frame — see `test_renewal_expiry.py` if you want to
reproduce.

### 2. AMS Slab Transition Matrix (Waterfall view)

A cross-tab matrix showing how customers moved between Past 6-month AMS
slabs (rows) and Current AMS slabs (columns), styled like the Excel pivot
in your screenshot:

- 🟦 **Blue diagonal** — customers stayed in the same slab
- 🟩 **Green (above diagonal)** — customers upgraded to a higher slab
- 🟧 **Orange (below diagonal)** — customers downgraded to a lower slab
- ⬛ **Dark** — Grand Total row/column

Added in two places:

- **AMS Migration Report page (Python)** — new section under the data table.
  Honours all the existing region / cluster / store / month filters. Includes
  Upgraded / Stayed Same / Downgraded KPI strip and a CSV download.
- **Rewards Intelligence → Return Rate tab (HTML)** — new "AMS Slab
  Transition Matrix (Waterfall)" section under the existing past-vs-current
  bar chart. Same color scheme; light- and dark-mode aware.

## What was removed from the original Rewards dashboard

- Upload screen, loading screen, restore banner
- AI Analyst tab + Anthropic API key modal + all AI code
- IndexedDB session persistence
- "New Upload" reset button (Python now owns the data lifecycle)

Everything else — Overview, Return Rate, Customers, Stores, Cashback &
Sales, Geography, Lost Sales, Data Explorer, all exports (CSV/XLSX/PDF/
JPEG/PPTX), theme toggle, responsive view toggle — works as before.

## Return Rate definition

> **Existing Customer** = enrolled in any month *before* the reporting month
> **New Customer** = enrolled in the reporting month
> **Return Rate** = (Existing Customers who shopped) ÷ (Total Existing Customers)

The on-screen note above the Return Rate KPIs reflects this. The header
reporting-month selector still recomputes the dashboard live when changed.

## Files changed / added

| File | Status | Purpose |
| --- | --- | --- |
| `app.py` | **modified** | Adds the new sidebar page, AMS Slab Transition Matrix section, cached HTML builder, cache busting |
| `renewal.py` | **modified** | Filters `previously_registered` to only memberships with `end_date <= current period` |
| `rewards_intelligence.py` | **new** | Maps AMS report DataFrame to the rewards schema and renders the embeddable HTML |
| `rewards_template.html` | **new** | Embeddable template (transformed from `Rewards_Intelligence_Dashboard_v4_fixed.html`) |
| `preview_rendered.html` | **new** | Standalone preview rendered from synthetic data |

No other files (`processing.py`, `ingest.py`, `db.py`, `auth.py`, `config.py`, `lookups.py`) were touched.

## Field mapping

The AMS report's column names are translated to the names the Rewards JS expects:

| AMS report column | Rewards dashboard field |
| --- | --- |
| `store_code`, `store_name`, `customer_name` | same |
| `city`, `cluster`, `region`, `format` | `city_name`, `cluster_name`, `region_name`, `format_type` |
| `enroll_month_label` | `enroll_month` (Mmm-yy) |
| `bill_value` | `current_bill_value` |
| `mtd_cashback_earned` | `cashback_earned_current_month` |
| `mtd_redemption` | `redemed_amount_current_month` |
| `incremental_sales`, `current_nob`, `current_asp`, `bill_slab`, `current_ams_slab`, `shopper_behaviour` | same |
| `past_ams` | `past_six_months_average_ams` |
| `past_nob` | `past_six_months_average_nob` |
| `past_ams_slab` | `past_six_months_ams_slab` |
| `msr_number` | `msr_number` |

`customer_type` is derived in the browser using the reporting month.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Default admin: `admin` / `spencers@2026`.


---

## Liquor + Registration-Type release (update)

### New source columns picked up automatically
- **Membership** → `Registration Type` (N / R / FE / EU) and `Transaction Date`.
  Mapped to a readable **Status of Enrollment**: New Acquisition, Renewal,
  Force Upgrade, Existing Upgrade. Old files without these columns still parse
  (everything defaults to N / New Acquisition).
- **Redemption** → `Cashback For` (LIQ / NON-LIQ). Cashback (BALANCE CREDIT) and
  redemption are now split into **Non-Liq** and **Liq** for both MTD and YTD.

### Two new liquor files (Upload Data page)
1. **Liquor Buyers BASE** — a single column of mobile numbers (1-year base).
   Flags every Diamond member as **Existing Liq Buyer** (found in base) or
   **New Liq Buyer**. Drives the `Is Existing Liq Buyer` (Yes/No) column for all
   customers. Stored in table `liq_buyers_base`. Upload occasionally.
2. **Liquor SALES** — transactional (date, month, store code, store name,
   mobile number, nob, billed qty, gross sales). **Appends** to what's already
   stored, de-duplicating on (date, store, mobile), so you only ever upload the
   latest day. Stored in table `liq_sales`. A consolidated **Excel** download
   and a **sample CSV** are on the Upload page.

### AMS Migration Report — column changes
- `City` now sits **before** `Cluster`.
- New `Retail/B2B Buyer` (bill value ≤ ₹25,000 → Retail, else B2B).
- New `Customer Type` (Past AMS = 0 → New Buyer, else Existing Buyer).
- `Is Existing Liq Buyer` added right after `Bill Slab`.
- `MTD/YTD Cashback Earned Liq` and `MTD/YTD Redemption Liq` added next to each
  existing MTD/YTD value.
- `Liq Gross Sales / Liq NOB / Liq Qty` (current month) added.
- Re-ordered to `Incremental Sales → Incremental NOB → Past NOB → Current NOB`.
- `Status of Enrollment` added after `Channel of Enrollment`.

### Renewals page
Now driven directly by `Registration Type` and bucketed by Transaction-Date
month. Four cards: **New Acquisition / Renewal / Existing Upgrade / Force
Upgrade**, plus tier breakdown and renewal %.

### New "Near Expiry" page (sidebar)
Pick an expiry month (the month a 12-month plan's End Date falls in) and see
every member expiring then: mobile, tier, store, whether they shopped this
month, liquor-buyer flag and KPIs — with month/tier/shopped filters and CSV
download.

### Storage note
The canonical store for liquor sales is the SQLite table `liq_sales` (this is
what persists on Streamlit Cloud and what the append/de-dup runs against). The
Excel file is a downloadable consolidated snapshot of that table — it is not
the live store, so you never have to re-upload history; just upload each new
day's CSV.

---

## AMS Report output template (format.csv)

The AMS Migration Report view **and** CSV download now follow the analyst's
`format.csv` column order and exact header names (including the wrapped headers
like "Subscription / Sold" and the "Eligable Bill Value" spelling), so the
download drops straight into the existing downstream process:

`Store_Code, Store Name, Subscription Sold, C_NAME, Month of Purchase, Channel,
Tier, Tagging, R_Status, B2B, Customer Type, Shopper_Behaviour, Bill Slab,
Region, City, Cluster, Format, Bill Value, Eligable Bill Value, Past AMS, Past
Billed_Qty, Current Billed_Qty, Current ASP, Past ASP, Current QPB, Past QPB,
Post Loyalty AMS, Past AMS Slab, Current AMS Slab, Cashback, Redemption Value,`
**`Liq Cashback`** *(inserted here, right after Redemption Value)*`,
Incremental sales, Incremental NOB, NOB Past Trends, Current NOB`

Column mapping notes:
- **Tagging** = Registration Type code (N / R / FE / EU); **R_Status** = the
  readable status (New Acquisition / Renewal / Force Upgrade / Existing Upgrade).
- **B2B** = Retail / B2B (bill value ≤ ₹25K → Retail).
- **Subscription Sold** = membership Plan Name; **Tier** = plan tier.
- **Cashback / Redemption Value** = MTD cashback / MTD redemption; **Liq
  Cashback** = MTD liquor cashback.
- **NOB Past Trends** = Past NOB.

Every remaining column (Is Existing Liq Buyer, Liq Buyer Type, Liq Redemption,
all YTD values, Liq Gross Sales/NOB/Qty, Lost Sales/NOB, Start/End/Transaction
Date) follows **after** the template block.
