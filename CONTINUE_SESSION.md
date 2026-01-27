# Continue Session Prompt

Copy the text below to start a new Claude Code session:

---

## Context

The Apify scraper evaluation and production importer are complete. Here's the summary:

### Completed:

1. **Scraper Evaluation** - Tested multiple Apify scrapers:
   - Winner: `tri_angle/redfin-search` (10/10 must-have fields, free tier)
   - Other scrapers require paid rental

2. **Production Importer Built** - `apps/apify-importer/apify_importer.py`:
   - Scrapes properties by county using correct Redfin region IDs
   - Maps Redfin fields to dreams.db schema
   - Matches existing properties by redfin_id, MLS number, or address
   - Detects and logs price/status changes to `property_changes` table
   - Tested on Graham County: 101 new properties, 4 price changes detected

3. **Config Updated** - Correct Redfin region IDs for all 11 WNC counties

### How to Run Full Import:

```bash
cd /home/bigeug/myDREAMS/apps/apify-importer

# Token is in .env file
source .env  # or: export APIFY_TOKEN='your_token_here'

# Import single county
python3 apify_importer.py --county Buncombe

# Import all 11 WNC counties
python3 apify_importer.py --all-counties

# Dry run to see what would happen
python3 apify_importer.py --all-counties --dry-run
```

### Cost Estimate:
- ~9,000 active properties across 11 counties
- At $0.001/result = ~$9 for full update
- Free tier: 5,000 results/month

### Next Steps (Optional):

1. **Run full import** on all 11 WNC counties to update database
2. **Set up scheduled updates** (cron job or GitHub Action)
3. **Build price change alerts** - email/SMS when tracked properties change

### Key Files:
- Importer: `apps/apify-importer/apify_importer.py`
- Config: `apps/apify-importer/config.py`
- Evaluation: `apps/apify-importer/evaluate_scrapers.py`

---

## If you need to continue:

The Apify importer is ready to use. Run `python3 apify_importer.py --all-counties` to update all WNC property data, or continue with building scheduled updates or alerts.

---
