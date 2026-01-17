"""
Notion Sync Service

Background service that syncs properties from SQLite to Notion.
"""

import threading
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Use Eastern timezone for all timestamps
EASTERN_TZ = ZoneInfo('America/New_York')


class NotionSyncService:
    """
    Syncs properties from SQLite to Notion database.
    Runs as a background thread.
    """

    def __init__(self, notion_api_key: str, database_id: str, db):
        """
        Initialize the sync service.

        Args:
            notion_api_key: Notion integration token
            database_id: Target Notion database ID
            db: DREAMSDatabase instance
        """
        from notion_client import Client

        self.notion = Client(auth=notion_api_key)
        self.database_id = database_id.replace('-', '')
        self.db = db
        self._sync_thread = None
        self._stop_event = threading.Event()

    def start_background_sync(self, interval_seconds: int = 60):
        """Start background sync thread."""
        def sync_loop():
            while not self._stop_event.is_set():
                try:
                    count = self.sync_pending_properties()
                    if count > 0:
                        logger.info(f"Synced {count} properties to Notion")
                except Exception as e:
                    logger.error(f"Notion sync error: {e}")

                # Wait for interval or stop signal
                self._stop_event.wait(interval_seconds)

        self._sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info(f"Notion sync service started (interval: {interval_seconds}s)")

    def stop(self):
        """Stop the background sync thread."""
        self._stop_event.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)

    def sync_pending_properties(self) -> int:
        """
        Sync all pending properties to Notion.

        Returns:
            Number of properties synced
        """
        pending = self.db.get_properties_by_sync_status('pending')
        synced_count = 0

        for prop in pending:
            try:
                # First, check if we already have a notion_page_id stored (from previous sync)
                existing_page_id = prop.get('notion_page_id')

                # If not stored, search Notion by MLS# or address
                if not existing_page_id:
                    existing_page_id = self._find_existing_page(prop)

                if existing_page_id:
                    self._update_notion_page(existing_page_id, prop)
                    notion_page_id = existing_page_id
                    logger.info(f"Updated existing Notion page {notion_page_id} for {prop.get('address')}")
                else:
                    notion_page_id = self._create_notion_page(prop)
                    logger.info(f"Created new Notion page {notion_page_id} for {prop.get('address')}")

                # Mark as synced
                self.db.update_property_sync_status(
                    prop['id'],
                    status='synced',
                    notion_page_id=notion_page_id
                )
                synced_count += 1

            except Exception as e:
                logger.error(f"Failed to sync property {prop['id']}: {e}")
                self.db.update_property_sync_status(
                    prop['id'],
                    status='failed',
                    error=str(e)
                )

        return synced_count

    def _find_existing_page(self, prop: Dict[str, Any]) -> Optional[str]:
        """Find existing Notion page by MLS# or address (excluding trashed pages)."""
        mls_number = prop.get('mls_number')
        address = prop.get('address')

        # First try MLS number (most reliable)
        if mls_number:
            try:
                response = self.notion.databases.query(
                    database_id=self.database_id,
                    filter={
                        'property': 'MLS #',
                        'rich_text': {'equals': str(mls_number)}
                    }
                )
                # Skip archived/trashed pages
                for page in response['results']:
                    if not page.get('archived', False) and not page.get('in_trash', False):
                        return page['id']
            except Exception:
                pass

        # Fallback: search by address (title field)
        if address:
            try:
                response = self.notion.databases.query(
                    database_id=self.database_id,
                    filter={
                        'property': 'Address',
                        'title': {'equals': address}
                    }
                )
                # Skip archived/trashed pages
                for page in response['results']:
                    if not page.get('archived', False) and not page.get('in_trash', False):
                        return page['id']
            except Exception:
                pass

        return None

    def _create_notion_page(self, prop: Dict[str, Any]) -> str:
        """Create a new Notion page for the property."""
        properties = self._build_notion_properties(prop, is_new=True)

        # Try to create, handle missing property errors
        try:
            response = self.notion.pages.create(
                parent={'database_id': self.database_id},
                properties=properties
            )
            return response['id']
        except Exception as e:
            error_msg = str(e)
            # If error mentions missing properties, retry without them
            if 'is not a property that exists' in error_msg:
                logger.warning(f"Retrying with reduced properties: {error_msg}")
                properties = self._build_notion_properties_safe(prop, is_new=True)
                response = self.notion.pages.create(
                    parent={'database_id': self.database_id},
                    properties=properties
                )
                return response['id']
            raise

    def _update_notion_page(self, page_id: str, prop: Dict[str, Any]):
        """Update an existing Notion page."""
        properties = self._build_notion_properties(prop, is_new=False)

        try:
            self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )
        except Exception as e:
            error_msg = str(e)
            if 'is not a property that exists' in error_msg:
                logger.warning(f"Retrying update with reduced properties: {error_msg}")
                properties = self._build_notion_properties_safe(prop, is_new=False)
                self.notion.pages.update(
                    page_id=page_id,
                    properties=properties
                )

    def _build_notion_properties(self, prop: Dict[str, Any], is_new: bool = True) -> Dict[str, Any]:
        """Convert property dict to Notion properties format."""
        properties = {}

        # Title (required)
        if prop.get('address'):
            properties['Address'] = {
                'title': [{'text': {'content': prop['address']}}]
            }

        # Numbers
        number_fields = [
            ('price', 'Price'),
            ('beds', 'Bedrooms'),
            ('baths', 'Bathrooms'),
            ('sqft', 'Sqft'),
            ('acreage', 'Acreage'),
            ('year_built', 'Year Built'),
            ('days_on_market', 'DOM'),
            ('hoa_fee', 'HOA Fee'),
            ('tax_assessed_value', 'Tax Assessed'),
            ('tax_annual_amount', 'Annual Tax'),
            ('zestimate', 'Zestimate'),
            ('rent_zestimate', 'Rent Zestimate'),
            ('page_views', 'Page Views'),
            ('favorites_count', 'Favorites'),
            ('stories', 'Stories'),
            ('latitude', 'Latitude'),
            ('longitude', 'Longitude'),
            ('school_elementary_rating', 'Elementary Rating'),
            ('school_middle_rating', 'Middle Rating'),
            ('school_high_rating', 'High Rating'),
        ]

        for db_field, notion_field in number_fields:
            value = prop.get(db_field)
            if value is not None:
                properties[notion_field] = {'number': value}

        # Rich text fields
        text_fields = [
            ('mls_number', 'MLS #'),
            ('mls_source', 'MLS Source'),
            ('parcel_id', 'Parcel ID'),
            ('zip', 'Zip'),
            ('county', 'County'),
            ('listing_agent_name', 'Agent Name'),
            ('listing_agent_phone', 'Agent Phone'),
            ('listing_brokerage', 'Brokerage'),
            ('heating', 'Heating'),
            ('cooling', 'Cooling'),
            ('garage', 'Garage'),
            ('sewer', 'Sewer'),
            ('roof', 'Roof'),
            ('subdivision', 'Subdivision'),
            ('added_for', 'Added For'),
            ('notes', 'Notes'),
            ('idx_mls_number', 'IDX MLS #'),
            ('original_mls_number', 'Original MLS #'),
            ('idx_mls_source', 'IDX MLS Source'),
        ]

        # City is a Select field in Notion
        if prop.get('city'):
            properties['City'] = {
                'select': {'name': prop['city']}
            }

        for db_field, notion_field in text_fields:
            value = prop.get(db_field)
            if value:
                properties[notion_field] = {
                    'rich_text': [{'text': {'content': str(value)}}]
                }

        # Email field
        if prop.get('listing_agent_email'):
            properties['Agent Email'] = {'email': prop['listing_agent_email']}

        # Select fields
        if prop.get('status'):
            status_map = {
                'active': 'Active',
                'pending': 'Pending',
                'sold': 'Sold',
                'for_sale': 'Active'
            }
            properties['Status'] = {
                'select': {'name': status_map.get(prop['status'].lower(), prop['status'])}
            }

        if prop.get('property_type'):
            properties['Property Type'] = {
                'select': {'name': prop['property_type']}
            }

        if prop.get('added_by'):
            properties['Added By'] = {
                'select': {'name': prop['added_by']}
            }

        if prop.get('source'):
            source_map = {
                'redfin': 'Redfin',
                'zillow': 'Zillow',
                'realtor': 'Realtor.com'
            }
            properties['Source'] = {
                'select': {'name': source_map.get(prop['source'].lower(), prop['source'].title())}
            }

        if prop.get('idx_validation_status'):
            idx_status_map = {
                'pending': 'Pending',
                'validated': 'Validated',
                'not_found': 'Not Found',
                'error': 'Error'
            }
            properties['IDX Status'] = {
                'select': {'name': idx_status_map.get(prop['idx_validation_status'].lower(), prop['idx_validation_status'].title())}
            }

        # Main URL field - the URL where property was captured from
        # Get URL based on source, with fallbacks
        source = (prop.get('source') or '').lower()
        if source == 'redfin':
            listing_url = prop.get('redfin_url')
        elif source == 'zillow':
            listing_url = prop.get('zillow_url')
        elif source == 'realtor':
            listing_url = prop.get('realtor_url')
        else:
            listing_url = prop.get('redfin_url') or prop.get('zillow_url') or prop.get('realtor_url')

        if listing_url:
            properties['URL'] = {'url': listing_url}

        # URL fields - separate fields for each source to support multi-source monitoring
        if prop.get('zillow_url'):
            properties['Zillow URL'] = {'url': prop['zillow_url']}
        if prop.get('redfin_url'):
            properties['Redfin URL'] = {'url': prop['redfin_url']}
        if prop.get('realtor_url'):
            properties['Realtor URL'] = {'url': prop['realtor_url']}

        # Primary photo - stored as external file in Notion
        if prop.get('primary_photo'):
            properties['Photos'] = {
                'files': [{
                    'type': 'external',
                    'name': 'Primary Photo',
                    'external': {'url': prop['primary_photo']}
                }]
            }

        # Checkbox
        properties['Monitoring Active'] = {'checkbox': True}

        # Date fields with time (ISO 8601 format with Eastern timezone)
        now_eastern = datetime.now(EASTERN_TZ)
        now_iso = now_eastern.strftime('%Y-%m-%dT%H:%M:%S%z')

        properties['Last Updated'] = {
            'date': {'start': now_iso}
        }

        # Only set Date Saved on new records
        if is_new:
            properties['Date Saved'] = {
                'date': {'start': now_iso}
            }

        return properties

    def _build_notion_properties_safe(self, prop: Dict[str, Any], is_new: bool = True) -> Dict[str, Any]:
        """
        Build Notion properties excluding fields that may not exist in the database.
        Used as fallback when _build_notion_properties fails.
        """
        # Fields that commonly don't exist in Notion databases
        excluded_fields = {'Zip', 'Garage', 'Property Type', 'Heating', 'Cooling', 'Sewer', 'Roof', 'Brokerage',
                          'Zillow URL', 'Redfin URL', 'Realtor URL'}

        properties = self._build_notion_properties(prop, is_new)

        # Remove excluded fields
        for field in excluded_fields:
            properties.pop(field, None)

        return properties
