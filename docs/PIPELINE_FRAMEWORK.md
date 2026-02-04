# Pipeline Framework: QUALIFY → CURATE → CLOSE → NURTURE

The canonical sales pipeline for myDREAMS. Every client moves through these four phases.

---

## Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   QUALIFY   │───▶│   CURATE    │───▶│    CLOSE    │───▶│   NURTURE   │
│             │    │             │    │             │    │             │
│ Lead → Buyer│    │ Requirements│    │ Contract to │    │ Past Client │
│ Validation  │    │ → Properties│    │ Keys        │    │ Relationship│
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

---

## Phase 1: QUALIFY

**Goal**: Convert a lead into a qualified buyer with clear requirements.

### What Happens
- Lead comes in (IDX, referral, Zillow, open house)
- Initial contact and rapport building
- Determine motivation, timeline, and financial readiness
- Capture buyer requirements in intake form
- Get pre-approval or proof of funds

### Key Deliverables
- Signed Buyer Agency Agreement
- Completed intake form (requirements captured)
- Pre-approval letter or proof of funds
- Clear understanding of timeline and motivation

### Exit Criteria
- [ ] Intake form completed with property criteria
- [ ] Financing verified (pre-approval or cash proof)
- [ ] Buyer agreement signed
- [ ] Client folder created with documents

### FUB Stage Mapping
- `New Lead` → Initial contact
- `Prospect` → Engaged, gathering info
- `Active Buyer` → Qualified, ready for CURATE

### Google Drive Folder
```
01_QUALIFY/
└── Smith.John/
    ├── requirements.md          # Syncs with intake_forms table
    ├── pre_approval.pdf
    ├── buyer_agreement.pdf
    └── notes.md
```

---

## Phase 2: CURATE

**Goal**: Match buyer requirements to properties and schedule showings.

### What Happens
- Run property searches based on intake form criteria
- Create property packages for presentation
- Send packages to client for review
- Client provides feedback (favorites, ratings, showing requests)
- Schedule and conduct property showings
- Iterate based on feedback

### Key Deliverables
- Property packages sent to client
- Showing tours completed
- Client feedback collected
- Refined requirements if needed

### Exit Criteria
- [ ] At least one showing tour completed
- [ ] Client has identified properties of interest
- [ ] Ready to write an offer

### FUB Stage Mapping
- `Active Buyer` → Actively searching
- Custom tag: `Showing Scheduled` / `Shown Properties`

### Google Drive Folder
```
02_CURATE/
└── Smith.John/
    ├── requirements.md          # Carried from QUALIFY
    ├── packages/
    │   ├── 260201.highlands.md  # Package: YYMMDD.area
    │   └── 260205.franklin.md
    ├── showing_feedback/
    │   └── 260210.tour1.md
    └── offers/
        └── 123.Main.St/         # Offer attempts
```

---

## Phase 3: CLOSE

**Goal**: From accepted offer to keys in hand.

### What Happens
- Write and submit offer
- Negotiate terms
- Contract execution (binding agreement)
- Due diligence period
  - Inspections
  - Appraisal
  - Title work
  - Repairs/negotiations
- Final walkthrough
- Closing

### Key Deliverables
- Executed purchase agreement
- All due diligence completed
- Clear to close
- Closing documents signed
- Keys transferred

### Exit Criteria
- [ ] Closing completed
- [ ] Commission received
- [ ] Client has keys
- [ ] All documents archived

### FUB Stage Mapping
- `Under Contract` → Offer accepted
- `Closed` → Transaction complete

### Google Drive Folder
```
03_CLOSE/
└── Smith.John.123.Main.St/      # Client + Address
    ├── requirements.md          # Reference
    ├── contract/
    │   ├── purchase_agreement.pdf
    │   └── addenda/
    ├── due_diligence/
    │   ├── inspection_report.pdf
    │   ├── repair_request.pdf
    │   └── appraisal.pdf
    ├── financing/
    │   └── commitment_letter.pdf
    └── closing/
        ├── settlement_statement.pdf
        └── deed.pdf
```

---

## Phase 4: NURTURE

**Goal**: Maintain relationship for referrals and repeat business.

### What Happens
- Post-closing follow-up
- Anniversary touchpoints
- Market updates relevant to their area
- Referral requests
- Track for future transactions (sell, buy again, investment)

### Key Deliverables
- Consistent touchpoints (quarterly minimum)
- Updated contact info
- Referral program enrollment
- Future transaction pipeline

### Exit Criteria
- N/A - Ongoing relationship

### FUB Stage Mapping
- `Past Client` → Closed transaction, in nurture

### Google Drive Folder
```
04_NURTURE/
└── Smith.John/
    ├── closed_transactions/
    │   └── 123.Main.St/         # Archived from CLOSE
    └── touchpoints.md           # Log of interactions
```

---

## Folder Structure Summary

```
myDREAMS Clients/
├── 00_TEMPLATES/
│   ├── buyer_requirements.md
│   ├── seller_requirements.md
│   ├── offer_checklist.md
│   ├── due_diligence_checklist.md
│   └── closing_checklist.md
│
├── 01_QUALIFY/
│   └── [Lastname.Firstname]/
│
├── 02_CURATE/
│   └── [Lastname.Firstname]/
│
├── 03_CLOSE/
│   └── [Lastname.Firstname.Address]/
│
├── 04_NURTURE/
│   └── [Lastname.Firstname]/
│
└── 99_ARCHIVE/
    └── [Lost deals, cancelled searches]
```

### Naming Conventions
- **Client folders**: `Lastname.Firstname` (dot separator for clean sorting)
- **Transaction folders**: `Lastname.Firstname.Address` (property-specific in CLOSE)
- **Date prefixes**: `YYMMDD` for packages, offers, and dated documents
- **Package names**: `YYMMDD.area.md` (e.g., `260201.highlands.md`)

---

## Database Integration

### Tables by Phase

| Phase | Primary Tables | Purpose |
|-------|----------------|---------|
| QUALIFY | `leads`, `intake_forms` | Contact info, requirements capture |
| CURATE | `property_packages`, `package_properties`, `showings` | Property matching, presentations |
| CLOSE | `showings`, `property_changes` | Transaction tracking |
| NURTURE | `leads` (stage=Past Client) | Relationship maintenance |

### Sync Strategy

**Markdown ↔ Database Sync**:
- `requirements.md` in client folders syncs with `intake_forms` table
- YAML frontmatter contains machine-readable criteria
- Body contains human-readable notes and context
- Two-way sync: edit in either place, sync to the other

---

## Morning Briefing Integration

The dashboard morning briefing should surface:

1. **QUALIFY Phase**
   - New leads needing initial contact
   - Leads with incomplete intake forms
   - Pending pre-approvals

2. **CURATE Phase**
   - Buyers needing property packages (has requirements, no recent packages)
   - Showings scheduled today
   - Package feedback waiting for review

3. **CLOSE Phase**
   - Due diligence deadlines approaching
   - Inspections scheduled
   - Closing dates this week

4. **NURTURE Phase**
   - Anniversary touchpoints due
   - Past clients with recent activity (re-engagement opportunity)

---

## Implementation Notes

### Phase Transitions

Moving a client between phases:
1. Update FUB stage
2. Move Google Drive folder (or create new subfolder)
3. Update `requirements.md` with phase metadata
4. Database records follow automatically via sync

### Lost Deals

When a deal falls through:
1. Move folder to `99_ARCHIVE/`
2. Update FUB stage to appropriate status
3. Add notes explaining what happened
4. Consider for future re-engagement

---

*Last Updated: 2025-02-04*
*Version: 1.0*
