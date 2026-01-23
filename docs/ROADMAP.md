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

## Phase 1.5: Cloud Migration (In Progress)

### Phase 1 - Local Prep (Completed)
| Task | Status | Notes |
|------|--------|-------|
| Fix hardcoded paths | Done | Use `Path(__file__)` relative paths |
| API key authentication | Done | `DREAMS_API_KEY` env var, `X-API-Key` header |
| Dashboard basic auth | Done | `DASHBOARD_USERNAME/PASSWORD` env vars |
| Chrome extension API key | Done | Settings panel, stored in sync storage |
| Production URLs in manifest | Done | `wncmountain.homes` host permissions |
| Update .env.example | Done | Added auth variables |

### Phase 2 - VPS Setup (Ready)
| Task | Status | Notes |
|------|--------|-------|
| Create systemd services | Done | `deploy/systemd/mydreams-*.service` |
| Create Caddyfile | Done | `deploy/Caddyfile` with subdomains |
| Create setup script | Done | `deploy/scripts/setup-vps.sh` |
| Create deploy script | Done | `deploy/scripts/deploy.sh` |
| Create backup script | Done | `deploy/scripts/backup.sh` with B2 |
| Deployment guide | Done | `docs/DEPLOYMENT.md` |

**Next: Provision VPS and run setup script**

### Phase 3 - DNS & SSL
- [ ] Transfer DNS to Cloudflare
- [ ] Create A records for api/app/leads subdomains
- [ ] Configure Caddy reverse proxy

### Phase 4 - Migration
- [ ] Export and transfer SQLite database
- [ ] Update Chrome extension to production URL
- [ ] Test end-to-end property capture

### Phase 5 - Cron & Backup
- [ ] Set up cron jobs (FUB sync, property monitor)
- [ ] Configure daily backup to Backblaze B2
- [ ] Set up UptimeRobot monitoring

---

## Phase 2: Lead Scoring & Matching (In Progress)

### Lead Scoring System
- [x] Multi-dimensional scoring: Heat, Value, Relationship, Priority
- [x] Behavioral signal processing from CRM activities (intent signals)
- [x] Daily priority contact list generation
- [ ] Score decay for inactive leads

### Unified Dashboard
- [x] Contacts list view with filtering by stage/heat
- [x] Contact detail view with scores and activity stats
- [x] Unified dashboard home with property + contact overview
- [x] SQLite as single source of truth for contacts

### Buyer-Property Matching
- [x] Contact-property relationship table (contact_properties)
- [x] Linked properties in contact detail view
- [ ] Weighted matching algorithm implementation
- [ ] Stated requirements vs. behavioral preferences
- [ ] Match score breakdown visualization

### Enhanced FUB Data Architecture (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| Score history table | Done | `contact_scoring_history` - daily snapshots |
| Communications table | Done | `contact_communications` - individual calls/texts |
| Events table | Done | `contact_events` - website visits, property views |
| Trend calculation | Done | Warming/cooling/stable based on score delta |
| Activity timeline | Done | Combined communications + events on contact detail |
| Trend mini-chart | Done | 7-day heat score visualization |
| Trend indicators | Done | Column on contacts list |

### Action Management System (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| contact_actions table | Done | Persistent actions that survive FUB syncs |
| contact_daily_activity table | Done | Aggregated daily stats for trend queries |
| scoring_runs table | Done | Audit trail for sync runs |
| Actions UI on contact detail | Done | Add/complete actions with modal |
| My Actions page (`/actions`) | Done | Dashboard of all pending actions |
| Scoring History page | Done | `/system/scoring-runs` audit view |
| Metrics dropdown | Done | Navigation menu on main dashboard |
| Backfill script | Done | Historical daily activity from events |

### CRM Integration Enhancements
- [x] Follow Up Boss activity sync to SQLite (fub-to-sheets)
- [x] Intent signals: repeat views, high favorites, activity burst, sharing
- [x] Activity timeline in dashboard (communications + events)
- [x] Score trend tracking and visualization
- [x] **Email tracking from FUB API** - Now fetches emails and includes in relationship scoring
- [ ] Lead requirements extraction from CRM notes
- [ ] Automatic note push on property matches

---

## Phase 3: Automation & Monitoring (In Progress)

### Property Monitoring
- [x] Price change detection (logged to SQLite)
- [x] Status change alerts (logged to SQLite)
- [x] VPS deployment scripts (`vps_setup.sh`, `run_monitor.sh`)
- [ ] New listing alerts for saved searches
- [ ] Historical price chart generation

**Scraper Status:**
| Source | Status | Notes |
|--------|--------|-------|
| Redfin | Working | Primary scraper via Playwright |
| Zillow | Broken | Code exists, blocked in practice |
| Realtor.com | Not Implemented | Falls back to Redfin scraper |

### Automated Reports
- [x] Daily priority call list email
- [x] Property changes in daily email report
- [x] Today's Changes section on dashboard
- [ ] Weekly market summary
- [ ] Monthly lead activity report
- [ ] Customizable alert thresholds

### Properties Viewed Feature (New - January 2026)
| Task | Status | Notes |
|------|--------|-------|
| Contact property summary | Done | Aggregated view history per contact |
| Who else is viewing | Done | Shows other contacts viewing same property |
| Properties Viewed UI | Done | Table on contact detail page |
| View count tracking | Done | Count of views per property |
| Favorited/Shared status | Done | Icons for favorites and shares |

### Configuration Page (Planned)
- [ ] Admin settings page for dashboard
- [ ] Configurable sync intervals
- [ ] API key management
- [ ] User preferences storage
- [ ] Feature toggles

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

### Click-to-Call / FUB Dialer Integration (Planned)
Deep-link phone numbers in dashboard to FUB contact pages for dialing.
- [ ] Add FUB person ID to contact records (already have from sync)
- [ ] Make phone numbers clickable links: `https://app.followupboss.com/2/people/{id}`
- [ ] Implement in contact list and contact detail views
- [ ] Calls logged automatically in FUB timeline

**Rationale**: Team prefers FUB dialer over custom VoIP. Deep linking keeps workflow unified.
- Cost: $0 (uses existing FUB subscription)
- Alternative considered: KDE Connect passthrough, Twilio VoIP (not needed)

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
| ~~Email tracking not implemented~~ | High | Done - Added email fetching from FUB API |
| Zillow scraper blocked | Medium | Code exists but site blocks scraping |
| Realtor.com scraper not implemented | Low | Falls back to Redfin pattern |
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

---

## Strategic Discussion Queued

**Platform Architecture Discussion** - See [PLATFORM_ARCHITECTURE_DISCUSSION.md](PLATFORM_ARCHITECTURE_DISCUSSION.md)

The tension between personal workflow optimization vs. building a configurable platform for others. Topics include:
- Data architecture abstraction
- CRM-agnostic design
- Plugin/adapter patterns
- Configuration vs. code trade-offs

---

## Contributing

1. Check this roadmap before starting new features
2. Update status when completing items
3. Add rollback points for significant changes
4. Document architectural decisions in ARCHITECTURE.md

---

*Roadmap maintained by Joseph & Claude*
*Last updated: January 23, 2026 - Action Management System, Metrics dropdown, Scoring History view*
