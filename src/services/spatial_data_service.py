"""
NC OneMap Spatial Data Service

Provides access to NC OneMap's ArcGIS REST services for:
- Flood zone data (FEMA flood hazard areas)
- Elevation/terrain data (DEM)
- School district boundaries
- Environmental constraints (wildfire, wetlands, landslides)
- Geocoding via AddressNC

All NC OneMap services:
https://services.nconemap.gov/secure/rest/services
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

# NC OneMap ArcGIS REST API endpoints
NCONEMAP_BASE = "https://services.nconemap.gov/secure/rest/services"

# Layer endpoints
FLOOD_URL = f"{NCONEMAP_BASE}/NC1Map_Floodplains/MapServer/0/query"  # Flood Hazard Areas
SCHOOLS_URL = f"{NCONEMAP_BASE}/NC1Map_Education/MapServer/3/query"  # Public Schools
ENVIRONMENT_URL = f"{NCONEMAP_BASE}/NC1Map_Environment/MapServer"
PARCELS_URL = f"{NCONEMAP_BASE}/NC1Map_Parcels/FeatureServer/0/query"
GEOCODE_URL = f"{NCONEMAP_BASE}/AddressNC/GeocodeServer/findAddressCandidates"

# Public USGS elevation service (no authentication required)
USGS_ELEVATION_URL = "https://epqs.nationalmap.gov/v1/json"

# Wildfire risk layers within Environment service
WILDFIRE_LAYER = 6  # Wildfire Risk


@dataclass
class FloodZoneResult:
    """Flood zone query result."""
    zone: str  # X, A, AE, VE, etc.
    zone_subtype: Optional[str] = None
    description: str = ""
    sfha: bool = False  # Special Flood Hazard Area (true = high risk)
    flood_factor: int = 1  # 1-10 risk score (1=minimal, 10=highest)
    panel: Optional[str] = None  # FEMA panel number

    @classmethod
    def from_feature(cls, feature: Dict) -> 'FloodZoneResult':
        """Create from ArcGIS feature."""
        attrs = feature.get('attributes', {})
        zone = attrs.get('FLD_ZONE', 'X')
        zone_subtype = attrs.get('ZONE_SUBTY')
        sfha = attrs.get('SFHA_TF', 'F') == 'T'

        # Calculate flood factor (1-10)
        factor = cls._calculate_flood_factor(zone, zone_subtype, sfha)

        # Generate description
        desc = cls._get_zone_description(zone, zone_subtype)

        return cls(
            zone=zone,
            zone_subtype=zone_subtype,
            description=desc,
            sfha=sfha,
            flood_factor=factor,
            panel=attrs.get('FIRM_PAN')
        )

    @staticmethod
    def _calculate_flood_factor(zone: str, subtype: str, sfha: bool) -> int:
        """
        Calculate flood risk factor 1-10.

        1-2: Minimal risk (Zone X)
        3-4: Low risk (Zone X with shallow flooding)
        5-6: Moderate risk (Zone A without BFE)
        7-8: High risk (Zone AE with BFE)
        9-10: Very high risk (Zone VE, coastal)
        """
        zone = zone.upper() if zone else 'X'

        if zone == 'X':
            if subtype and 'SHADED' in subtype.upper():
                return 3  # 0.2% annual chance
            return 1  # Minimal risk
        elif zone == 'D':
            return 3  # Undetermined but possible
        elif zone == 'A':
            return 6  # 1% annual chance, no BFE
        elif zone == 'AO':
            return 6  # Sheet flow, 1% annual
        elif zone == 'AH':
            return 7  # Ponding, 1% annual
        elif zone == 'AE':
            return 7  # 1% annual with BFE
        elif zone in ('AR', 'A99'):
            return 6  # Protected by levee
        elif zone == 'V':
            return 9  # Coastal, no BFE
        elif zone == 'VE':
            return 10  # Coastal with wave action
        else:
            return 5 if sfha else 2

    @staticmethod
    def _get_zone_description(zone: str, subtype: str) -> str:
        """Get human-readable description."""
        zone = zone.upper() if zone else 'X'

        descriptions = {
            'X': 'Minimal flood hazard',
            'A': '100-year flood zone (no BFE)',
            'AE': '100-year flood zone with base flood elevation',
            'AO': 'River or stream flood zone, sheet flow',
            'AH': 'Flood zone with ponding',
            'AR': 'Flood zone protected by levee',
            'A99': 'Flood zone protected by levee under construction',
            'V': 'Coastal flood zone with velocity hazard',
            'VE': 'Coastal flood zone with wave action',
            'D': 'Undetermined flood hazard',
        }

        desc = descriptions.get(zone, f'Flood zone {zone}')

        if subtype:
            if 'SHADED' in subtype.upper():
                desc = '500-year flood zone (0.2% annual chance)'
            elif 'FLOODWAY' in subtype.upper():
                desc += ' (within floodway - highest risk)'

        return desc


@dataclass
class ElevationResult:
    """Elevation query result."""
    elevation_feet: int
    elevation_meters: float
    slope_percent: Optional[float] = None
    aspect: Optional[str] = None  # N, NE, E, SE, S, SW, W, NW
    view_potential: Optional[int] = None  # 1-10 score

    @classmethod
    def from_identify(cls, data: Dict) -> 'ElevationResult':
        """Create from ImageServer identify response."""
        # Elevation value is in the response
        elevation_m = float(data.get('value', 0))
        elevation_ft = int(elevation_m * 3.28084)

        return cls(
            elevation_feet=elevation_ft,
            elevation_meters=elevation_m
        )


@dataclass
class SchoolResult:
    """School district query result."""
    district_name: str
    school_name: Optional[str] = None
    school_type: Optional[str] = None  # Elementary, Middle, High
    distance_miles: Optional[float] = None

    @classmethod
    def from_feature(cls, feature: Dict) -> 'SchoolResult':
        """Create from ArcGIS feature."""
        attrs = feature.get('attributes', {})
        return cls(
            district_name=attrs.get('DISTRICT', attrs.get('LEA_NAME', '')),
            school_name=attrs.get('SCHNAME', attrs.get('SCH_NAME', '')),
            school_type=attrs.get('LEVEL', attrs.get('SCH_TYPE', ''))
        )


@dataclass
class EnvironmentResult:
    """Environmental constraints result."""
    wildfire_risk: Optional[str] = None  # Low, Moderate, High, Very High
    wildfire_score: int = 1  # 1-10
    landslide_risk: Optional[str] = None
    wetland_type: Optional[str] = None
    steep_slope: bool = False

    @classmethod
    def from_features(cls, wildfire: Dict = None, wetland: Dict = None) -> 'EnvironmentResult':
        """Create from multiple layer queries."""
        result = cls()

        if wildfire:
            attrs = wildfire.get('attributes', {})
            risk = attrs.get('RISK_CATEGORY', attrs.get('WUI_RISK', ''))
            result.wildfire_risk = risk if risk else None
            result.wildfire_score = cls._wildfire_score(risk)

        if wetland:
            attrs = wetland.get('attributes', {})
            result.wetland_type = attrs.get('WETLAND_TYPE', attrs.get('ATTRIBUTE', ''))

        return result

    @staticmethod
    def _wildfire_score(risk: str) -> int:
        """Convert risk category to 1-10 score."""
        if not risk:
            return 1
        risk = risk.upper()
        if 'VERY HIGH' in risk or 'EXTREME' in risk:
            return 10
        elif 'HIGH' in risk:
            return 7
        elif 'MODERATE' in risk or 'MEDIUM' in risk:
            return 5
        elif 'LOW' in risk:
            return 2
        return 1


@dataclass
class SpatialEnrichment:
    """Combined spatial enrichment data for a property."""
    latitude: float
    longitude: float
    flood: Optional[FloodZoneResult] = None
    elevation: Optional[ElevationResult] = None
    school: Optional[SchoolResult] = None
    environment: Optional[EnvironmentResult] = None
    enriched_at: Optional[str] = None


class SpatialDataService:
    """
    Service for querying NC OneMap spatial data.

    Rate limiting: 0.5s delay between requests to be respectful.
    Caching: LRU cache for repeated queries.
    CRS handling: Requests in WGS84 (EPSG:4326), converts as needed.
    """

    def __init__(self, rate_limit_delay: float = 0.5):
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'myDREAMS/1.0 Real Estate Platform'
        })

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, url: str, params: Dict, timeout: int = 30) -> Optional[Dict]:
        """Make HTTP request with error handling."""
        self._rate_limit()

        try:
            response = self.session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed: {url} - {e}")
            return None
        except ValueError as e:
            logger.warning(f"Invalid JSON response: {url} - {e}")
            return None

    def query_flood_zone(self, lat: float, lon: float) -> Optional[FloodZoneResult]:
        """
        Query FEMA flood zone at a point.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)

        Returns:
            FloodZoneResult or None if not in a mapped flood zone
        """
        # Point query using geometry intersection
        params = {
            'geometry': f'{lon},{lat}',
            'geometryType': 'esriGeometryPoint',
            'inSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': 'FLD_ZONE,ZONE_SUBTY,SFHA_TF,FIRM_PAN',
            'returnGeometry': 'false',
            'f': 'json'
        }

        data = self._make_request(FLOOD_URL, params)

        if not data:
            return None

        features = data.get('features', [])

        if not features:
            # No flood zone data = minimal risk (Zone X)
            return FloodZoneResult(
                zone='X',
                description='Outside mapped flood hazard area',
                sfha=False,
                flood_factor=1
            )

        # Return highest risk zone if multiple
        results = [FloodZoneResult.from_feature(f) for f in features]
        return max(results, key=lambda r: r.flood_factor)

    def query_elevation(self, lat: float, lon: float) -> Optional[ElevationResult]:
        """
        Query elevation at a point using USGS National Map service.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)

        Returns:
            ElevationResult or None
        """
        params = {
            'x': lon,
            'y': lat,
            'units': 'Feet',
            'output': 'json'
        }

        data = self._make_request(USGS_ELEVATION_URL, params)

        if not data or 'value' not in data:
            return None

        try:
            elevation_ft = int(data['value'])
            return ElevationResult(
                elevation_feet=elevation_ft,
                elevation_meters=elevation_ft / 3.28084
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Failed to parse elevation: {e}")
            return None

    def query_slope_aspect(self, lat: float, lon: float) -> Tuple[Optional[float], Optional[str]]:
        """
        Query slope and aspect at a point using DEM services.

        Returns:
            (slope_percent, aspect_direction) tuple
        """
        # NC OneMap has separate slope/aspect services
        slope_url = f"{NCONEMAP_BASE}/NC1Map_Elevation/NC_DEM03_Slope/ImageServer/identify"
        aspect_url = f"{NCONEMAP_BASE}/NC1Map_Elevation/NC_DEM03_Aspect/ImageServer/identify"

        params = {
            'geometry': f'{lon},{lat}',
            'geometryType': 'esriGeometryPoint',
            'f': 'json'
        }

        slope = None
        aspect = None

        # Query slope
        slope_data = self._make_request(slope_url, params)
        if slope_data and 'value' in slope_data:
            try:
                slope = float(slope_data['value'])
            except (ValueError, TypeError):
                pass

        # Query aspect
        aspect_data = self._make_request(aspect_url, params)
        if aspect_data and 'value' in aspect_data:
            try:
                aspect_deg = float(aspect_data['value'])
                aspect = self._degrees_to_direction(aspect_deg)
            except (ValueError, TypeError):
                pass

        return slope, aspect

    @staticmethod
    def _degrees_to_direction(degrees: float) -> str:
        """Convert aspect degrees to cardinal direction."""
        if degrees < 0:
            return 'Flat'

        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        index = int((degrees + 22.5) / 45) % 8
        return directions[index]

    def query_schools_nearby(
        self,
        lat: float,
        lon: float,
        radius_miles: float = 5.0
    ) -> List[SchoolResult]:
        """
        Query schools within radius of a point.

        Args:
            lat: Latitude
            lon: Longitude
            radius_miles: Search radius in miles

        Returns:
            List of SchoolResult
        """
        # Convert miles to meters for buffer
        radius_meters = radius_miles * 1609.34

        params = {
            'geometry': f'{lon},{lat}',
            'geometryType': 'esriGeometryPoint',
            'inSR': '4326',
            'distance': radius_meters,
            'units': 'esriSRUnit_Meter',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': 'SCHNAME,SCH_NAME,DISTRICT,LEA_NAME,LEVEL,SCH_TYPE',
            'returnGeometry': 'true',
            'outSR': '4326',
            'f': 'json'
        }

        data = self._make_request(SCHOOLS_URL, params)

        if not data:
            return []

        results = []
        for feature in data.get('features', []):
            result = SchoolResult.from_feature(feature)

            # Calculate distance if geometry present
            geom = feature.get('geometry')
            if geom and 'x' in geom and 'y' in geom:
                dist = self._haversine_miles(lat, lon, geom['y'], geom['x'])
                result.distance_miles = round(dist, 1)

            results.append(result)

        # Sort by distance
        results.sort(key=lambda s: s.distance_miles or 999)

        return results

    def query_wildfire_risk(self, lat: float, lon: float) -> Optional[str]:
        """
        Query wildfire risk level at a point.

        Returns:
            Risk category string or None
        """
        url = f"{ENVIRONMENT_URL}/{WILDFIRE_LAYER}/query"

        params = {
            'geometry': f'{lon},{lat}',
            'geometryType': 'esriGeometryPoint',
            'inSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': '*',
            'returnGeometry': 'false',
            'f': 'json'
        }

        data = self._make_request(url, params)

        if not data:
            return None

        features = data.get('features', [])
        if not features:
            return None

        attrs = features[0].get('attributes', {})
        # Try common field names
        for field in ['RISK_CATEGORY', 'WUI_RISK', 'RISK', 'HAZARD']:
            if field in attrs and attrs[field]:
                return str(attrs[field])

        return None

    def query_environment(self, lat: float, lon: float) -> EnvironmentResult:
        """
        Query environmental constraints at a point.

        Returns:
            EnvironmentResult with wildfire risk and other data
        """
        wildfire_risk = self.query_wildfire_risk(lat, lon)

        result = EnvironmentResult()
        if wildfire_risk:
            result.wildfire_risk = wildfire_risk
            result.wildfire_score = EnvironmentResult._wildfire_score(wildfire_risk)

        return result

    def geocode_address(self, address: str, city: str = None, state: str = 'NC') -> Optional[Tuple[float, float]]:
        """
        Geocode an address using NC AddressNC service.

        Args:
            address: Street address
            city: City name (optional)
            state: State (default NC)

        Returns:
            (latitude, longitude) tuple or None
        """
        # Build single-line address
        full_address = address
        if city:
            full_address += f", {city}"
        full_address += f", {state}"

        params = {
            'SingleLine': full_address,
            'f': 'json',
            'outSR': '4326',
            'maxLocations': 1
        }

        data = self._make_request(GEOCODE_URL, params)

        if not data:
            return None

        candidates = data.get('candidates', [])
        if not candidates:
            return None

        # Take best match
        best = candidates[0]
        location = best.get('location', {})

        if 'x' in location and 'y' in location:
            return (location['y'], location['x'])

        return None

    def enrich_property(
        self,
        lat: float,
        lon: float,
        include_flood: bool = True,
        include_elevation: bool = True,
        include_schools: bool = False,
        include_environment: bool = True
    ) -> SpatialEnrichment:
        """
        Full spatial enrichment for a property location.

        Args:
            lat: Latitude
            lon: Longitude
            include_flood: Query flood zone
            include_elevation: Query elevation
            include_schools: Query nearby schools
            include_environment: Query environmental constraints

        Returns:
            SpatialEnrichment with all requested data
        """
        from datetime import datetime

        enrichment = SpatialEnrichment(
            latitude=lat,
            longitude=lon,
            enriched_at=datetime.now().isoformat()
        )

        if include_flood:
            enrichment.flood = self.query_flood_zone(lat, lon)

        if include_elevation:
            elevation = self.query_elevation(lat, lon)
            if elevation:
                slope, aspect = self.query_slope_aspect(lat, lon)
                elevation.slope_percent = slope
                elevation.aspect = aspect
                enrichment.elevation = elevation

        if include_schools:
            schools = self.query_schools_nearby(lat, lon, radius_miles=10)
            if schools:
                enrichment.school = schools[0]  # Nearest

        if include_environment:
            enrichment.environment = self.query_environment(lat, lon)

        return enrichment

    @staticmethod
    def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in miles."""
        from math import radians, sin, cos, sqrt, atan2

        R = 3959  # Earth radius in miles

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c

    def calculate_view_potential(
        self,
        lat: float,
        lon: float,
        elevation: int
    ) -> int:
        """
        Calculate mountain view potential score (1-10).

        Higher scores for:
        - Higher elevation relative to surroundings
        - South/West facing (mountain view) aspects
        - Ridge/hilltop positions

        Args:
            lat: Latitude
            lon: Longitude
            elevation: Elevation in feet

        Returns:
            Score 1-10
        """
        score = 5  # Default moderate

        # Elevation bonus (WNC mountains)
        if elevation > 4000:
            score += 3
        elif elevation > 3000:
            score += 2
        elif elevation > 2000:
            score += 1
        elif elevation < 1500:
            score -= 1

        # Get slope/aspect for this location
        slope, aspect = self.query_slope_aspect(lat, lon)

        # Aspect bonus (views typically SW-NW in WNC)
        if aspect in ('S', 'SW', 'W'):
            score += 2
        elif aspect in ('SE', 'NW'):
            score += 1

        # Moderate slope is good for views (not flat, not cliff)
        if slope:
            if 10 <= slope <= 30:
                score += 1
            elif slope > 50:
                score -= 1

        # Clamp to 1-10
        return max(1, min(10, score))


# Convenience function for quick queries
def get_spatial_service() -> SpatialDataService:
    """Get singleton spatial data service instance."""
    return SpatialDataService()
