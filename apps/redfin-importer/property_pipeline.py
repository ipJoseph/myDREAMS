#!/usr/bin/env python3
"""
Property Pipeline Orchestrator

Unified pipeline for property data acquisition and enrichment:
1. Download CSV from Redfin (using saved login cookies)
2. Import properties to database
3. Scrape page data (photos, views, favorites, agent info)
4. Enrich with NC OneMap parcel data (APN, owner, values)

Usage:
    python property_pipeline.py --county Macon                    # Full pipeline for county
    python property_pipeline.py --county Macon --skip-scrape      # Skip page scraping
    python property_pipeline.py --county Macon --scrape-only      # Only scrape existing URLs
    python property_pipeline.py --county Macon --enrich-only      # Only enrich with OneMap
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.getenv('REDFIN_DB_PATH', str(PROJECT_ROOT / 'data' / 'redfin_imports.db'))


class PropertyPipeline:
    """Orchestrates the full property data pipeline."""

    def __init__(self, db_path: str = DB_PATH, headless: bool = True):
        self.db_path = db_path
        self.headless = headless
        self.stats = {
            'download_time': 0,
            'import_time': 0,
            'scrape_time': 0,
            'enrich_time': 0,
            'properties_downloaded': 0,
            'properties_imported': 0,
            'properties_scraped': 0,
            'properties_enriched': 0,
        }

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def run_download(self, counties: List[str]) -> List[str]:
        """Download CSVs from Redfin for specified counties."""
        from redfin_auto_download import RedfinAutoDownloader

        logger.info(f"=== STEP 1: DOWNLOAD FROM REDFIN ===")
        logger.info(f"Counties: {', '.join(counties)}")

        start = time.time()
        csv_files = []

        async with RedfinAutoDownloader(headless=self.headless) as downloader:
            for county in counties:
                try:
                    csv_path = await downloader.download_county(county.lower())
                    if csv_path:
                        csv_files.append(csv_path)
                        self.stats['properties_downloaded'] += 1
                        logger.info(f"Downloaded: {csv_path}")
                except Exception as e:
                    logger.error(f"Error downloading {county}: {e}")

        self.stats['download_time'] = time.time() - start
        return csv_files

    def run_import(self, csv_files: List[str]) -> Dict:
        """Import CSVs to database."""
        from redfin_csv_importer import RedfinCSVImporter

        logger.info(f"=== STEP 2: IMPORT TO DATABASE ===")
        logger.info(f"Files: {len(csv_files)}")

        start = time.time()

        importer = RedfinCSVImporter(db_path=self.db_path)
        stats = importer.import_multiple(csv_files)

        self.stats['import_time'] = time.time() - start
        self.stats['properties_imported'] = stats['rows_imported']

        logger.info(f"Imported: {stats['rows_imported']} properties")
        return stats

    async def run_scrape(self, limit: int = None, county: str = None) -> Dict:
        """Scrape Redfin pages for additional data."""
        from redfin_page_scraper import RedfinPageScraper

        logger.info(f"=== STEP 3: SCRAPE PAGE DATA ===")

        start = time.time()

        # Get pending URLs from scrape queue
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build query
        sql = '''
            SELECT sq.id, sq.property_id, sq.url, p.county
            FROM redfin_scrape_queue sq
            JOIN properties p ON sq.property_id = p.id
            WHERE sq.status = 'pending'
        '''
        params = []

        if county:
            sql += ' AND LOWER(p.county) = LOWER(?)'
            params.append(county)

        sql += ' ORDER BY sq.created_at'

        if limit:
            sql += f' LIMIT {limit}'

        cursor.execute(sql, params)
        pending_count = len(cursor.fetchall())
        conn.close()

        logger.info(f"Pending URLs to scrape: {pending_count}")

        if pending_count == 0:
            logger.info("No URLs to scrape")
            return {'scraped': 0}

        async with RedfinPageScraper(db_path=self.db_path, headless=self.headless) as scraper:
            stats = await scraper.process_queue(limit=limit)

        self.stats['scrape_time'] = time.time() - start
        self.stats['properties_scraped'] = stats['scraped']

        logger.info(f"Scraped: {stats['scraped']} pages")
        return stats

    def run_enrich(self, county: str = None, limit: int = None) -> Dict:
        """Enrich properties with NC OneMap data."""
        from nc_onemap_enricher import NCOneMapEnricher

        logger.info(f"=== STEP 4: ENRICH WITH NC ONEMAP ===")

        start = time.time()

        enricher = NCOneMapEnricher(db_path=self.db_path)
        stats = enricher.enrich_all(county=county, limit=limit)

        self.stats['enrich_time'] = time.time() - start
        self.stats['properties_enriched'] = stats['enriched']

        logger.info(f"Enriched: {stats['enriched']} properties")
        return stats

    async def run_full_pipeline(
        self,
        counties: List[str],
        skip_download: bool = False,
        skip_scrape: bool = False,
        skip_enrich: bool = False,
        scrape_limit: int = None,
        enrich_limit: int = None,
        csv_files: List[str] = None,
    ) -> Dict:
        """Run the full pipeline."""
        logger.info("=" * 60)
        logger.info("PROPERTY PIPELINE - STARTING")
        logger.info("=" * 60)
        logger.info(f"Counties: {', '.join(counties)}")
        logger.info(f"Database: {self.db_path}")
        logger.info("")

        pipeline_start = time.time()

        # Step 1: Download
        if not skip_download and not csv_files:
            csv_files = await self.run_download(counties)
            if not csv_files:
                logger.warning("No CSV files downloaded")
        elif csv_files:
            logger.info(f"Using provided CSV files: {csv_files}")

        # Step 2: Import
        if csv_files:
            self.run_import(csv_files)

        # Step 3: Scrape (optional)
        if not skip_scrape:
            # Scrape for each county
            for county in counties:
                await self.run_scrape(limit=scrape_limit, county=county)

        # Step 4: Enrich
        if not skip_enrich:
            for county in counties:
                self.run_enrich(county=county, limit=enrich_limit)

        total_time = time.time() - pipeline_start

        # Summary
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Total Time:          {total_time:.1f}s")
        print(f"")
        print(f"Download Time:       {self.stats['download_time']:.1f}s")
        print(f"Import Time:         {self.stats['import_time']:.1f}s")
        print(f"Scrape Time:         {self.stats['scrape_time']:.1f}s")
        print(f"Enrich Time:         {self.stats['enrich_time']:.1f}s")
        print(f"")
        print(f"Properties Imported: {self.stats['properties_imported']}")
        print(f"Properties Scraped:  {self.stats['properties_scraped']}")
        print(f"Properties Enriched: {self.stats['properties_enriched']}")
        print("=" * 60)

        return self.stats

    def get_property_summary(self, county: str = None) -> Dict:
        """Get summary of properties in database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Base counts
        sql = 'SELECT COUNT(*) as total FROM properties'
        params = []
        if county:
            sql += ' WHERE LOWER(county) = LOWER(?)'
            params.append(county)

        cursor.execute(sql, params)
        total = cursor.fetchone()['total']

        # With parcel data
        sql = '''
            SELECT COUNT(*) as count FROM properties
            WHERE parcel_id IS NOT NULL AND parcel_id != ''
        '''
        if county:
            sql += ' AND LOWER(county) = LOWER(?)'
        cursor.execute(sql, params)
        with_parcel = cursor.fetchone()['count']

        # With photo
        sql = '''
            SELECT COUNT(*) as count FROM properties
            WHERE primary_photo IS NOT NULL AND primary_photo != ''
        '''
        if county:
            sql += ' AND LOWER(county) = LOWER(?)'
        cursor.execute(sql, params)
        with_photo = cursor.fetchone()['count']

        # With agent info
        sql = '''
            SELECT COUNT(*) as count FROM properties
            WHERE listing_agent_name IS NOT NULL AND listing_agent_name != ''
        '''
        if county:
            sql += ' AND LOWER(county) = LOWER(?)'
        cursor.execute(sql, params)
        with_agent = cursor.fetchone()['count']

        conn.close()

        return {
            'total': total,
            'with_parcel': with_parcel,
            'with_photo': with_photo,
            'with_agent': with_agent,
        }


async def main():
    parser = argparse.ArgumentParser(description='Property data pipeline orchestrator')
    parser.add_argument('--county', nargs='+', required=True, help='County or counties to process')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('--headed', action='store_true', help='Run browser in visible mode')

    # Pipeline control
    parser.add_argument('--skip-download', action='store_true', help='Skip Redfin download')
    parser.add_argument('--skip-scrape', action='store_true', help='Skip page scraping')
    parser.add_argument('--skip-enrich', action='store_true', help='Skip NC OneMap enrichment')

    # Standalone modes
    parser.add_argument('--scrape-only', action='store_true', help='Only run page scraping')
    parser.add_argument('--enrich-only', action='store_true', help='Only run NC OneMap enrichment')

    # Limits
    parser.add_argument('--scrape-limit', type=int, help='Max pages to scrape')
    parser.add_argument('--enrich-limit', type=int, help='Max properties to enrich')

    # CSV import
    parser.add_argument('--csv', nargs='+', help='Import specific CSV files')

    # Info
    parser.add_argument('--summary', action='store_true', help='Show database summary')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    pipeline = PropertyPipeline(db_path=args.db, headless=not args.headed)

    # Summary mode
    if args.summary:
        for county in args.county:
            summary = pipeline.get_property_summary(county)
            print(f"\n{county.title()} County Summary:")
            print(f"  Total Properties:     {summary['total']}")
            print(f"  With Parcel/APN:      {summary['with_parcel']}")
            print(f"  With Photo:           {summary['with_photo']}")
            print(f"  With Agent Info:      {summary['with_agent']}")
        return

    # Standalone scrape mode
    if args.scrape_only:
        for county in args.county:
            await pipeline.run_scrape(limit=args.scrape_limit, county=county)
        return

    # Standalone enrich mode
    if args.enrich_only:
        for county in args.county:
            pipeline.run_enrich(county=county, limit=args.enrich_limit)
        return

    # Full pipeline
    await pipeline.run_full_pipeline(
        counties=args.county,
        skip_download=args.skip_download,
        skip_scrape=args.skip_scrape,
        skip_enrich=args.skip_enrich,
        scrape_limit=args.scrape_limit,
        enrich_limit=args.enrich_limit,
        csv_files=args.csv,
    )


if __name__ == '__main__':
    asyncio.run(main())
