# FUB Smart List Critical Analysis

**Date:** 2026-02-16
**Author:** myDREAMS Analytics
**Audience:** Jon Tharp Homes Leadership

---

## 1. Executive Summary

Our Follow Up Boss smart lists currently bucket **37 of 367 active contacts** — leaving **89% of the database invisible** to the daily call workflow at any given moment. The system was designed around 7 lists that should cover the full pipeline, but three structural flaws undermine the design: **threshold cliffs** that create 150-contact surge days, **dead buckets** that waste cadence slots on empty stages, and **stage blindness** that leaves revenue-stage contacts (Active Clients, Under Contract) in zero lists. This report quantifies each gap with real data and provides a concrete 8-bucket redesign that projects coverage from ~5% to ~53%.

---

## 2. How FUB Smart Lists Work

### The Three Filter Axes

Every FUB smart list is built from three dimensions:

| Axis | What It Controls | Example |
|------|-----------------|---------|
| **Stage** | Which pipeline stage the contact is in | Lead, Nurture, Hot Prospect |
| **Last Communication** | How long since the last call/text/email | >7 days, >30 days, >90 days |
| **Timeframe** | The contact's self-reported buying timeline | 0-3 months, 3-6 months, 6-12 months |

### The "Zero Out Your List" Workflow

The operational model is straightforward: each morning, an agent opens their smart lists and works each bucket to zero. As contacts are called, they drop off (because `lastComm` resets). They reappear on the list when enough time passes per that bucket's cadence. This only works when every contact lands in *some* bucket.

### Current 7 Buckets

| # | Bucket | Filter | Cadence | Current Count |
|---|--------|--------|---------|---------------|
| 1 | New Leads | Stage=Lead + Created <14d + LastComm >12hrs | Daily | ~18 |
| 2 | Priority | Stage=Hot Prospect + LastComm >3d | Semiweekly | **0** |
| 3 | Hot | Stage=Nurture + Timeframe=0-3mo + LastComm >7d | Weekly | ~8 |
| 4 | Warm | Stage=Nurture + Timeframe=3-6mo + LastComm >30d | Monthly | ~9 |
| 5 | Cool | Stage=Nurture + Timeframe=6-12/12+/No Plans + LastComm >90d | Quarterly | ~1 |
| 6 | Unresponsive | Stage=Lead + Created >14d + LastComm >14d | Biweekly | ~1* |
| 7 | Timeframe Empty | Stage=Nurture + No timeframe set | As needed | ~0 |

*\*Unresponsive count fluctuates dramatically — see Section 3.*

**Total in buckets: ~37 of 367 active contacts (10%)**

---

## 3. Bucket-by-Bucket Critical Analysis

### 3.1 New Leads — Functional, With a Cliff

| | |
|---|---|
| **Filter** | Stage=Lead + Created <14d + LastComm >12hrs |
| **Cadence** | Daily |
| **Current Count** | ~18 |
| **Verdict** | ✅ Functional |

**What works:** Captures new IDX registrations from smokymountainhomes4sale.com promptly. Daily cadence matches the speed-to-lead imperative.

**What fails:** The 14-day cliff is abrupt. On day 15, a lead vanishes from New Leads. If they were contacted within the last 14 days, they also don't qualify for Unresponsive. This creates **Lead Limbo** — a dead zone where 169 contacts are invisible (see Section 5.1).

FUB's own recommended default for new lead follow-up is **10 days**, not 14. The extra 4 days delays the transition without adding value.

---

### 3.2 Priority — Permanently Dead

| | |
|---|---|
| **Filter** | Stage=Hot Prospect + LastComm >3d |
| **Cadence** | Semiweekly |
| **Current Count** | **0** |
| **Verdict** | ❌ Dead |

**What works:** Nothing. The Hot Prospect stage is not used in our pipeline.

**What fails:** There is exactly 1 Hot Prospect contact in the entire FUB account (Mark Cantos), and that contact is assigned to a different agent. For Eugy's database: **zero contacts, zero chance of populating.** This semiweekly cadence slot — the second-highest priority in the system — is completely wasted.

**The cost:** A semiweekly call cadence is the most aggressive follow-up tier after Daily. This slot should be reserved for revenue-generating contacts (Active Clients, Under Contract). Instead, it monitors an empty stage.

---

### 3.3 Hot — Stage-Locked and Incomplete

| | |
|---|---|
| **Filter** | Stage=Nurture + Timeframe=0-3mo + LastComm >7d |
| **Cadence** | Weekly |
| **Current Count** | ~8 |
| **Verdict** | ⚠️ Partially Functional |

**What works:** For Nurture contacts with a 0-3 month timeframe who haven't been contacted in a week, this works as intended.

**What fails:**
- **Stage lock:** Only sees Nurture. There are **2 Lead-stage contacts** with heat scores of 100 and 87 (Christopher Graney, Bill Hollenbeck) who are invisible to this list. Erik Stielow (Active Client, heat 70.8) is also missed.
- **Timeframe dependency:** Requires a manually-set timeframe. Of 18 Nurture contacts with 0-3mo timeframe, only those with lapsed communication appear.
- **No activity signal:** A contact could be viewing 50 properties a day on the IDX site, but if they're Stage=Lead or have no timeframe set, they'll never appear here.

**14 contacts have heat scores ≥70 across all stages.** This list catches at most 8.

---

### 3.4 Warm — Too Slow, Too Narrow

| | |
|---|---|
| **Filter** | Stage=Nurture + Timeframe=3-6mo + LastComm >30d |
| **Cadence** | Monthly |
| **Current Count** | ~9 |
| **Verdict** | ⚠️ Partially Functional |

**What works:** Catches Nurture contacts in the 3-6 month buying window who've gone quiet.

**What fails:**
- **30-day threshold is 2x FUB's own recommendation.** FUB's default for warm leads is 14 days. At 30 days, a contact has gone a full month without hearing from us — by then, they may have engaged another agent.
- **Same stage lock as Hot.** 8 Lead-stage contacts have a 3-6 month timeframe and are completely invisible.
- **Same pool (27 Nurture + 3-6mo)** but most were contacted recently enough to not trigger. Only the truly neglected 9 appear.

---

### 3.5 Cool — Absurdly Strict

| | |
|---|---|
| **Filter** | Stage=Nurture + Timeframe=6-12/12+/No Plans + LastComm >90d |
| **Cadence** | Quarterly |
| **Current Count** | **1** |
| **Verdict** | ❌ Broken |

**What works:** The concept — longer-timeframe contacts need less frequent touch.

**What fails:** The 90-day lastComm threshold is extreme. **FUB's own recommended default is 30 days.** Our threshold is 3x stricter than the platform's own guidance.

The math: 102 Nurture contacts have a 6-12mo/12+/No Plans timeframe. To appear on Cool, they must not have been contacted in 90 days. Only 1 contact meets this bar. The other 101 were contacted more recently — but at monthly-or-less frequency, many are genuinely cooling off and need a touch.

**This is the single highest-impact fix:** changing 90 → 30 days would immediately surface ~20-30 contacts that are currently invisible.

---

### 3.6 Unresponsive — Surge Pattern

| | |
|---|---|
| **Filter** | Stage=Lead + Created >14d + LastComm >14d |
| **Cadence** | Biweekly |
| **Current Count** | ~1 (fluctuates wildly) |
| **Verdict** | ⚠️ Structurally Flawed |

**What works:** Identifies old leads who haven't responded to outreach.

**What fails:** The 14-day lastComm threshold creates a **cliff synchronized with bulk action plans.** When a drip campaign fires, it resets lastComm for a large batch. Exactly 14 days later, the entire batch floods into Unresponsive simultaneously.

From our Feb 11 analysis: **150 contacts were last contacted exactly 13 days prior** — meaning they all hit Unresponsive on the same day. At biweekly cadence, that's 150 calls to make in a single session. This isn't a manageable list; it's a wall.

The surge repeats every time a bulk action plan fires, making the list useless during spike days and nearly empty otherwise.

---

### 3.7 Timeframe Empty — Good Concept, Wrong Scope

| | |
|---|---|
| **Filter** | Stage=Nurture + No timeframe set |
| **Cadence** | As needed |
| **Current Count** | ~0 |
| **Verdict** | ⚠️ Too Narrow |

**What works:** Flags contacts who need a buying timeline captured. This is operationally valuable — you can't prioritize someone without knowing their timeframe.

**What fails:** Only covers Nurture stage. But **160 Lead-stage contacts** also have no timeframe set (81% of all Leads). These are the contacts most in need of a qualification call. Meanwhile, only 6 Nurture contacts lack a timeframe — so the list is nearly empty despite 166 contacts needing the same action.

---

## 4. The Math Problem — 89% Unbucketed

### The Funnel of Exclusion

Starting from the full active database, here's how contacts get filtered out:

```
862 total contacts in database
 └─ 367 active contacts (scored, non-Trash/Closed/DNC)
     │
     ├─ Stage filter removes:
     │   ├─ 14 Active Clients  → in ZERO buckets
     │   ├─  1 Under Contract  → in ZERO buckets
     │   └─  0 Hot Prospects   → Priority bucket exists but empty
     │
     ├─ 198 Leads eligible for: New Leads OR Unresponsive
     │   ├─ ~18 qualify for New Leads (created <14d + lastComm >12hrs)
     │   ├─  ~1 qualifies for Unresponsive (created >14d + lastComm >14d)
     │   └─ 169 in Lead Limbo (too old for New, too recent for Unresponsive)
     │
     └─ 153 Nurture eligible for: Hot, Warm, Cool, or Timeframe Empty
         ├─ 6 have no timeframe → Timeframe Empty (~0 currently showing)
         ├─ 18 have 0-3mo → Hot if lastComm >7d (~8 qualify)
         ├─ 27 have 3-6mo → Warm if lastComm >30d (~9 qualify)
         ├─ 102 have 6-12/12+/No Plans → Cool if lastComm >90d (~1 qualifies)
         └─ ~128 recently contacted → waiting to resurface

RESULT: ~37 in buckets / 367 active = ~10% bucketed
        ~330 contacts invisible to the daily workflow
```

### Stages With Zero Bucket Coverage

| Stage | Contacts | Avg Priority | Bucket Coverage |
|-------|----------|-------------|----------------|
| Active Client | 14 | 35.4 | **None** |
| Under Contract | 1 | 74.9 | **None** |
| Hot Prospect | 0 | — | Priority bucket exists, but empty |

These are the **highest-revenue contacts in the database.** Active Clients have deals in progress. Under Contract contacts are days from closing. Neither stage appears in any smart list. They rely entirely on the agent's memory for follow-up timing.

Notable Active Clients getting zero automated follow-up prompts:
- **Kevin Lewis** — Under Contract, heat 100, priority 74.9
- **Paige Albrecht** — Active Client, priority 57.3
- **Kimberley Speck** — Active Client, priority 56.9, relationship 93.8
- **Erik Stielow** — Active Client, heat 70.8 (actively browsing IDX)

### The Circular Dependency

The Hot/Warm/Cool buckets require a timeframe to be set. But:

1. To get a timeframe, a contact needs a qualification call
2. To prompt a qualification call, the contact needs to be on a list
3. To get on Hot/Warm/Cool, they need a timeframe

**178 contacts (49% of active) have no timeframe set.** They can't enter the Hot/Warm/Cool pipeline until someone manually sets one — but there's no list prompting that action (Timeframe Empty only covers 6 Nurture contacts, not the 160 Leads).

---

## 5. Five Failure Patterns

### 5.1 Lead Limbo — 169 Contacts Invisible

**What:** Leads older than 14 days who were contacted within the last 14 days. Too old for New Leads, too recently contacted for Unresponsive.

**Scale:** 169 contacts (46% of all active contacts) at the time of analysis.

**Impact:** These contacts are in active follow-up sequences but have no smart list visibility. If the action plan stalls or an agent wants to manually check in, there's no prompt.

**Root cause:** The New Leads and Unresponsive buckets share a 14-day boundary with no overlap or bridge bucket.

### 5.2 Unresponsive Surge — 150 Contacts on One Day

**What:** Bulk action plans reset lastComm for large batches. Exactly 14 days later, the entire batch crosses the Unresponsive threshold simultaneously.

**Scale:** 150 contacts flooding into a biweekly list on the same day.

**Impact:** The list is either empty (99% of the time) or overwhelmingly full (spike days). Neither state is actionable. On surge days, the agent either skips the list or cherry-picks, defeating the purpose.

**Root cause:** The 14-day Unresponsive threshold is too short for a system that uses bulk communication. Raising it to 45 days would spread the surge across a wider window and catch genuinely unresponsive contacts rather than recently-dripped ones.

### 5.3 Dead Priority — Semiweekly Cadence on an Empty Stage

**What:** The Priority bucket requires Stage=Hot Prospect, a stage not used in our pipeline.

**Scale:** 0 contacts. Permanently.

**Impact:** The second-most-aggressive call cadence in the system (semiweekly) is allocated to a bucket that will never populate. Meanwhile, 15 revenue-stage contacts (Active Client + Under Contract) have no bucket at all.

**Root cause:** The Hot Prospect stage may be a FUB default that was never adopted in our workflow. The Priority slot should be repurposed for contacts that actually exist.

### 5.4 Invisible Active Clients — 15 Revenue-Stage Contacts in Zero Buckets

**What:** Active Client and Under Contract contacts don't match any smart list filter.

**Scale:** 15 contacts with an average priority score of 37.6.

**Impact:** These are the contacts closest to closing a deal. Kevin Lewis (Under Contract, priority 74.9) and Erik Stielow (Active Client, heat 70.8, actively browsing) receive zero automated follow-up prompts. Communication depends entirely on agent memory.

**Root cause:** No bucket filters on Stage=Active Client or Stage=Under Contract.

### 5.5 The Timeframe Trap — 49% of Contacts Missing a Required Field

**What:** Hot, Warm, and Cool buckets all require a timeframe. 178 of 367 active contacts (49%) don't have one.

| Stage | No Timeframe | Total | % Missing |
|-------|-------------|-------|-----------|
| Lead | 160 | 198 | 81% |
| Active Client | 12 | 14 | 86% |
| Nurture | 6 | 153 | 4% |

**Impact:** Nurture is well-covered (96% have timeframes). But Leads — the contacts most needing qualification — are almost entirely locked out. And Active Clients, who *should* have the most data on file, are missing timeframes too (likely because the field isn't relevant once someone is actively transacting).

**Root cause:** The timeframe field is set during qualification calls. Leads haven't been qualified yet. The system penalizes contacts for not having data that the system itself hasn't prompted anyone to collect.

---

## 6. Best Practice Comparison

### FUB Recommended Defaults vs Our Setup

| Parameter | FUB Default | Our Setting | Gap |
|-----------|------------|-------------|-----|
| New Lead window | 10 days | 14 days | 4 days longer (delays transition) |
| Warm lastComm threshold | 14 days | 30 days | 2x slower (contacts go cold) |
| Cool lastComm threshold | 30 days | 90 days | 3x slower (1 contact vs ~25) |
| Unresponsive threshold | 30 days | 14 days | 2x faster (creates surge pattern) |
| Pipeline coverage | Active Client bucket | No bucket | Revenue stage invisible |

### Industry Standard Cadences

| Contact Type | Industry Standard | Our Cadence | Status |
|-------------|-------------------|-------------|--------|
| Speed-to-lead (new) | 5 min response, daily for 7-10 days | Daily for 14 days | ✅ Close |
| Active buyer (0-3mo) | Every 3-5 days | Weekly | ⚠️ Slightly slow |
| Active client (deal in progress) | Every 2-3 days | **No cadence** | ❌ Missing |
| Warm pipeline (3-6mo) | Biweekly | Monthly | ⚠️ 2x slow |
| Long-term nurture (6mo+) | Monthly | Quarterly (effectively never) | ❌ Broken |
| Unresponsive re-engagement | Monthly | Biweekly (but surge pattern) | ⚠️ Frequency OK, execution broken |

### Cost of Each Deviation

| Deviation | Business Cost |
|-----------|--------------|
| No Active Client bucket | Risk of deal falling through without timely follow-up |
| 30d Warm threshold (vs 14d) | 16 extra days of silence during active buying window |
| 90d Cool threshold (vs 30d) | 101 nurture contacts get no touchpoint for 3 months |
| 14d Unresponsive threshold | 150-contact surge overwhelms the daily workflow |
| No Lead Limbo bridge | 169 contacts in follow-up with zero list visibility |

---

## 7. Recommended Bucket Redesign

### Proposed 8-Bucket System

| # | Bucket | Filter | Cadence | Change from Current |
|---|--------|--------|---------|-------------------|
| 1 | **New Leads** | Stage=Lead + Created <10d + LastComm >12hrs | Daily | Tighten from 14d → 10d |
| 2 | **Active Pipeline** | Stage IN (Active Client, Under Contract) + LastComm >3d | Every 3 days | **NEW — replaces dead Priority** |
| 3 | **Hot** | Stage=Nurture + Timeframe=0-3mo + LastComm >7d | Weekly | No change (add IDX tags in Phase 3) |
| 4 | **Warm** | Stage=Nurture + Timeframe=3-6mo + LastComm >14d | Biweekly | Tighten from 30d → 14d |
| 5 | **Cool** | Stage=Nurture + Timeframe=6-12/12+/No Plans + LastComm >30d | Monthly | **Fix from 90d → 30d** |
| 6 | **Attempted** | Stage=Lead + Created >10d + LastComm 5-45d | Every 5 days | **NEW — fills Lead Limbo** |
| 7 | **Unresponsive** | Stage=Lead + Created >10d + LastComm >45d | Biweekly | Raise threshold from 14d → 45d |
| 8 | **Timeframe Empty** | Stage IN (Lead, Nurture) + No timeframe + LastComm >14d | As needed | Expand to include Leads |

### Key Design Decisions

**Why replace Priority with Active Pipeline?**
The Hot Prospect stage is unused. Active Client and Under Contract are the highest-revenue contacts with zero coverage. Repurposing the semiweekly slot for actual revenue-stage contacts is the single most impactful change.

**Why add Attempted?**
Lead Limbo (169 contacts between New Leads and Unresponsive) is the largest gap. "Attempted" captures leads that have been contacted but haven't responded yet — the follow-up window between first contact and giving up. The 5-45 day lastComm window avoids overlap with New Leads (<10d) and Unresponsive (>45d).

**Why raise Unresponsive to 45 days?**
The current 14-day threshold catches contacts still in active drip campaigns. At 45 days, a contact has genuinely gone cold despite multiple touches. This also eliminates the surge pattern: instead of 150 contacts hitting the threshold on the same day, they spread across a 31-day window (day 15 to day 45 is handled by Attempted).

**Why expand Timeframe Empty to include Leads?**
160 of 178 contacts without timeframes are Leads. The whole point of Timeframe Empty is to prompt a qualification call — and Leads are the contacts most needing qualification.

---

## 8. Before/After Coverage Projection

### Estimated Bucket Populations

| Bucket | Before (Current) | After (Redesign) | Change |
|--------|------------------|-------------------|--------|
| New Leads | ~18 | ~15 | -3 (tighter window) |
| Priority → Active Pipeline | 0 | ~15 | +15 (revenue contacts covered) |
| Hot | ~8 | ~8 | — |
| Warm | ~9 | ~15 | +6 (lower threshold) |
| Cool | 1 | ~25 | +24 (30d vs 90d) |
| Attempted | — | ~80 | **NEW** (Lead Limbo filled) |
| Unresponsive | ~1* | ~40 | Smoothed (no surge) |
| Timeframe Empty | ~0 | ~30 | +30 (Leads included) |

*\*Averages; current Unresponsive spikes to 150+ on surge days.*

### Coverage Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Contacts in any bucket** | ~37 | ~195† | 5x increase |
| **Coverage rate** | ~10% | ~53% | +43 points |
| **Active Clients covered** | 0 of 15 | 15 of 15 | Full coverage |
| **Lead Limbo size** | 169 | 0 | Eliminated |
| **Surge max (single day)** | 150 | ~40 | 73% reduction |
| **Stages with zero coverage** | 2 (Active Client, Under Contract) | 0 | Full pipeline |

†*Some contacts may appear in multiple buckets; effective unique coverage ~53%.*

### What Remains Unbucketed (~47%)

The remaining unbucketed contacts are **by design** — they were recently contacted and haven't hit their next cadence threshold yet. This is FUB working correctly: a contact drops off after a call and reappears when follow-up is due.

The critical difference: **before**, 89% unbucketed included contacts that would *never* appear in any bucket (Active Clients, Lead Limbo). **After**, all unbucketed contacts are simply between touches.

---

## 9. Implementation Sequence

### Phase 1 — Quick Wins (Week 1, ~30 minutes in FUB)

These are filter changes to existing smart lists. No new lists needed.

| Action | Bucket | Change | Impact |
|--------|--------|--------|--------|
| Fix Cool threshold | Cool | 90d → 30d | +24 contacts immediately visible |
| Repurpose Priority | Priority → Active Pipeline | Stage=Hot Prospect → Stage IN (Active Client, Under Contract), LastComm >3d | 15 revenue contacts covered |
| Fix Warm threshold | Warm | 30d → 14d | +6 contacts, aligns with FUB recommendation |

**Estimated time:** 30 minutes (3 filter edits in FUB settings)
**Immediate impact:** ~45 more contacts in buckets, revenue stage covered

### Phase 2 — New Buckets (Week 2)

| Action | Bucket | Details | Impact |
|--------|--------|---------|--------|
| Create Attempted list | NEW | Stage=Lead + Created >10d + LastComm 5-45d, Every 5 days | Fills 169-contact Lead Limbo |
| Adjust Unresponsive | Unresponsive | LastComm 14d → 45d | Eliminates surge pattern |
| Expand Timeframe Empty | Timeframe Empty | Add Stage=Lead to filter | +160 Leads needing qualification |

**Estimated time:** 45 minutes (2 new lists + 1 filter edit)
**Impact:** Lead Limbo eliminated, surge pattern fixed

### Phase 3 — Enhancement (Weeks 3-4)

| Action | Details | Impact |
|--------|---------|--------|
| Tighten New Leads | 14d → 10d window | Cleaner handoff to Attempted |
| IDX activity tagging | Use DREAMS heat scores to auto-tag "IDX Active" in FUB | Hot list can use activity signals beyond stage+timeframe |
| Review Active Pipeline cadence | Monitor if every-3-days is right for the team | Optimize based on actual usage |

### Phase 4 — Ongoing (Monthly)

| Action | Frequency | Purpose |
|--------|-----------|---------|
| Bucket population audit | Weekly for first month, then monthly | Verify counts match projections |
| Threshold tuning | Monthly | Adjust lastComm thresholds based on actual call capacity |
| Surge monitoring | After each bulk action plan | Confirm Attempted absorbs the load |
| Stage hygiene | Monthly | Move stale Active Clients to Nurture, close completed deals |

---

## Appendix A: Contact Distribution by Stage and Timeframe

| Stage | No Timeframe | 0-3 Mo | 3-6 Mo | 6-12 Mo | 12+ Mo | No Plans | **Total** |
|-------|-------------|--------|--------|---------|--------|----------|-----------|
| Lead | 160 | 22 | 8 | 6 | 1 | 1 | **198** |
| Nurture | 6 | 18 | 27 | 85 | 11 | 6 | **153** |
| Active Client | 12 | 1 | 1 | — | — | — | **14** |
| Under Contract | — | 1 | — | — | — | — | **1** |
| **Total** | **178** | **42** | **36** | **91** | **12** | **7** | **366** |

**49% of active contacts have no timeframe set.** Among Leads specifically, it's 81%.

## Appendix B: High-Heat Contacts Outside Bucket Coverage

These contacts have heat scores ≥70 (heavy IDX activity) but are in stages that no current bucket monitors:

| Contact | Stage | Heat | Priority | Timeframe | Current Bucket |
|---------|-------|------|----------|-----------|---------------|
| Christopher Graney | Lead | 100 | 66.8 | 0-3 Mo | None (too old for New Leads) |
| Bill Hollenbeck | Lead | 87.2 | 50.0 | 3-6 Mo | None (too old for New Leads) |
| Erik Stielow | Active Client | 70.8 | 50.9 | 0-3 Mo | None (no Active Client bucket) |
| Kevin Lewis | Under Contract | 100 | 74.9 | 0-3 Mo | None (no UC bucket) |

Under the redesign, Christopher Graney and Bill Hollenbeck would appear in **Attempted**, while Erik Stielow and Kevin Lewis would appear in **Active Pipeline**.

---

*Report generated by myDREAMS Analytics — 2026-02-16*
*Data source: DREAMS database (862 contacts, 367 active) + FUB API*
