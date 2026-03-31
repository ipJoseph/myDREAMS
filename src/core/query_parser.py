"""
Natural Language Query Parser for Real Estate Search

Parses user input like "3 bed cabin under 400k in Sylva" into structured
ListingFilters parameters. Deterministic regex-based (no LLM) for speed
and reliability.

Usage:
    from src.core.query_parser import QueryParser

    parser = QueryParser(cities=['Sylva', ...], counties=['Jackson', ...])
    result = parser.parse("3 bed cabin under 400k in Sylva")
    # result.filters = {'min_beds': 3, 'max_price': 400000, 'city': 'Sylva', 'property_type': 'Residential'}
    # result.interpretations = ['3+ bedrooms', 'Under $400,000', 'Sylva', 'Residential']
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParsedQuery:
    """Result of parsing a natural language search query."""
    filters: Dict[str, Any] = field(default_factory=dict)
    remainder: str = ''
    interpretations: List[str] = field(default_factory=list)
    is_mls_lookup: bool = False
    is_address_lookup: bool = False


# Property type keyword mapping
PROPERTY_TYPE_KEYWORDS = {
    'Residential': [
        'home', 'homes', 'house', 'houses', 'residential', 'cabin', 'cabins',
        'cottage', 'cottages', 'bungalow', 'chalet', 'townhouse', 'townhome',
        'condo', 'condominium',
    ],
    'Land': [
        'land', 'lot', 'lots', 'parcel', 'parcels', 'acreage',
    ],
    'Farm': [
        'farm', 'farms', 'ranch', 'farmhouse', 'farmland',
    ],
    'Commercial': [
        'commercial', 'office', 'retail', 'warehouse', 'industrial',
    ],
    'Multi-Family': [
        'multi-family', 'multifamily', 'duplex', 'triplex', 'fourplex',
        'quadplex', 'apartment',
    ],
}

# Build reverse lookup: keyword -> property type
_KEYWORD_TO_TYPE = {}
for ptype, keywords in PROPERTY_TYPE_KEYWORDS.items():
    for kw in keywords:
        _KEYWORD_TO_TYPE[kw] = ptype

# View-related keywords
VIEW_KEYWORDS = [
    'mountain view', 'mountain views', 'long range view', 'long range views',
    'year round view', 'winter view', 'view', 'views',
    'waterfront', 'lakefront', 'lake view', 'lake views',
    'river view', 'creek', 'pond',
]

# Feature keywords (passed as remainder for LIKE search on public_remarks)
FEATURE_KEYWORDS = [
    'garage', 'pool', 'fireplace', 'basement', 'workshop',
    'barn', 'fenced', 'gated', 'private', 'mountain view', 'mountain views',
    'waterfront', 'lakefront', 'creek', 'river', 'pond', 'lake',
    'hot tub', 'deck', 'porch', 'wrap around porch',
    'hardwood', 'granite', 'stainless', 'updated', 'renovated', 'new construction',
]

# Price pattern: $400k, 400k, $400,000, 400000, $1.5m, 1.5m
_PRICE_RE = re.compile(
    r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([km])?',
    re.IGNORECASE
)

# Address pattern: number + street name + suffix
_ADDRESS_SUFFIXES = (
    'street|st|road|rd|drive|dr|lane|ln|way|court|ct|circle|cir|trail|trl|'
    'ave|avenue|blvd|boulevard|place|pl|loop|terrace|ter|path|pike|hollow|'
    'ridge|run|creek|mountain|gap|cove'
)
_ADDRESS_RE = re.compile(
    rf'\b(\d+\s+[\w\s]+?\s+(?:{_ADDRESS_SUFFIXES}))\b',
    re.IGNORECASE
)

# MLS number pattern: 5-8 digits, optionally prefixed with CAR/NCM
_MLS_RE = re.compile(r'^(?:CAR|NCM)?(\d{5,8})$', re.IGNORECASE)

# Bed/bath patterns
_BEDS_RE = re.compile(r'(\d+)\s*(?:\+\s*)?(?:bed(?:room)?s?|br|bd)\b', re.IGNORECASE)
_BATHS_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:bath(?:room)?s?|ba)\b', re.IGNORECASE)

# Acreage patterns
_ACREAGE_RE = re.compile(
    r'(?:(?:over|above|more than|at least|min(?:imum)?)\s+)?'
    r'(\d+(?:\.\d+)?)\s*\+?\s*(?:acre|acres|ac)\b',
    re.IGNORECASE
)

# Elevation patterns
_ELEVATION_RE = re.compile(
    r'(?:(?:over|above|more than|at least|min)\s+)?'
    r'(\d{3,5})\s*(?:ft|feet|foot|elevation)\b',
    re.IGNORECASE
)
_ELEVATION_ABOVE_RE = re.compile(
    r'(?:above|over|higher than)\s+(\d{3,5})\s*(?:ft|feet|foot|elevation)?\b',
    re.IGNORECASE
)
_ELEVATION_BELOW_RE = re.compile(
    r'(?:below|under|lower than)\s+(\d{3,5})\s*(?:ft|feet|foot|elevation)?\b',
    re.IGNORECASE
)

# Price range: "200k-400k", "200k to 400k", "$200,000-$400,000"
_PRICE_RANGE_RE = re.compile(
    r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([km])?\s*'
    r'(?:-|to)\s*'
    r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([km])?',
    re.IGNORECASE
)

# Price with modifier: "under 400k", "above $300,000"
_PRICE_BELOW_RE = re.compile(
    r'(?:under|below|less than|up to|max|maximum|<)\s*'
    r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([km])?',
    re.IGNORECASE
)
_PRICE_ABOVE_RE = re.compile(
    r'(?:over|above|more than|at least|min|minimum|starting|>)\s*'
    r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([km])?',
    re.IGNORECASE
)

# Sqft patterns
_SQFT_RE = re.compile(
    r'(?:(?:over|above|more than|at least|min)\s+)?'
    r'(\d{3,5})\s*(?:sq\s*ft|sqft|square\s*feet|sf)\b',
    re.IGNORECASE
)

# View score pattern
_VIEW_SCORE_RE = re.compile(
    r'view\s*(?:score|rating|potential)\s*(?:of\s+)?(\d)',
    re.IGNORECASE
)


def _parse_price(amount_str: str, suffix: str = '') -> Optional[int]:
    """Convert a price string like '400' with suffix 'k' to integer 400000."""
    try:
        amount = float(amount_str.replace(',', ''))
        if suffix and suffix.lower() == 'k':
            amount *= 1000
        elif suffix and suffix.lower() == 'm':
            amount *= 1_000_000
        elif amount < 1000:
            # Bare number under 1000, likely shorthand for thousands
            amount *= 1000
        return int(amount)
    except (ValueError, TypeError):
        return None


class QueryParser:
    """Parse natural language real estate search queries.

    Requires city and county lists from the database to match location names.
    Load once at service startup and reuse.
    """

    def __init__(self, cities: List[str] = None, counties: List[str] = None):
        self.cities = sorted(cities or [], key=lambda c: -len(c))  # longest first
        self.counties = sorted(counties or [], key=lambda c: -len(c))
        # Build lowercase lookup sets
        self._city_set = {c.lower(): c for c in self.cities}
        self._county_set = {c.lower(): c for c in self.counties}

    def parse(self, raw_query: str) -> ParsedQuery:
        """Parse a raw search string into structured filters."""
        if not raw_query or not raw_query.strip():
            return ParsedQuery()

        result = ParsedQuery()
        text = raw_query.strip()

        # 1. Check for MLS number (entire query is an MLS#)
        mls_match = _MLS_RE.match(text.strip())
        if mls_match:
            mls_num = text.strip().upper()
            if not mls_num.startswith('CAR'):
                mls_num = mls_match.group(1)
            result.is_mls_lookup = True
            result.filters['mls_number'] = mls_num
            result.interpretations.append(f'MLS# {mls_num}')
            return result

        # 2. Check for address pattern
        addr_match = _ADDRESS_RE.search(text)
        if addr_match:
            result.is_address_lookup = True
            result.filters['q'] = text
            result.interpretations.append(f'Address: {addr_match.group(0).strip()}')
            return result

        # 3. Extract unit-tagged values FIRST (acreage, sqft, elevation)
        #    before price patterns, so "over 5 acres" doesn't match as a price.

        # Acreage
        acreage_match = _ACREAGE_RE.search(text)
        if acreage_match:
            acres = float(acreage_match.group(1))
            result.filters['min_acreage'] = acres
            result.interpretations.append(f'{acres:g}+ acres')
            text = text[:acreage_match.start()] + text[acreage_match.end():]

        # Sqft
        sqft_match = _SQFT_RE.search(text)
        if sqft_match:
            sqft = int(sqft_match.group(1))
            result.filters['min_sqft'] = sqft
            result.interpretations.append(f'{sqft:,}+ sq ft')
            text = text[:sqft_match.start()] + text[sqft_match.end():]

        # Elevation
        elev_below = _ELEVATION_BELOW_RE.search(text)
        if elev_below:
            result.filters['max_elevation'] = int(elev_below.group(1))
            result.interpretations.append(f'Below {elev_below.group(1)} ft')
            text = text[:elev_below.start()] + text[elev_below.end():]

        elev_above = _ELEVATION_ABOVE_RE.search(text)
        if elev_above:
            result.filters['min_elevation'] = int(elev_above.group(1))
            result.interpretations.append(f'Above {elev_above.group(1)} ft')
            text = text[:elev_above.start()] + text[elev_above.end():]

        if 'min_elevation' not in result.filters and 'max_elevation' not in result.filters:
            elev_match = _ELEVATION_RE.search(text)
            if elev_match:
                result.filters['min_elevation'] = int(elev_match.group(1))
                result.interpretations.append(f'Above {elev_match.group(1)} ft')
                text = text[:elev_match.start()] + text[elev_match.end():]

        # Bedrooms
        beds_match = _BEDS_RE.search(text)
        if beds_match:
            beds = int(beds_match.group(1))
            result.filters['min_beds'] = beds
            result.interpretations.append(f'{beds}+ bedrooms')
            text = text[:beds_match.start()] + text[beds_match.end():]

        # Bathrooms
        baths_match = _BATHS_RE.search(text)
        if baths_match:
            baths = float(baths_match.group(1))
            result.filters['min_baths'] = baths
            result.interpretations.append(f'{baths:g}+ bathrooms')
            text = text[:baths_match.start()] + text[baths_match.end():]

        # 4. Now extract prices (after unit-tagged values are consumed)
        range_match = _PRICE_RANGE_RE.search(text)
        if range_match:
            min_p = _parse_price(range_match.group(1), range_match.group(2) or '')
            max_p = _parse_price(range_match.group(3), range_match.group(4) or '')
            if min_p:
                result.filters['min_price'] = min_p
            if max_p:
                result.filters['max_price'] = max_p
            result.interpretations.append(f'${min_p:,} - ${max_p:,}')
            text = text[:range_match.start()] + text[range_match.end():]

        if 'max_price' not in result.filters:
            below_match = _PRICE_BELOW_RE.search(text)
            if below_match:
                price = _parse_price(below_match.group(1), below_match.group(2) or '')
                if price:
                    result.filters['max_price'] = price
                    result.interpretations.append(f'Under ${price:,}')
                    text = text[:below_match.start()] + text[below_match.end():]

        if 'min_price' not in result.filters:
            above_match = _PRICE_ABOVE_RE.search(text)
            if above_match:
                price = _parse_price(above_match.group(1), above_match.group(2) or '')
                if price:
                    result.filters['min_price'] = price
                    result.interpretations.append(f'Over ${price:,}')
                    text = text[:above_match.start()] + text[above_match.end():]

        # 5. Extract view score
        view_score_match = _VIEW_SCORE_RE.search(text)
        if view_score_match:
            score = int(view_score_match.group(1))
            if 1 <= score <= 5:
                result.filters['min_view_score'] = score
                result.interpretations.append(f'View score {score}+')
                text = text[:view_score_match.start()] + text[view_score_match.end():]

        # 11. Extract view keywords (check before property type to avoid "view" conflicts)
        text_lower = text.lower()
        for vkw in VIEW_KEYWORDS:
            if vkw in text_lower:
                result.filters['has_view'] = True
                result.interpretations.append('Has view')
                # Remove the keyword from text
                idx = text_lower.find(vkw)
                text = text[:idx] + text[idx + len(vkw):]
                text_lower = text.lower()
                break

        # 12. Extract property type keywords
        words = text.lower().split()
        for word in words:
            clean = word.strip('.,;:!?')
            if clean in _KEYWORD_TO_TYPE:
                result.filters['property_type'] = _KEYWORD_TO_TYPE[clean]
                result.interpretations.append(_KEYWORD_TO_TYPE[clean])
                text = re.sub(rf'\b{re.escape(clean)}\b', '', text, flags=re.IGNORECASE)
                break

        # 13. Extract county (check "X County" pattern first, then standalone)
        text_lower = text.lower()
        for county in self.counties:
            county_pattern = county.lower() + ' county'
            if county_pattern in text_lower:
                result.filters['county'] = county
                result.interpretations.append(f'{county} County')
                idx = text_lower.find(county_pattern)
                text = text[:idx] + text[idx + len(county_pattern):]
                text_lower = text.lower()
                break
        else:
            # Try standalone county name (only if it's not also a city name,
            # or if no city match would be found)
            for county in self.counties:
                pattern = rf'\b{re.escape(county)}\b'
                if re.search(pattern, text, re.IGNORECASE):
                    # If this is also a city name, skip (city takes priority)
                    if county.lower() in self._city_set:
                        continue
                    result.filters['county'] = county
                    result.interpretations.append(f'{county} County')
                    text = re.sub(pattern, '', text, flags=re.IGNORECASE)
                    text_lower = text.lower()
                    break

        # 14. Extract city
        text_lower = text.lower()
        for city in self.cities:
            pattern = rf'\b{re.escape(city)}\b'
            if re.search(pattern, text, re.IGNORECASE):
                result.filters['city'] = city
                result.interpretations.append(city)
                text = re.sub(pattern, '', text, flags=re.IGNORECASE)
                break

        # 15. Clean up remainder (remove noise words and extra whitespace)
        noise = {'in', 'at', 'on', 'near', 'the', 'a', 'an', 'with', 'and', 'or', 'for', 'to', 'of'}
        remainder_words = [w for w in text.split() if w.lower().strip('.,;:!?') not in noise and len(w.strip()) > 1]
        result.remainder = ' '.join(remainder_words).strip()

        # If there's meaningful remainder, pass it as q for LIKE search
        if result.remainder:
            result.filters['q'] = result.remainder

        return result
