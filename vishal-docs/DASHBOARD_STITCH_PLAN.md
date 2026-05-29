# DASHBOARD STITCH PLAN

**Created**: 2026-05-27  
**Purpose**: Map content from 4 standalone pages into drill-down sections within `dashboard/v2/app.html`

---

## Architecture Summary

```
app.html (SINGLE URL)
├── TAB: Overview
│   ├── Hero KPIs (capital, balance, P&L, today P&L)
│   ├── Margin utilization bar
│   ├── Charts (cumulative + daily P&L)
│   ├── Daily P&L table
│   ├── AI Postmortem (latest narrative)
│   └── DRILL-DOWN BUTTONS:
│       ├── [📊 Performance Detail] → hidden section
│       ├── [⚠️ Risk Status] → hidden section
│       └── [🌐 Universe View] → hidden section
├── TAB: Intraday (Trades)
├── TAB: F&O
├── TAB: Swing
└── TAB: Audit (already complete in app.html)
```

---

## Performance Page (167 lines)

**Source**: `dashboard/v2/performance.html`

### Unique Content

| Element | Data Source | Purpose |
|---------|------------|---------|
| Total Net P&L (KPI) | `api/v2/{profile}/daily_pnl/*.json` — sum of `daily_net_pnl` | Aggregate performance |
| Win Rate all-time (KPI) | Same — `wins / trade_count` | Overall accuracy |
| Profit Factor (KPI) | Gross wins / gross losses | Risk-adjusted return |
| Total Charges (KPI) | Sum of `daily_charges` | Cost awareness |
| Best Day (KPI) | Max `daily_net_pnl` | Peak performance |
| Worst Day (KPI) | Min `daily_net_pnl` | Worst drawdown day |
| Cumulative P&L chart | Line chart, running sum | Equity curve |
| Daily P&L chart | Bar chart, green/red per day | Daily variance |
| Rolling Stats table | 7-day / 14-day / all-time windows | Trend detection |

### What's NOT Already in app.html

- **Profit Factor** — not computed in app.html Overview
- **Total Charges** — not shown as standalone KPI
- **Rolling Stats table** (7d/14d/all windows) — not in app.html
- **Best/Worst Day** — not shown

### New Location

**Drill-down section: "Performance Detail"** within Overview tab.

Content to include:
1. 6 KPI cards (Total P&L, WR, Profit Factor, Charges, Best Day, Worst Day)
2. Cumulative P&L line chart (can reuse app.html chart logic)
3. Daily P&L bar chart (can reuse app.html chart logic)
4. Rolling Stats table (7d / 14d / all-time)
5. Future: WR by strategy type, WR by day-of-week (Phase 3 enhancement)

### Data Source

Same as app.html: `api/v2/{profile}/daily_pnl/{date}.json` files (HEAD-probed for last 30 days).

---

## Risk Page (205 lines)

**Source**: `dashboard/v2/risk.html`

### Unique Content

| Element | Data Source | Purpose |
|---------|------------|---------|
| 4 Profile cards | Hardcoded from RULES.md | Capital limits per profile |
| Global Risk Gates | Hardcoded | VIX thresholds, R:R min, force exit time |
| F&O Paper Config | Hardcoded | F&O-specific limits |
| Capital Scaling Plan table | Hardcoded | 5-phase scaling roadmap |

### What's NOT Already in app.html

- **Profile config cards** (all 4 profiles side-by-side) — not in app.html
- **Global Risk Gates** (VIX levels, R:R, force exit) — not in app.html
- **F&O Paper Config** — not in app.html
- **Capital Scaling Plan** — not in app.html

### New Location

**Drill-down section: "Risk Status"** within Overview tab.

Content to include:
1. **Trip Wires** (6 status indicators) — NEW, not in risk.html either. Placeholder until V3 builds trip wire data.
2. **VIX Gate** — current VIX + threshold + status (from `dhan_live.json` if available)
3. **Capital Deployment** — today's deployed vs limit (progress bar)
4. **Profile Config Cards** — 4 profiles with limits (from risk.html)
5. **Global Risk Gates** — VIX levels, R:R, force exit (from risk.html)
6. **Capital Scaling Plan** — 5-phase table (from risk.html)

### Data Source

- Mostly hardcoded (same as risk.html)
- VIX: from `api/{profile}/dhan_live.json` if available
- Trip wires: placeholder "🟢 OK" until V3 provides data
- Capital deployed: from latest `daily_pnl` JSON (`capital_deployed_peak`)

---

## Universe Page (230 lines)

**Source**: `dashboard/v2/universe.html`

### Unique Content

| Element | Data Source | Purpose |
|---------|------------|---------|
| 4 Tier sections | Hardcoded JS arrays | Show stock universe |
| Tier 1: Nifty 50 (50 chips) | Hardcoded | Primary alpha stocks |
| Tier 2: Nifty Next 50 (50 chips) | Hardcoded | Secondary stocks |
| Tier 3: Nifty 500 sample (30 chips) | Hardcoded | Mid/small cap sample |
| Tier 4: F&O eligible (40 chips) | Hardcoded | Derivatives universe |
| Scanner Inclusion Rules | Hardcoded | Price/volume/momentum filters |
| Staleness check | JS date comparison | Warns if data > 7 days old |

### What's NOT Already in app.html

- **Entire universe display** — nothing like this in app.html
- **Tier breakdown** — not shown anywhere
- **Scanner rules reference** — not shown

### New Location

**Drill-down section: "Universe View"** within Overview tab.

Content to include:
1. **Summary cards** — Total stocks, tiers breakdown, sectors count
2. **Tier sections** with chip grids (Nifty 50, Next 50, sample, F&O)
3. **Scanner Inclusion Rules** — params list
4. Future (Phase 5): searchable table from `nifty500_constituents.json`

### Data Source

- Hardcoded JS arrays (same as universe.html)
- Future: `api/v2/nifty500_constituents.json` when V3 provides it

---

## Audit Page (172 lines)

**Source**: `dashboard/v2/audit.html`

### Already In app.html?

**YES — fully duplicated.** The app.html Audit tab contains:
- Date selector (probes last 30 days via HEAD)
- Summary cards: trades, net P&L, win rate, charges, drift, trust score
- AI Narrative section (recommendation, what went right/wrong, bugs/risks)
- Bugs Observed section
- Trades detail table with drift badges

### Comparison

| Feature | audit.html | app.html Audit tab |
|---------|-----------|-------------------|
| Date picker | ✓ | ✓ |
| KPI cards (6) | ✓ | ✓ |
| AI Narrative | ✓ | ✓ |
| Bugs section | ✓ | ✓ |
| Trades table | ✓ | ✓ |
| Drift badges | ✓ | ✓ |
| Trust score | ✓ | ✓ |
| Validation JSON | ✓ (loads .validation.json) | ✗ (not in app.html) |

### Action

**Delete `audit.html`** — content is already in app.html Audit tab.

One minor gap: audit.html loads a `.validation.json` file for trust score. Verify if app.html Audit tab also does this. If not, add that fetch in Phase 2 as a minor enhancement.

---

## Summary: What Goes Where

| Source Page | Lines | Destination | Type |
|-------------|-------|-------------|------|
| `performance.html` | 167 | Overview → Drill-down "Performance Detail" | SECTION (hidden, revealed on click) |
| `risk.html` | 205 | Overview → Drill-down "Risk Status" | SECTION (hidden, revealed on click) |
| `universe.html` | 230 | Overview → Drill-down "Universe View" | SECTION (hidden, revealed on click) |
| `audit.html` | 172 | Already in app.html Audit TAB | DELETE (duplicate) |

---

## Files to Delete After Stitch (Phase 6)

| File | Reason |
|------|--------|
| `dashboard/v2/audit.html` | Duplicate of app.html Audit tab |
| `dashboard/v2/performance.html` | Content moved to Performance drill-down |
| `dashboard/v2/risk.html` | Content moved to Risk drill-down |
| `dashboard/v2/universe.html` | Content moved to Universe drill-down |
| `dashboard/v2/swing/` (entire dir) | Empty placeholder, never worked |
| `dashboard/v2/components/header.html` | Orphan (no pages left to include it) |
| `dashboard/v2/css/design.css` | Only used by deleted pages |
| `dashboard/v2/css/components.css` | Only used by deleted pages |
| `dashboard/v2/index.html` | Replace with redirect to app.html |
| `dashboard/index.html` | Replace with redirect to /v2/app.html |

---

## Acceptance Criteria (Phase 1)

- [x] All 5 files read (app.html, performance.html, risk.html, universe.html, audit.html)
- [x] DASHBOARD_STITCH_PLAN.md created
- [x] No HTML changes made
- [x] Plan distinguishes "drill-down section" (Performance/Risk/Universe) from "tab" (Overview/Trades/F&O/Swing/Audit)

---

## DASHBOARD PHASE 1 COMPLETE

**Files modified**: 0  
**Files created**: 1 (`vishal-docs/DASHBOARD_STITCH_PLAN.md`)  
**Lines added**: ~170  
**Drill-down sections planned**: 3 (Performance Detail, Risk Status, Universe View)  
**Tabs total**: 5 (unchanged: Overview, Intraday, F&O, Swing, Audit)  
**Deployed to S3**: No  
**URL verified**: N/A (no changes)  
**Time**: ~15 minutes  

**Awaiting approval for Phase 2.**
