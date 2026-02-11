# Smart List Analysis: FUB vs DREAMS Bucketing

**Date:** 2026-02-11
**Status:** Analysis complete, action items pending Eugy's ideas

---

## Overview

The Smart Lists page (`/smart-lists`) shows FUB's 7 cadence call lists side-by-side with DREAMS' locally-computed equivalents. This document captures the count differences, why they exist, and the risk analysis of unbucketed contacts.

---

## Filter Comparison

| List | Cadence | FUB Filter | DREAMS Filter |
|------|---------|-----------|---------------|
| **New Leads** | Daily | Stage=Lead + Created <14d + LastComm >12hrs | Stage=Lead + Created <7d |
| **Priority** | Semiweekly | Stage=Hot Prospect + LastComm >3d | Top priority score (not a distinct bucket) |
| **Hot** | Weekly | Stage=Nurture + Timeframe=0-3mo + LastComm >7d | Heat score >= 70 (any stage) |
| **Warm** | Monthly | Stage=Nurture + Timeframe=3-6mo + LastComm >30d | Heat score 40-69 (any stage) |
| **Cool** | Quarterly | Stage=Nurture + Timeframe=6-12/12+/No Plans + LastComm >90d | Heat score 10-39 (any stage) |
| **Unresponsive** | Biweekly | Stage=Lead + Created >14d + LastComm >14d | Relationship score <15 + Heat >5 + Not new |
| **Timeframe Empty** | As needed | Stage=Nurture + No timeframeId set | Heat >=30 + No active intake form |

### Methodology Difference

- **FUB = communication cadence tool.** "Who haven't I talked to recently, grouped by urgency?" Filters use stage + time-since-last-contact + buying timeframe.
- **DREAMS = activity-based prioritization.** "Who's showing buying signals on the IDX site?" Filters use heat score (derived from property views, saves, site visits).

Neither is wrong — they answer different questions:
- **FUB answers:** "Who's overdue for a call?"
- **DREAMS answers:** "Who's actively shopping right now?"

---

## Count Comparison (as of 2026-02-11)

| List | FUB | DREAMS | Why the gap |
|------|-----|--------|-------------|
| New Leads | 18 | 12 | FUB uses 14-day window, DREAMS uses 7-day. The 6 extra FUB contacts are in the 7-14 day gap. |
| Priority | 0 | 0 | Both zero. No Hot Prospect contacts currently assigned. |
| Hot | 8 | 13 | DREAMS catches anyone with high IDX activity regardless of stage/timeframe. FUB only catches Nurture + 0-3mo + lapsed >7d. |
| Warm | 9 | 18 | DREAMS heat 40-69 spans all stages. FUB is narrow: Nurture + 3-6mo + lapsed >30d. |
| Cool | 1 | 68 | FUB's 90-day lastComm threshold is very strict. Most long-timeframe Nurture contacts were contacted more recently. DREAMS heat 10-39 is a wide band. |
| Unresponsive | 1 | 31 | FUB: old Leads with >14d since last comm. DREAMS: low relationship score across stages. Most old Leads have been contacted within 14d. |
| Timeframe Empty | 0 | 43 | Different concepts entirely. FUB: Nurture + no timeframe set (all current Nurture contacts have one). DREAMS: heat >=30 + no intake form (actionable signal). |

---

## Unbucketed Contact Analysis

**297 of 334 FUB contacts (89%) don't land in any bucket.** Zero permanent loss risk — everyone resurfaces eventually — but timing and surge patterns matter.

### Group 1: Lead Limbo — 169 contacts (57%)

Leads older than 14 days who were contacted within the last 14 days. Too old for New Leads, too recently contacted for Unresponsive. Dead zone between the two lists.

- **150 were last contacted exactly 13 days ago** (bulk action plan ~13 days prior)
- All 150 flood into Unresponsive the next day when they cross the 14-day threshold
- Resurface on: **Unresponsive** (biweekly cadence)
- This surge pattern repeats every time a bulk action plan fires

**Last comm distribution (169 Lead Limbo contacts):**
| Days since last comm | Count |
|---------------------|-------|
| 0-3 days | ~5 |
| 4-7 days | ~5 |
| 8-12 days | ~9 |
| 13 days | ~150 |

### Group 2: Nurture Recently Contacted — 128 contacts (43%)

Nurture contacts with timeframe set, but contacted recently enough to not hit the lastComm threshold. This is FUB working as designed — they drop off until it's time again.

| Subgroup | Count | Resurface on | Time to resurface |
|----------|-------|-------------|-------------------|
| 0-3 Mo timeframe | 9 | Hot (weekly) | 1-6 days |
| 3-6 Mo timeframe | 18 | Warm (monthly) | 1-29 days |
| 6-12/12+/No Plans | 101 | Cool (quarterly) | 1-89 days, avg ~71 days |

### Group 3: New Leads Just Contacted — ~0

Leads under 14 days old contacted within the last 12 hours. Nearly nobody at any given time — they resurface on New Leads within hours.

### Resurface Timeline Summary

| Window | Contacts | % of unbucketed |
|--------|----------|----------------|
| Within 7 days | 171 | 58% |
| Within 30 days | 202 | 68% |
| 30+ days out | 95 | 32% |
| Never/unknown | 0 | 0% |

---

## Key Insights

1. **No leaks, but surges.** FUB's threshold-based system creates cliff effects. When a bulk action plan fires, it creates a predictable wave 14 days later.

2. **The 150-contact Unresponsive spike** is the main operational risk. At biweekly cadence, that's a heavy day. This pattern will repeat with every bulk outreach.

3. **DREAMS' timeframe_empty (43 contacts) catches a signal FUB misses** — people with IDX activity who haven't had requirements documented. Actionable regardless of FUB bucket status.

4. **DREAMS complements FUB** — use FUB lists for the daily "bring to zero" workflow, use DREAMS heat/priority to prioritize within each bucket.

---

## TODO

Eugy has ideas for addressing the surge pattern and unbucketed gap. To be continued.
