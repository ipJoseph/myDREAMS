"""
DREAMS Matching Engine

Intelligent buyer-property matching based on stated requirements
and behavioral signals.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import logging

from src.core.database import DREAMSDatabase
from src.adapters.base_adapter import Lead, Property, Match, Activity

logger = logging.getLogger(__name__)


@dataclass
class MatchWeights:
    """Configurable weights for matching algorithm."""
    price: float = 0.25
    location: float = 0.20
    size: float = 0.20
    features: float = 0.15
    style: float = 0.10
    recency: float = 0.10
    
    # Relative weight of behavioral vs stated preferences
    behavioral_weight: float = 0.6
    stated_weight: float = 0.4


@dataclass
class BuyerPreferences:
    """Inferred preferences from behavioral analysis."""
    inferred_min_price: Optional[int] = None
    inferred_max_price: Optional[int] = None
    preferred_cities: List[str] = None
    preferred_styles: List[str] = None
    preferred_features: List[str] = None
    confidence: float = 0.0
    
    def __post_init__(self):
        self.preferred_cities = self.preferred_cities or []
        self.preferred_styles = self.preferred_styles or []
        self.preferred_features = self.preferred_features or []


class MatchingEngine:
    """
    Core matching algorithm for buyer-property matching.
    
    Uses multi-factor scoring that weights behavioral signals
    over stated preferences (actions speak louder than words).
    """
    
    def __init__(
        self,
        db: DREAMSDatabase,
        weights: Optional[MatchWeights] = None
    ):
        self.db = db
        self.weights = weights or MatchWeights()
    
    def find_matches_for_lead(
        self,
        lead_id: str,
        min_score: float = 50.0,
        max_results: int = 20
    ) -> List[Match]:
        """
        Find and rank properties for a buyer.
        
        Args:
            lead_id: ID of the buyer lead
            min_score: Minimum match score (0-100)
            max_results: Maximum matches to return
            
        Returns:
            List of Match objects sorted by score
        """
        # Get lead data
        lead_data = self.db.get_lead(lead_id)
        if not lead_data:
            logger.warning(f"Lead not found: {lead_id}")
            return []
        
        # Get behavioral data
        activities = self.db.get_activities_for_lead(lead_id)
        behavioral_prefs = self._infer_preferences(activities)
        
        # Get active properties
        properties = self.db.get_properties(status='active', limit=1000)
        
        # Score each property
        matches = []
        for prop in properties:
            score = self._calculate_match_score(lead_data, prop, behavioral_prefs)
            if score['total'] >= min_score:
                match = Match(
                    id=f"match_{lead_id}_{prop['id']}",
                    lead_id=lead_id,
                    property_id=prop['id'],
                    total_score=score['total'],
                    stated_score=score['stated'],
                    behavioral_score=score['behavioral'],
                    score_breakdown=score['breakdown']
                )
                matches.append(match)
        
        # Sort by score and return top matches
        matches.sort(key=lambda m: m.total_score, reverse=True)
        return matches[:max_results]
    
    def _infer_preferences(
        self,
        activities: List[Dict[str, Any]]
    ) -> BuyerPreferences:
        """
        Analyze lead activities to infer actual preferences.
        
        Weight activities by type:
        - Inquiries: 4.0 (strongest signal)
        - Saves: 3.0
        - Favorites: 2.5
        - Views: 1.0 (weakest signal)
        """
        if not activities:
            return BuyerPreferences(confidence=0.0)
        
        # Weight by activity type
        weights = {
            'inquiry': 4.0,
            'save': 3.0,
            'favorite': 2.5,
            'view': 1.0,
            'search': 1.5,
            'email_click': 2.0,
        }
        
        # Collect weighted property attributes
        prices = []
        cities = []
        styles = []
        features = []
        
        for activity in activities:
            weight = weights.get(activity.get('activity_type', ''), 1.0)
            property_id = activity.get('property_id')
            
            if property_id:
                prop = self.db.get_property(property_id)
                if prop:
                    # Add weighted samples
                    for _ in range(int(weight)):
                        if prop.get('price'):
                            prices.append(prop['price'])
                        if prop.get('city'):
                            cities.append(prop['city'])
                        if prop.get('style'):
                            styles.append(prop['style'])
                        
                        # Extract features from JSON fields
                        for field in ['views', 'water_features', 'amenities']:
                            if prop.get(field):
                                try:
                                    items = json.loads(prop[field])
                                    features.extend(items)
                                except (json.JSONDecodeError, TypeError):
                                    pass
        
        # Calculate inferred ranges
        if not prices:
            return BuyerPreferences(confidence=0.1)
        
        prices.sort()
        n = len(prices)
        
        return BuyerPreferences(
            inferred_min_price=prices[int(n * 0.1)] if n > 1 else prices[0],
            inferred_max_price=prices[int(n * 0.9)] if n > 1 else prices[0],
            preferred_cities=self._most_common(cities, 3),
            preferred_styles=self._most_common(styles, 2),
            preferred_features=self._most_common(features, 10),
            confidence=min(1.0, len(activities) / 20)  # More activities = more confidence
        )
    
    def _calculate_match_score(
        self,
        lead: Dict[str, Any],
        property: Dict[str, Any],
        behavioral: BuyerPreferences
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive match score.
        
        Returns dict with:
        - total: Overall score (0-100)
        - stated: Score from stated requirements
        - behavioral: Score from behavioral analysis
        - breakdown: Per-factor scores
        """
        breakdown = {}
        
        # Price scoring (25%)
        breakdown['price'] = self._score_price(
            property.get('price', 0),
            lead.get('min_price'), lead.get('max_price'),
            behavioral.inferred_min_price, behavioral.inferred_max_price
        ) * self.weights.price * 100
        
        # Location scoring (20%)
        breakdown['location'] = self._score_location(
            property.get('city', ''),
            self._parse_json_list(lead.get('preferred_cities')),
            behavioral.preferred_cities
        ) * self.weights.location * 100
        
        # Size scoring (20%)
        breakdown['size'] = self._score_size(
            property.get('beds', 0),
            property.get('baths', 0),
            property.get('sqft', 0),
            lead.get('min_beds'),
            lead.get('min_baths'),
            lead.get('min_sqft')
        ) * self.weights.size * 100
        
        # Feature scoring (15%)
        prop_features = (
            self._parse_json_list(property.get('views')) +
            self._parse_json_list(property.get('water_features')) +
            self._parse_json_list(property.get('amenities'))
        )
        breakdown['features'] = self._score_features(
            prop_features,
            behavioral.preferred_features
        ) * self.weights.features * 100
        
        # Style scoring (10%)
        breakdown['style'] = self._score_style(
            property.get('style', ''),
            behavioral.preferred_styles
        ) * self.weights.style * 100
        
        # Recency scoring (10%)
        breakdown['recency'] = self._score_recency(
            property.get('days_on_market', 0)
        ) * self.weights.recency * 100
        
        # Calculate totals
        total = sum(breakdown.values())
        
        # Estimate stated vs behavioral contribution
        stated = breakdown['size'] + (breakdown['price'] * 0.5)
        behavioral_score = (
            breakdown['features'] + breakdown['style'] +
            breakdown['location'] + (breakdown['price'] * 0.5)
        )
        
        return {
            'total': round(total, 1),
            'stated': round(stated, 1),
            'behavioral': round(behavioral_score, 1),
            'breakdown': {k: round(v, 1) for k, v in breakdown.items()}
        }
    
    def _score_price(
        self,
        price: int,
        stated_min: Optional[int],
        stated_max: Optional[int],
        inferred_min: Optional[int],
        inferred_max: Optional[int]
    ) -> float:
        """Score price fit. Returns 0.0-1.0"""
        if not price:
            return 0.0
        
        # Blend stated and inferred ranges
        min_price = stated_min or inferred_min or 0
        max_price = stated_max or inferred_max or float('inf')
        
        if inferred_min and stated_min:
            min_price = (stated_min * 0.4 + inferred_min * 0.6)
        if inferred_max and stated_max:
            max_price = (stated_max * 0.4 + inferred_max * 0.6)
        
        if min_price <= price <= max_price:
            return 1.0
        elif price < min_price:
            # Under budget is okay
            return 0.7
        else:
            # Over budget - penalty based on how much
            over_pct = (price - max_price) / max_price if max_price else 0
            return max(0, 1.0 - over_pct * 2)
    
    def _score_location(
        self,
        city: str,
        stated_cities: List[str],
        behavioral_cities: List[str]
    ) -> float:
        """Score location match. Returns 0.0-1.0"""
        if not city:
            return 0.5
        
        city_lower = city.lower()
        
        # Check behavioral (stronger signal)
        for bc in behavioral_cities:
            if bc.lower() == city_lower:
                return 1.0
        
        # Check stated
        for sc in stated_cities:
            if sc.lower() == city_lower:
                return 0.9
        
        return 0.3  # Not in preferred list
    
    def _score_size(
        self,
        beds: int,
        baths: float,
        sqft: int,
        min_beds: Optional[int],
        min_baths: Optional[float],
        min_sqft: Optional[int]
    ) -> float:
        """Score size requirements. Returns 0.0-1.0"""
        score = 1.0
        
        if min_beds and beds < min_beds:
            score *= 0.5
        if min_baths and baths < min_baths:
            score *= 0.8
        if min_sqft and sqft < min_sqft:
            score *= 0.7
        
        return score
    
    def _score_features(
        self,
        property_features: List[str],
        preferred_features: List[str]
    ) -> float:
        """Score feature overlap. Returns 0.0-1.0"""
        if not preferred_features:
            return 0.5
        
        prop_lower = {f.lower() for f in property_features}
        pref_lower = {f.lower() for f in preferred_features}
        
        overlap = len(prop_lower & pref_lower)
        return min(1.0, overlap / max(len(pref_lower), 1))
    
    def _score_style(
        self,
        property_style: str,
        preferred_styles: List[str]
    ) -> float:
        """Score style match. Returns 0.0-1.0"""
        if not property_style or not preferred_styles:
            return 0.5
        
        style_lower = property_style.lower()
        for ps in preferred_styles:
            if ps.lower() == style_lower:
                return 1.0
        
        return 0.3
    
    def _score_recency(self, days_on_market: int) -> float:
        """Score freshness - newer listings score higher. Returns 0.0-1.0"""
        if days_on_market is None:
            return 0.5
        
        if days_on_market <= 7:
            return 1.0
        elif days_on_market <= 30:
            return 0.8
        elif days_on_market <= 90:
            return 0.6
        else:
            return 0.4
    
    def _most_common(self, items: List[str], n: int) -> List[str]:
        """Get n most common items from list."""
        if not items:
            return []
        
        from collections import Counter
        counts = Counter(items)
        return [item for item, _ in counts.most_common(n)]
    
    def _parse_json_list(self, value: Any) -> List[str]:
        """Safely parse JSON list from database."""
        if not value:
            return []
        if isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
