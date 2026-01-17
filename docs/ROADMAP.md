# myDREAMS Roadmap

*Current Status & Future Development*

---

## Current Version: v1.0 (Production)

### Core Features (Completed)

| Feature | Status | Notes |
|---------|--------|-------|
| Property Scraping | Done | Zillow, Redfin, Realtor.com via Chrome Extension v3.9.16 |
| SQLite Database | Done | Canonical data store with WAL mode |
| Property API | Done | Flask REST API on port 5000 |
| Property Dashboard | Done | Flask web UI on port 5001 |
| Notion Sync | Done | Bi-directional property sync every 60s |
| IDX Validation | Done | MLS# validation with address fallback |
| IDX Portfolio | Done | Bulk portfolio creation on IDX site |
| Lead Management | Done | FUB to Google Sheets sync |

### Recent Additions (January 2026)

| Feature | Commit | Description |
|---------|--------|-------------|
| IDX MLS Validation | `f157fb0` | Automatic validation with address fallback |
| On-Demand Validation | `016271b` | Validates properties when creating IDX portfolio |
| Redfin Scraper Fix | `f157fb0` | Fixed incorrect "Sold" status extraction |
| Dashboard Layout | `0917cba` | Reordered columns, IDX status badges |
| Default Search Names | `016271b` | YYMMDD.HHMM.ClientName format |

---

## Phase 2: Lead Scoring & Matching (Planned)

### Lead Scoring System
- [ ] Multi-dimensional scoring: Heat, Value, Relationship, Priority
- [ ] Behavioral signal processing from CRM activities
- [ ] Daily priority contact list generation
- [ ] Score decay for inactive leads

### Buyer-Property Matching
- [ ] Weighted matching algorithm implementation
- [ ] Stated requirements vs. behavioral preferences
- [ ] Match score breakdown visualization
- [ ] Suggested properties dashboard

### CRM Integration Enhancements
- [ ] Follow Up Boss activity sync
- [ ] Activity timeline in dashboard
- [ ] Lead requirements extraction from CRM notes
- [ ] Automatic note push on property matches

---

## Phase 3: Automation & Monitoring (Planned)

### Property Monitoring
- [ ] Price change detection
- [ ] Status change alerts (Active → Pending → Sold)
- [ ] New listing alerts for saved searches
- [ ] Historical price chart generation

### Automated Reports
- [ ] Daily priority call list email
- [ ] Weekly market summary
- [ ] Monthly lead activity report
- [ ] Customizable alert thresholds

### Package Generation
- [ ] PDF showing packages
- [ ] Branded property flyers
- [ ] Comparative market analysis
- [ ] Client presentation decks

---

## Phase 4: Scale & Polish (Future)

### Performance
- [ ] Property search optimization
- [ ] Batch Notion sync for large datasets
- [ ] Database indexing review
- [ ] Memory usage optimization

### User Experience
- [ ] Dark mode support
- [ ] Keyboard shortcuts
- [ ] Bulk actions interface
- [ ] Mobile-responsive dashboard

### Infrastructure
- [ ] Backup automation
- [ ] Log rotation
- [ ] Health monitoring
- [ ] Configuration validation

---

## Known Issues & Tech Debt

| Issue | Priority | Status |
|-------|----------|--------|
| ~~Multiple extension versions in repo~~ | Low | Done - moved to archive/ |
| ~~Backup files scattered~~ | Low | Done - archive/ created |
| Inconsistent error handling | Medium | Standardize patterns |
| Missing unit tests | Medium | Add test coverage |

---

## Rollback Points

| Commit | Date | Description |
|--------|------|-------------|
| `016271b` | Jan 17, 2026 | Current stable - default search names |
| `0917cba` | Jan 17, 2026 | Pre-validation - dashboard layout only |
| `f157fb0` | Jan 17, 2026 | IDX validation + scraper fix |

---

## Contributing

1. Check this roadmap before starting new features
2. Update status when completing items
3. Add rollback points for significant changes
4. Document architectural decisions in ARCHITECTURE.md

---

*Roadmap maintained by Joseph & Claude*
*Last updated: January 17, 2026*
