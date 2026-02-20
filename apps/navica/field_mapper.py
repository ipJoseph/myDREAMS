"""
Navica RESO Field Mapper

Maps RESO Data Dictionary fields to the myDREAMS listings table schema.
Based on the proven mapping from scripts/import_mlsgrid.py, extended for
Navica-specific fields and BBO data.

RESO Data Dictionary reference: https://ddwiki.reso.org/
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Status mapping: RESO StandardStatus to myDREAMS status
# ---------------------------------------------------------------

RESO_STATUS_MAP = {
    'Active': 'ACTIVE',
    'Active Under Contract': 'PENDING',
    'Pending': 'PENDING',
    'Closed': 'SOLD',
    'Expired': 'EXPIRED',
    'Withdrawn': 'WITHDRAWN',
    'Canceled': 'CANCELLED',
    'Cancelled': 'CANCELLED',
    'Coming Soon': 'COMING_SOON',
    'Hold': 'HOLD',
    'Delete': 'DELETED',
    'Incomplete': 'INCOMPLETE',
}

# ---------------------------------------------------------------
# Property type mapping
# ---------------------------------------------------------------

RESO_PROPERTY_TYPE_MAP = {
    'Residential': 'Residential',
    'Land': 'Land',
    'Farm': 'Farm',
    'Commercial Sale': 'Commercial',
    'Residential Income': 'Multi-Family',
    'Manufactured In Park': 'Manufactured',
    'Business Opportunity': 'Business',
    'Condominium': 'Condo',
}


def map_status(reso_status: str) -> str:
    """Map RESO StandardStatus to myDREAMS status."""
    if not reso_status:
        return 'UNKNOWN'
    return RESO_STATUS_MAP.get(reso_status, reso_status.upper())


def map_property_type(reso_type: str) -> str:
    """Map RESO PropertyType to myDREAMS property_type."""
    if not reso_type:
        return 'Unknown'
    return RESO_PROPERTY_TYPE_MAP.get(reso_type, reso_type)


def parse_date(date_str: str) -> Optional[str]:
    """
    Parse RESO date/datetime string to YYYY-MM-DD format.
    Handles ISO 8601 variants returned by various RESO implementations.
    """
    if not date_str:
        return None

    formats = [
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    # If none of the formats match, try to extract just the date portion
    match = re.match(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        return match.group(1)

    logger.debug(f"Could not parse date: {date_str}")
    return None


def parse_timestamp(ts_str: str) -> Optional[str]:
    """
    Parse RESO timestamp to full ISO 8601 format (preserving time).
    Used for ModificationTimestamp tracking.
    """
    if not ts_str:
        return None

    formats = [
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        except ValueError:
            continue

    return ts_str


def generate_listing_id(mls_number: str, mls_source: str = 'NavicaMLS') -> str:
    """
    Generate a deterministic unique listing ID from MLS number and source.
    Uses MD5 hash prefix for consistency with existing import patterns.
    """
    hash_input = f"{mls_source}:{mls_number}"
    hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    return f"lst_{hash_val}"


def extract_photos(media_list: List[Dict]) -> Tuple[Optional[str], List[str], int]:
    """
    Extract photo URLs from RESO Media array.

    Args:
        media_list: RESO Media objects (from $expand=Media)

    Returns:
        Tuple of (primary_photo_url, all_photo_urls, photo_count)
    """
    if not media_list:
        return None, [], 0

    photos = []
    primary = None

    for media in media_list:
        # Filter to photos only (skip virtual tours, documents, etc.)
        category = media.get('MediaCategory', '')
        if category and category != 'Photo':
            continue

        url = media.get('MediaURL')
        if not url:
            continue

        # Build ordered list
        order = media.get('Order', media.get('MediaOrder', 999))
        photos.append((order, url))

    # Sort by order
    photos.sort(key=lambda x: x[0])
    photo_urls = [url for _, url in photos]

    # Primary is the first photo (order=1 or lowest order)
    if photo_urls:
        primary = photo_urls[0]

    return primary, photo_urls, len(photo_urls)


def extract_virtual_tour(media_list: List[Dict]) -> Optional[str]:
    """Extract virtual tour URL from RESO Media array."""
    if not media_list:
        return None

    for media in media_list:
        category = media.get('MediaCategory', '')
        if category in ('VirtualTour', 'Video'):
            url = media.get('MediaURL')
            if url:
                return url

    return None


def build_address(prop: Dict) -> str:
    """
    Build a clean address string from RESO address components.
    Falls back to UnparsedAddress if components are missing.
    """
    parts = [
        prop.get('StreetNumber', ''),
        prop.get('StreetDirPrefix', ''),
        prop.get('StreetName', ''),
        prop.get('StreetSuffix', ''),
        prop.get('StreetDirSuffix', ''),
    ]
    address = ' '.join(p.strip() for p in parts if p and p.strip())

    # Add unit/apt if present
    unit = prop.get('UnitNumber') or prop.get('UnitDesignation')
    if unit:
        address += f" #{unit}"

    if not address:
        address = prop.get('UnparsedAddress') or ''

    return address.strip()


def json_encode_list(value) -> Optional[str]:
    """Encode a list or comma-separated string as JSON. Returns None if empty."""
    if not value:
        return None
    if isinstance(value, list):
        return json.dumps(value) if value else None
    if isinstance(value, str):
        return json.dumps([v.strip() for v in value.split(',') if v.strip()])
    return None


def map_reso_to_listing(prop: Dict, mls_source: str = 'NavicaMLS') -> Dict[str, Any]:
    """
    Map a RESO property record to the myDREAMS listings table schema.

    This is the core field mapper. It handles all RESO Data Dictionary fields
    and produces a flat dict ready for database upsert.

    Args:
        prop: Raw RESO property record from the API
        mls_source: MLS source identifier (e.g., 'NavicaMLS', 'CanopyMLS')

    Returns:
        Dict matching the listings table columns
    """
    # Extract media
    media = prop.get('Media', [])
    primary_photo, all_photos, photo_count = extract_photos(media)
    virtual_tour = extract_virtual_tour(media)

    # Build address
    address = build_address(prop)

    # Calculate total baths
    # Navica provides BathroomsTotalDecimal directly; fall back to computing from parts
    total_baths = prop.get('BathroomsTotalDecimal')
    if total_baths is None:
        full_baths = prop.get('BathroomsFull', 0) or 0
        half_baths = prop.get('BathroomsHalf', 0) or 0
        if full_baths or half_baths:
            total_baths = full_baths + half_baths * 0.5

    # Determine MLS number
    mls_number = prop.get('ListingId') or prop.get('ListingKey')

    now = datetime.now().isoformat()

    listing = {
        # Identifiers
        'id': generate_listing_id(mls_number, mls_source),
        'mls_number': mls_number,
        'mls_source': mls_source,
        'listing_key': prop.get('ListingKey'),

        # Status and dates
        'status': map_status(prop.get('StandardStatus')),
        'list_date': parse_date(
            prop.get('ListingContractDate')
            or prop.get('OnMarketDate')
            or prop.get('OriginalEntryTimestamp')
        ),
        'sold_date': parse_date(prop.get('CloseDate')),
        'days_on_market': prop.get('DaysOnMarket'),
        'expiration_date': parse_date(prop.get('ExpirationDate')),

        # Pricing
        'list_price': prop.get('ListPrice'),
        'original_list_price': prop.get('OriginalListPrice'),
        'sold_price': prop.get('ClosePrice'),

        # Location
        'address': address,
        'city': prop.get('City'),
        'state': prop.get('StateOrProvince', 'NC'),
        'zip': prop.get('PostalCode'),
        'county': prop.get('CountyOrParish'),
        'latitude': prop.get('Latitude'),
        'longitude': prop.get('Longitude'),
        'subdivision': prop.get('SubdivisionName'),
        'directions': prop.get('Directions'),

        # Property details
        'property_type': map_property_type(prop.get('PropertyType')),
        'property_subtype': prop.get('PropertySubType'),
        'beds': prop.get('BedroomsTotal'),
        'baths': total_baths,
        'sqft': prop.get('LivingArea'),
        'acreage': prop.get('LotSizeAcres'),
        'lot_sqft': prop.get('LotSizeSquareFeet'),
        'year_built': prop.get('YearBuilt'),
        'stories': None,  # Not available in Navica API
        'garage_spaces': prop.get('GarageSpaces'),
        'is_residential': 1 if prop.get('PropertyType') in ('Residential', 'Condominium') else 0,

        # Features (stored as JSON arrays)
        'heating': json_encode_list(prop.get('Heating')),
        'cooling': json_encode_list(prop.get('Cooling')),
        'appliances': json_encode_list(prop.get('Appliances')),
        'interior_features': json_encode_list(prop.get('InteriorFeatures')),
        'exterior_features': json_encode_list(prop.get('ExteriorFeatures')),
        'amenities': json_encode_list(prop.get('AssociationAmenities')),
        'views': json_encode_list(prop.get('View')),
        'style': json_encode_list(prop.get('ArchitecturalStyle')),
        'roof': json_encode_list(prop.get('Roof')),
        'sewer': json_encode_list(prop.get('Sewer')),
        'water_source': json_encode_list(prop.get('WaterSource')),
        'construction_materials': json_encode_list(prop.get('ConstructionMaterials')),
        'foundation': json_encode_list(prop.get('FoundationDetails')),
        'flooring': json_encode_list(prop.get('Flooring')),
        'fireplace_features': json_encode_list(prop.get('FireplaceFeatures')),
        'parking_features': json_encode_list(prop.get('ParkingFeatures')),

        # Financial
        'hoa_fee': prop.get('AssociationFee'),
        'hoa_frequency': prop.get('AssociationFeeFrequency'),
        'tax_annual_amount': prop.get('TaxAnnualAmount'),
        'tax_assessed_value': prop.get('TaxAssessedValue'),
        'tax_year': prop.get('TaxYear'),

        # Agent info
        'listing_agent_id': prop.get('ListAgentMlsId') or prop.get('ListAgentKey'),
        'listing_agent_name': prop.get('ListAgentFullName'),
        'listing_agent_phone': prop.get('ListAgentPreferredPhone') or prop.get('ListAgentHomePhone'),
        'listing_agent_email': prop.get('ListAgentEmail'),
        'listing_office_id': prop.get('ListOfficeMlsId') or prop.get('ListOfficeKey'),
        'listing_office_name': prop.get('ListOfficeName'),

        # Buyer agent info (available for closed listings in BBO feed)
        'buyer_agent_id': prop.get('BuyerAgentMlsId'),
        'buyer_agent_name': prop.get('BuyerAgentFullName'),
        'buyer_office_id': prop.get('BuyerOfficeMlsId') or prop.get('BuyerOfficeKey'),
        'buyer_office_name': prop.get('BuyerOfficeName'),

        # Photos
        'primary_photo': primary_photo,
        'photos': json.dumps(all_photos) if all_photos else None,
        'photo_count': photo_count,
        'photo_source': 'navica' if all_photos else None,
        'photo_verified_at': now if all_photos else None,
        'photo_review_status': 'verified' if all_photos else None,

        # Virtual tour
        'virtual_tour_url': virtual_tour,

        # Parcel
        'parcel_number': prop.get('ParcelNumber'),

        # Descriptions
        'public_remarks': prop.get('PublicRemarks'),
        'private_remarks': prop.get('PrivateRemarks'),  # BBO only
        'showing_instructions': prop.get('ShowingInstructions'),  # BBO only

        # IDX display rules
        'idx_opt_in': prop.get('InternetEntireListingDisplayYN', True),
        'idx_address_display': prop.get('InternetAddressDisplayYN', True),
        'vow_opt_in': prop.get('VirtualTourURLUnbranded'),

        # Sync metadata
        'source': 'navica',
        'modification_timestamp': prop.get('ModificationTimestamp'),
        'captured_at': now,
        'updated_at': now,
    }

    return listing


def map_reso_to_member(member: Dict) -> Dict[str, Any]:
    """
    Map a RESO Member record to a member/agent dict.

    Args:
        member: Raw RESO Member record

    Returns:
        Dict for agent storage
    """
    return {
        'member_key': member.get('MemberKey'),
        'member_mls_id': member.get('MemberMlsId'),
        'first_name': member.get('MemberFirstName'),
        'last_name': member.get('MemberLastName'),
        'full_name': member.get('MemberFullName'),
        'email': member.get('MemberEmail'),
        'phone': member.get('MemberPreferredPhone') or member.get('MemberMobilePhone'),
        'mobile_phone': member.get('MemberMobilePhone'),
        'office_key': member.get('OfficeKey'),
        'office_name': member.get('OfficeName'),
        'member_type': member.get('MemberType'),
        'member_status': member.get('MemberStatus'),
        'modification_timestamp': member.get('ModificationTimestamp'),
    }


def map_reso_to_office(office: Dict) -> Dict[str, Any]:
    """
    Map a RESO Office record.

    Args:
        office: Raw RESO Office record

    Returns:
        Dict for office storage
    """
    return {
        'office_key': office.get('OfficeKey'),
        'office_mls_id': office.get('OfficeMlsId'),
        'office_name': office.get('OfficeName'),
        'office_phone': office.get('OfficePhone'),
        'office_email': office.get('OfficeEmail'),
        'office_address': office.get('OfficeAddress1'),
        'office_city': office.get('OfficeCity'),
        'office_state': office.get('OfficeStateOrProvince'),
        'office_zip': office.get('OfficePostalCode'),
        'broker_key': office.get('OfficeBrokerKey'),
        'broker_name': office.get('OfficeBrokerMlsId'),
        'modification_timestamp': office.get('ModificationTimestamp'),
    }


def map_reso_to_open_house(oh: Dict) -> Dict[str, Any]:
    """
    Map a RESO OpenHouse record.

    Args:
        oh: Raw RESO OpenHouse record

    Returns:
        Dict for open house storage
    """
    return {
        'open_house_key': oh.get('OpenHouseKey'),
        'listing_key': oh.get('ListingKey'),
        'listing_id': oh.get('ListingId'),
        'date': parse_date(oh.get('OpenHouseDate')),
        'start_time': oh.get('OpenHouseStartTime'),
        'end_time': oh.get('OpenHouseEndTime'),
        'type': oh.get('OpenHouseType'),
        'remarks': oh.get('OpenHouseRemarks'),
        'status': oh.get('OpenHouseStatus'),
        'modification_timestamp': oh.get('ModificationTimestamp'),
    }
