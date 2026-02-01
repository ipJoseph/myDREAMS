# myDREAMS Sales Flow Model

This document describes the sales flow architecture powering the myDREAMS dashboard.

## Overview

myDREAMS uses a **dual-input funnel model** where two independent streams (People and Properties) converge into Pursuits that lead to Contracts.

## The Three-Step Sales Process

1. **Understand buyer requirements** → Intake Forms
2. **Know available properties** → Unified Properties Database
3. **Connect the two** → Pursuits → Contracts

## Data Flow Diagram

```
                    IDX Website (JonTharpHomes.com)
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
       ┌──────────┐                   ┌─────────────┐
       │  LEADS   │                   │ PROPERTIES  │
       │          │                   │             │
       │ Contact  │                   │ Searched    │
       │ + Heat   │                   │ Viewed      │◄──── MLS Feeds
       │ scoring  │                   │ Saved       │◄──── PropStream
       └────┬─────┘                   │ Shared      │
            │ Qualify                 └──────┬──────┘
            ▼                                │
       ┌──────────┐                          │
       │  BUYERS  │                          │
       │          │                          │
       │ Qualified│                          │
       │ + Intake │                          │
       │ Forms    │                          │
       └────┬─────┘                          │
            │                                │
            └──────────────┬─────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  PURSUITS   │
                    │             │
                    │ Buyer +     │
                    │ Property    │
                    │ Portfolio   │
                    │             │
                    │ (IDX activity│
                    │  seeds the  │
                    │  portfolio) │
                    └──────┬──────┘
                           │ Buyer selects
                           ▼
                    ┌─────────────┐
                    │  CONTRACTS  │
                    │             │
                    │ Committed   │
                    │ Buyer +     │
                    │ Property    │
                    └──────┬──────┘
                           │ Close
                           ▼
                    ┌─────────────┐
                    │   CLOSED    │
                    └─────────────┘
```

## Pipeline Stages Defined

### LEADS
- **Source**: IDX website registration, manual entry, referrals
- **Data**: Contact info + heat scoring from IDX activity
- **Key Metrics**: Total count, new in last 7 days
- **Exit Criteria**: Qualified through conversation → becomes BUYER

### BUYERS
- **Definition**: Qualified lead with documented requirements
- **Data**: Intake form capturing price range, location, beds/baths, features
- **Key Metrics**: Count, how many need intake forms
- **Exit Criteria**: Has intake form + enters property search → creates PURSUIT

### PROPERTIES
- **Sources**: MLS feeds (Canopy, Carolina Smokies), PropStream, IDX saves
- **Data**: Unified schema with price, location, features, status
- **Key Metrics**: Active listings, new today, price drops
- **Flow**: Properties flow into Pursuits when matched to buyer requirements

### PURSUITS
- **Definition**: Active buyer + their property portfolio
- **Components**:
  - Buyer (qualified lead with intake)
  - Criteria summary (from intake form)
  - Property portfolio (matched, saved, suggested properties)
- **Key Metrics**: Active pursuits, total properties in play
- **Exit Criteria**: Buyer selects property → becomes CONTRACT

### CONTRACTS
- **Definition**: Committed buyer + specific property under contract
- **Key Metrics**: Count, pipeline value
- **Exit Criteria**: Close → CLOSED

### CLOSED
- **Definition**: Completed transactions
- **Key Metrics**: Count, volume (monthly/annual)

## Key Insight: IDX Activity Seeds Both Pipelines

When a visitor uses the IDX website (JonTharpHomes.com):

1. **People Pipeline**: Their registration creates a Lead, their activity generates Heat score
2. **Properties Pipeline**: The properties they view/save/share get logged

When a Lead qualifies as a Buyer:
- Their IDX activity history becomes the **seed** of their Pursuit portfolio
- Properties they've already shown interest in automatically populate

## Scoring System

### Heat Score (0-100)
Measures IDX engagement:
- Website visits
- Properties viewed
- Properties favorited
- Properties shared
- Repeat views (intent signal)
- Activity bursts (intent signal)

### Value Score (0-100)
Measures revenue potential:
- Price range (higher = more value)
- Timeline urgency
- Pre-qualification status

### Relationship Score (0-100)
Measures agent-lead communication:
- Call frequency (inbound + outbound)
- Text exchanges
- Email engagement
- Response times

### Priority Score (0-100)
Customizable blend of Heat + Value + Relationship, configured in system settings.

## Dashboard Alignment

The home dashboard reflects this flow:

| Dashboard Section | Sales Stage |
|-------------------|-------------|
| Priority Actions | Immediate tasks for today |
| Pipeline Snapshot | Visual of dual-input funnel |
| Hottest Leads | LEADS with high Heat scores |
| Overnight Changes | New LEADS, property changes |
| Active Pursuits | PURSUITS with property portfolios |

## Data Model

### Pursuit Table
```sql
pursuits (
    id,
    buyer_id,           -- FK to leads
    intake_form_id,     -- FK to intake_forms
    fub_deal_id,        -- FUB deal ID if synced
    name,               -- "John Smith — Primary Residence"
    status,             -- active, paused, converted, abandoned
    criteria_summary,   -- "3BR, $300-400K, Franklin"
    created_at,
    updated_at
)
```

### Pursuit Properties Table
```sql
pursuit_properties (
    id,
    pursuit_id,         -- FK to pursuits
    property_id,        -- FK to listings
    status,             -- suggested, sent, viewed, favorited, rejected
    source,             -- idx_saved, agent_added, auto_match
    added_at,
    sent_at,
    viewed_at,
    notes
)
```

## Future Integrations

- **Task Sync**: Todoist ↔ FUB tasks tied to Pursuits
- **Obsidian**: Narrative knowledge linked to structured data
- **ShowingTime**: Showings integrated into Pursuit workflow
- **Email/SMS**: "Send Update" from Pursuit portfolio
