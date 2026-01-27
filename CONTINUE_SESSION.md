# Continue Session Prompt

Copy the text below to start a new Claude Code session:

---

## Context

I'm implementing an Apify scraper evaluation system for updating property data in myDREAMS. Here's the progress so far:

### Completed:

1. **Created `apps/apify-importer/` directory** with:
   - `config.py` - Configuration with Apify actor IDs, pricing, field mappings
   - `evaluate_scrapers.py` - Test harness to run and compare scrapers
   - `evaluation_results.md` - Template to document findings

2. **Architecture confirmed:**
   - `package_properties` table already has `added_at` column (no change needed)
   - ~9K properties in database (8216 ACTIVE, 539 PENDING, 222 CONTINGENT)

### Next Steps:

1. **Run the evaluation:**
   ```bash
   cd /home/bigeug/myDREAMS/apps/apify-importer

   # Export 50 test properties
   python evaluate_scrapers.py --export-test-set

   # Set Apify token (get from https://console.apify.com/account#/integrations)
   export APIFY_TOKEN='your_token'

   # Run evaluations
   python evaluate_scrapers.py --run redfin_triangle
   python evaluate_scrapers.py --run redfin_epctex
   python evaluate_scrapers.py --run redfin_mantisus
   python evaluate_scrapers.py --run zillow_maxcopell

   # Generate comparison report
   python evaluate_scrapers.py --analyze
   ```

2. **After evaluation, build the production importer:**
   - Create `apps/apify-importer/apify_importer.py`
   - Map Apify fields to dreams.db schema
   - Implement source hierarchy (PropStream > Redfin > Zillow)
   - Log changes to `property_changes` table

3. **Full data update:**
   - Run winning scraper on all 11 WNC counties
   - Import to dreams.db
   - Verify change tracking working

### Key Files:
- Plan details: See `docs/TODO.md` or the plan at top of this conversation
- Evaluation template: `apps/apify-importer/evaluation_results.md`
- Test harness: `apps/apify-importer/evaluate_scrapers.py`
- Reference importer: `apps/redfin-importer/propstream_importer.py`

### Budget:
- Evaluation: ~$0.25 (covered by free tier)
- Full update: ~$30-40 one-time

---

## If you need to continue:

Please help me continue with the Apify scraper evaluation. The files have been created in `apps/apify-importer/`. Next I need to:

1. Create an Apify account and get the API token
2. Export the test property set
3. Run the evaluations
4. Analyze results and pick the winning scrapers
5. Build the production importer

---
