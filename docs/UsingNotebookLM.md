# Using NotebookLM with myDREAMS

Guide for loading myDREAMS project files into Google NotebookLM for conversational reference and brainstorming.

## Why NotebookLM?

NotebookLM serves as a **companion layer** to our Claude Code sessions:

| Tool | Strength |
|------|----------|
| **Claude Code** | Executes code, queries databases, interacts with FUB, builds features |
| **NotebookLM** | Conversational Q&A over docs, audio overviews, brainstorming, explaining the system to others |

They complement each other - NotebookLM for understanding and reference, Claude Code for implementation.

---

## Recommended Setup: Two Notebooks

NotebookLM allows up to 50 sources per notebook. We recommend splitting into two focused notebooks for better results.

---

### Notebook 1: "myDREAMS Platform" (Architecture & Technical)

#### Tier 1 - Must Load (Core Understanding)

| File | Why |
|------|-----|
| `CLAUDE.md` | The single best overview of vision, architecture, and workflow |
| `docs/ARCHITECTURE.md` | Technical design, principles, data flow |
| `docs/ROADMAP.md` | Where we are, where we're going |
| `docs/TODO.md` | Master task list with priorities |
| `CHANGELOG.md` | What we've built and when |
| `VisionFor_myDreams.txt` | Original vision - the "why" behind everything |
| `docs/PROJECT_PLAYBOOK.md` | Executive vision and CRM independence principles |

#### Tier 2 - Data Model (The Heart of the System)

| File | Why |
|------|-----|
| `docs/DATA_DICTIONARY.md` | Complete database schema |
| `docs/PARCELS_SCHEMA.md` | Immutable land/parcel data model |
| `docs/LISTINGS_SCHEMA.md` | Transactional MLS/listing data model |
| `docs/DATA_QUALITY_TRACKING.md` | Quality metrics and baseline |

#### Tier 3 - Infrastructure & Deployment

| File | Why |
|------|-----|
| `docs/DEPLOYMENT.md` | Cloud deployment guide |
| `docs/project-index.md` | Index of all apps and components |
| `deploy/Caddyfile` | Reverse proxy config (shows URL structure) |
| `config/config.example.yaml` | Full platform config template |
| `docs/PLATFORM_ARCHITECTURE_DISCUSSION.md` | Key design tension discussion |

#### Tier 4 - Decisions & Patterns

| File | Why |
|------|-----|
| `docs/decisions/0001-dev-os-baseline.md` | ADR: tech stack choices |
| `docs/decisions/0002-vendor-directory.md` | ADR: vendor directory approach |
| `docs/patterns/assistant-roles.md` | AI assistant lanes |

#### Example Questions for This Notebook

- "What's the current state of the property enrichment pipeline?"
- "How does data flow from MLS to client packages?"
- "What's left on the TODO list for the dashboard?"
- "Explain the adapter pattern we use"
- "What are the key architectural principles?"
- "How is the production server deployed?"

---

### Notebook 2: "myDREAMS Sales & Scoring" (Business Process)

#### Tier 1 - Sales Framework

| File | Why |
|------|-----|
| `docs/SALES_FLOW.md` | Dual-input funnel model |
| `docs/PIPELINE_FRAMEWORK.md` | 4-phase sales pipeline |
| `templates/buyer_requirements.md` | Buyer requirements template |

#### Tier 2 - Scoring System

| File | Why |
|------|-----|
| `apps/fub-to-sheets/SCORING_GUIDE.md` | Heat, Value, Relationship, Priority scoring |
| `apps/fub-to-sheets/SCORE_CAPPING_AND_STAGES_UPDATE.md` | Score capping and stage multipliers |
| `apps/fub-to-sheets/TIER1_ENHANCEMENTS_SUMMARY.md` | Form submission tracking |

#### Tier 3 - App-Specific Docs

| File | Why |
|------|-----|
| `apps/fub-core/README.md` | FUB integration library |
| `apps/vendor-directory/README.md` | Vendor tracking |
| `apps/buyer-workflow/schema.sql` | Intake forms and showing management schema |
| `mcp-servers/README.md` | MCP server capabilities |

#### Example Questions for This Notebook

- "How does lead scoring work?"
- "Walk me through the buyer qualification process"
- "What determines a lead's priority score?"
- "Explain the QUALIFY to NURTURE pipeline"
- "What's the difference between Heat and Value scores?"
- "How do stage multipliers affect scoring?"

---

## What to Skip

These files don't add value in NotebookLM:

| Skip | Reason |
|------|--------|
| `.claude/` commands/skills | Claude Code-specific, not useful for Q&A |
| `archive/` | Deprecated code |
| `requirements.txt` files | Dependency lists aren't useful for conversation |
| Systemd service files | Too operational/granular |
| Apify evaluation reports | One-time analysis, not ongoing reference |
| `CONTINUE_SESSION.md` | Session-specific context |

---

## Tips for Getting the Most Out of NotebookLM

1. **Use the Audio Overview feature** - Generate podcast-style summaries to listen to while driving between showings
2. **Keep notebooks focused** - Two focused notebooks beat one overloaded one
3. **Refresh periodically** - After major milestones, re-upload updated versions of CHANGELOG.md, ROADMAP.md, and TODO.md
4. **Use it for client explanations** - Ask NotebookLM to explain parts of the system in plain language for conversations with team members or partners
5. **Brainstorm with it** - Ask "what if" questions about architecture decisions or sales process improvements

---

## Maintenance

When we ship significant features or make architectural changes:

1. Update the relevant source files in NotebookLM (especially CHANGELOG.md, ROADMAP.md, TODO.md)
2. If new documentation is created that fits a notebook's scope, add it as a source
3. Remove sources that become obsolete or get merged into other docs
