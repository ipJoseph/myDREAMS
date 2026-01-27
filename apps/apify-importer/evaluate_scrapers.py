#!/usr/bin/env python3
"""
Apify Scraper Evaluation Tool

Test and compare multiple Apify scrapers to find the best fit for myDREAMS.

Usage:
    # Export test properties first
    python evaluate_scrapers.py --export-test-set

    # Run evaluation (requires APIFY_TOKEN env var)
    python evaluate_scrapers.py --run-redfin
    python evaluate_scrapers.py --run-zillow
    python evaluate_scrapers.py --run-all

    # Analyze results
    python evaluate_scrapers.py --analyze
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import (
    APIFY_TOKEN, DB_PATH, ACTORS, PRICING,
    REQUIRED_FIELDS, VALIDATION_RULES, WNC_COUNTIES
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Output directory for evaluation results
OUTPUT_DIR = Path(__file__).parent / 'evaluation_output'


class ApifyClient:
    """Simple Apify API client."""

    def __init__(self, token: str):
        self.token = token
        self.base_url = 'https://api.apify.com/v2'

    def run_actor(self, actor_id: str, input_data: dict,
                  wait_secs: int = 300) -> Optional[dict]:
        """Run an actor and wait for results."""
        try:
            import requests
        except ImportError:
            logger.error("requests library required. Install with: pip install requests")
            return None

        # Start the actor run
        url = f"{self.base_url}/acts/{actor_id}/runs"
        headers = {'Authorization': f'Bearer {self.token}'}

        logger.info(f"Starting actor: {actor_id}")
        response = requests.post(url, json=input_data, headers=headers)

        if response.status_code != 201:
            logger.error(f"Failed to start actor: {response.text}")
            return None

        run_data = response.json()['data']
        run_id = run_data['id']
        logger.info(f"Actor run started: {run_id}")

        # Wait for completion
        status_url = f"{self.base_url}/actor-runs/{run_id}"
        start_time = time.time()

        while time.time() - start_time < wait_secs:
            response = requests.get(status_url, headers=headers)
            status = response.json()['data']['status']

            if status == 'SUCCEEDED':
                logger.info(f"Actor run completed successfully")
                break
            elif status in ['FAILED', 'ABORTED', 'TIMED-OUT']:
                logger.error(f"Actor run failed with status: {status}")
                return None

            time.sleep(5)
        else:
            logger.error(f"Actor run timed out after {wait_secs}s")
            return None

        # Get results from default dataset
        dataset_id = run_data['defaultDatasetId']
        dataset_url = f"{self.base_url}/datasets/{dataset_id}/items"

        response = requests.get(dataset_url, headers=headers)
        return response.json()

    def get_run_stats(self, run_id: str) -> dict:
        """Get usage statistics for a run."""
        try:
            import requests
        except ImportError:
            return {}

        url = f"{self.base_url}/actor-runs/{run_id}"
        headers = {'Authorization': f'Bearer {self.token}'}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()['data']
            return {
                'status': data.get('status'),
                'started_at': data.get('startedAt'),
                'finished_at': data.get('finishedAt'),
                'compute_units': data.get('stats', {}).get('computeUnits', 0),
                'run_time_secs': data.get('stats', {}).get('runTimeSecs', 0),
            }
        return {}


class ScraperEvaluator:
    """Evaluate and compare Apify scrapers."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.client = ApifyClient(APIFY_TOKEN) if APIFY_TOKEN else None
        OUTPUT_DIR.mkdir(exist_ok=True)

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def export_test_set(self, count: int = 50) -> List[dict]:
        """Export a diverse set of properties for testing.

        Selects properties across:
        - Multiple cities
        - Various price ranges
        - Different statuses
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get diverse sample
        # 20 from Asheville area (most active)
        # 15 from other major cities
        # 10 from smaller towns
        # 5 from different price ranges

        query = '''
            WITH ranked AS (
                SELECT
                    id, address, city, county, price, status, mls_number,
                    beds, baths, sqft,
                    ROW_NUMBER() OVER (PARTITION BY city ORDER BY RANDOM()) as rn
                FROM properties
                WHERE status IN ('ACTIVE', 'PENDING', 'CONTINGENT')
                AND price IS NOT NULL
                AND address IS NOT NULL
            )
            SELECT * FROM ranked WHERE rn <= 3
            ORDER BY
                CASE
                    WHEN city = 'Asheville' THEN 1
                    WHEN city IN ('Hendersonville', 'Brevard', 'Waynesville', 'Franklin') THEN 2
                    ELSE 3
                END,
                RANDOM()
            LIMIT ?
        '''

        cursor.execute(query, (count,))
        properties = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Save to file
        output_file = OUTPUT_DIR / 'test_properties.json'
        with open(output_file, 'w') as f:
            json.dump(properties, f, indent=2)

        logger.info(f"Exported {len(properties)} test properties to {output_file}")

        # Also create address list for easy copy/paste
        addr_file = OUTPUT_DIR / 'test_addresses.txt'
        with open(addr_file, 'w') as f:
            for p in properties:
                f.write(f"{p['address']}\n")

        # Summary stats
        cities = {}
        for p in properties:
            cities[p['city']] = cities.get(p['city'], 0) + 1

        print("\nTest Set Summary:")
        print(f"  Total properties: {len(properties)}")
        print(f"  Cities covered: {len(cities)}")
        print(f"  Top cities: {sorted(cities.items(), key=lambda x: -x[1])[:5]}")
        print(f"  Price range: ${min(p['price'] or 0 for p in properties):,} - ${max(p['price'] or 0 for p in properties):,}")

        return properties

    def build_redfin_input(self, scraper_key: str, addresses: List[str]) -> dict:
        """Build input for a Redfin scraper."""

        if scraper_key == 'redfin_triangle':
            # tri_angle/redfin-search uses search URLs
            # For evaluation, we'll search by county
            return {
                'searchUrls': [
                    f"https://www.redfin.com/county/{info['redfin_region']}/NC/{name}-County/filter/property-type=house,min-beds=1"
                    for name, info in list(WNC_COUNTIES.items())[:3]  # Just 3 counties for test
                ],
                'maxItems': 50,
            }

        elif scraper_key == 'redfin_epctex':
            # epctex/redfin-scraper
            return {
                'search': [
                    {'term': 'Asheville, NC', 'propertyType': 'house'},
                ],
                'maxItems': 50,
            }

        elif scraper_key == 'redfin_mantisus':
            # mantisus/redfin-fast-scraper
            return {
                'startUrls': [
                    {'url': 'https://www.redfin.com/city/570/NC/Asheville'}
                ],
                'maxProperties': 50,
            }

        return {}

    def build_zillow_input(self, scraper_key: str, addresses: List[str]) -> dict:
        """Build input for a Zillow scraper."""

        if scraper_key == 'zillow_maxcopell':
            # maxcopell/zillow-scraper
            return {
                'searchTerms': ['Asheville, NC', 'Brevard, NC', 'Franklin, NC'],
                'maxItems': 50,
            }

        elif scraper_key == 'zillow_detail':
            # maxcopell/zillow-detail-scraper - needs zpids
            # We'd need to get zpids from another source first
            return {
                'zpids': [],  # Would need to populate
            }

        return {}

    def run_evaluation(self, scraper_key: str) -> dict:
        """Run a single scraper evaluation."""
        if not self.client:
            logger.error("APIFY_TOKEN not set. Set environment variable or add to .env")
            return {'error': 'No API token'}

        actor_id = ACTORS.get(scraper_key)
        if not actor_id:
            logger.error(f"Unknown scraper: {scraper_key}")
            return {'error': f'Unknown scraper: {scraper_key}'}

        # Load test addresses
        test_file = OUTPUT_DIR / 'test_properties.json'
        if not test_file.exists():
            logger.info("Test set not found, exporting...")
            self.export_test_set()

        with open(test_file) as f:
            test_properties = json.load(f)

        addresses = [p['address'] for p in test_properties]

        # Build input based on scraper type
        if scraper_key.startswith('redfin'):
            input_data = self.build_redfin_input(scraper_key, addresses)
        else:
            input_data = self.build_zillow_input(scraper_key, addresses)

        # Run the actor
        start_time = time.time()
        results = self.client.run_actor(actor_id, input_data)
        elapsed = time.time() - start_time

        if not results:
            return {'error': 'Actor run failed', 'elapsed_secs': elapsed}

        # Analyze results
        evaluation = self.analyze_results(scraper_key, results, test_properties)
        evaluation['elapsed_secs'] = elapsed
        evaluation['timestamp'] = datetime.now().isoformat()

        # Save results
        results_file = OUTPUT_DIR / f'{scraper_key}_results.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        eval_file = OUTPUT_DIR / f'{scraper_key}_evaluation.json'
        with open(eval_file, 'w') as f:
            json.dump(evaluation, f, indent=2)

        return evaluation

    def analyze_results(self, scraper_key: str, results: list,
                       test_properties: list) -> dict:
        """Analyze scraper results against our requirements."""

        if not results:
            return {'error': 'No results', 'score': 0}

        evaluation = {
            'scraper': scraper_key,
            'total_results': len(results),
            'fields_present': {},
            'fields_missing': [],
            'match_rate': 0,
            'data_quality': {},
            'issues': [],
        }

        # Check which fields are present
        if results:
            sample = results[0]
            all_keys = set()
            for r in results[:10]:
                all_keys.update(r.keys())

            # Check required fields
            for field in REQUIRED_FIELDS['must_have']:
                # Map our field names to possible scraper field names
                possible_names = self._get_field_variants(field)
                found = any(name in all_keys for name in possible_names)
                evaluation['fields_present'][field] = found
                if not found:
                    evaluation['fields_missing'].append(field)

            # Check nice-to-have fields
            for field in REQUIRED_FIELDS['nice_to_have']:
                possible_names = self._get_field_variants(field)
                found = any(name in all_keys for name in possible_names)
                evaluation['fields_present'][field] = found

        # Calculate match rate against test set
        test_addresses = {p['address'].upper() for p in test_properties}
        result_addresses = set()
        for r in results:
            addr = r.get('address') or r.get('streetAddress') or r.get('formattedAddress', '')
            if addr:
                result_addresses.add(addr.upper())

        matches = test_addresses & result_addresses
        evaluation['match_rate'] = len(matches) / len(test_addresses) if test_addresses else 0

        # Data quality checks
        quality_issues = []
        for r in results:
            # Check beds
            beds = r.get('beds') or r.get('bedrooms')
            if beds and beds > VALIDATION_RULES['beds_max']:
                quality_issues.append(f"High beds count: {beds}")

            # Check price
            price = r.get('price') or r.get('listPrice')
            if price:
                if price < VALIDATION_RULES['price_min']:
                    quality_issues.append(f"Low price: ${price}")
                elif price > VALIDATION_RULES['price_max']:
                    quality_issues.append(f"High price: ${price}")

        evaluation['data_quality']['issues_found'] = len(quality_issues)
        evaluation['data_quality']['issue_samples'] = quality_issues[:5]

        # Calculate overall score
        must_have_score = sum(1 for f in REQUIRED_FIELDS['must_have']
                             if evaluation['fields_present'].get(f, False))
        nice_to_have_score = sum(1 for f in REQUIRED_FIELDS['nice_to_have']
                                 if evaluation['fields_present'].get(f, False))

        evaluation['scores'] = {
            'must_have': f"{must_have_score}/{len(REQUIRED_FIELDS['must_have'])}",
            'nice_to_have': f"{nice_to_have_score}/{len(REQUIRED_FIELDS['nice_to_have'])}",
            'completeness': (must_have_score * 2 + nice_to_have_score) /
                           (len(REQUIRED_FIELDS['must_have']) * 2 + len(REQUIRED_FIELDS['nice_to_have'])),
        }

        return evaluation

    def _get_field_variants(self, field: str) -> List[str]:
        """Get possible field name variants for a standard field."""
        variants = {
            'address': ['address', 'streetAddress', 'formattedAddress', 'street_address'],
            'city': ['city', 'cityName'],
            'state': ['state', 'stateCode'],
            'zip': ['zip', 'zipCode', 'postalCode', 'zipcode'],
            'price': ['price', 'listPrice', 'list_price', 'currentPrice'],
            'status': ['status', 'homeStatus', 'listingStatus', 'propertyStatus'],
            'beds': ['beds', 'bedrooms', 'bedroomCount', 'bedroom_count'],
            'baths': ['baths', 'bathrooms', 'bathroomCount', 'bathroom_count'],
            'sqft': ['sqft', 'livingArea', 'squareFeet', 'square_feet', 'buildingSize'],
            'photo_url': ['photo', 'photos', 'imgSrc', 'primaryPhoto', 'photoUrl'],
            'days_on_market': ['daysOnMarket', 'days_on_market', 'dom', 'timeOnZillow'],
            'views': ['views', 'pageViewCount', 'viewCount'],
            'favorites': ['favorites', 'favoriteCount', 'saves'],
            'listing_agent_name': ['listingAgent', 'agent', 'agentName', 'listing_agent'],
            'listing_agent_phone': ['agentPhone', 'agent_phone', 'brokerPhone'],
            'price_history': ['priceHistory', 'price_history', 'priceChanges'],
            'all_photos': ['photos', 'images', 'photoUrls'],
            'mls_number': ['mlsId', 'mls', 'mlsNumber', 'listingId'],
            'acreage': ['acreage', 'lotSize', 'lot_size', 'lotAreaValue'],
            'year_built': ['yearBuilt', 'year_built', 'builtYear'],
        }
        return variants.get(field, [field])

    def generate_report(self) -> str:
        """Generate comparison report from all evaluations."""

        evaluations = []
        for eval_file in OUTPUT_DIR.glob('*_evaluation.json'):
            with open(eval_file) as f:
                evaluations.append(json.load(f))

        if not evaluations:
            return "No evaluation results found. Run evaluations first."

        report = []
        report.append("# Apify Scraper Evaluation Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append(f"\nEvaluations: {len(evaluations)}\n")

        # Summary table
        report.append("## Summary\n")
        report.append("| Scraper | Results | Must-Have | Nice-to-Have | Time (s) |")
        report.append("|---------|---------|-----------|--------------|----------|")

        for e in sorted(evaluations, key=lambda x: -x.get('scores', {}).get('completeness', 0)):
            scraper = e.get('scraper', 'Unknown')
            results = e.get('total_results', 0)
            must_have = e.get('scores', {}).get('must_have', '?/?')
            nice = e.get('scores', {}).get('nice_to_have', '?/?')
            elapsed = e.get('elapsed_secs', 0)
            report.append(f"| {scraper} | {results} | {must_have} | {nice} | {elapsed:.1f} |")

        # Detailed findings
        report.append("\n## Detailed Findings\n")

        for e in evaluations:
            scraper = e.get('scraper', 'Unknown')
            report.append(f"### {scraper}\n")

            if 'error' in e:
                report.append(f"**Error:** {e['error']}\n")
                continue

            report.append(f"- **Results returned:** {e.get('total_results', 0)}")
            report.append(f"- **Match rate:** {e.get('match_rate', 0)*100:.1f}%")
            report.append(f"- **Execution time:** {e.get('elapsed_secs', 0):.1f}s")

            # Missing fields
            missing = e.get('fields_missing', [])
            if missing:
                report.append(f"- **Missing required fields:** {', '.join(missing)}")
            else:
                report.append("- **All required fields present**")

            # Quality issues
            quality = e.get('data_quality', {})
            if quality.get('issues_found', 0) > 0:
                report.append(f"- **Data quality issues:** {quality['issues_found']}")
                for issue in quality.get('issue_samples', []):
                    report.append(f"  - {issue}")

            report.append("")

        # Recommendation
        report.append("## Recommendation\n")

        best = max(evaluations, key=lambda x: x.get('scores', {}).get('completeness', 0))
        report.append(f"Based on completeness score, **{best.get('scraper')}** is the recommended scraper.\n")

        report_text = '\n'.join(report)

        # Save report
        report_file = OUTPUT_DIR / 'evaluation_report.md'
        with open(report_file, 'w') as f:
            f.write(report_text)

        logger.info(f"Report saved to {report_file}")
        return report_text


def main():
    parser = argparse.ArgumentParser(description='Evaluate Apify scrapers')
    parser.add_argument('--export-test-set', action='store_true',
                       help='Export test properties from database')
    parser.add_argument('--run-redfin', action='store_true',
                       help='Run all Redfin scraper evaluations')
    parser.add_argument('--run-zillow', action='store_true',
                       help='Run all Zillow scraper evaluations')
    parser.add_argument('--run-all', action='store_true',
                       help='Run all scraper evaluations')
    parser.add_argument('--run', type=str,
                       help='Run specific scraper (e.g., redfin_triangle)')
    parser.add_argument('--analyze', action='store_true',
                       help='Generate comparison report')
    parser.add_argument('--db', default=DB_PATH, help='Database path')

    args = parser.parse_args()

    evaluator = ScraperEvaluator(db_path=args.db)

    if args.export_test_set:
        evaluator.export_test_set()
        return

    if args.run:
        result = evaluator.run_evaluation(args.run)
        print(json.dumps(result, indent=2))
        return

    if args.run_redfin or args.run_all:
        for key in ['redfin_triangle', 'redfin_epctex', 'redfin_mantisus']:
            print(f"\n{'='*60}")
            print(f"Evaluating: {key}")
            print('='*60)
            result = evaluator.run_evaluation(key)
            print(json.dumps(result, indent=2))

    if args.run_zillow or args.run_all:
        for key in ['zillow_maxcopell']:  # zillow_detail needs zpids
            print(f"\n{'='*60}")
            print(f"Evaluating: {key}")
            print('='*60)
            result = evaluator.run_evaluation(key)
            print(json.dumps(result, indent=2))

    if args.analyze:
        report = evaluator.generate_report()
        print(report)

    if not any([args.export_test_set, args.run, args.run_redfin,
                args.run_zillow, args.run_all, args.analyze]):
        parser.print_help()
        print("\nQuick start:")
        print("  1. python evaluate_scrapers.py --export-test-set")
        print("  2. export APIFY_TOKEN='your_token_here'")
        print("  3. python evaluate_scrapers.py --run redfin_triangle")
        print("  4. python evaluate_scrapers.py --analyze")


if __name__ == '__main__':
    main()
