"""
DREAMS Base Adapter Interfaces

This module defines the abstract interfaces that all adapters must implement.
The adapter pattern allows swapping external systems without changing core logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import json


# ============================================
# DATA CLASSES (Canonical Representations)
# ============================================

@dataclass
class Lead:
    """Canonical lead/contact representation"""
    id: str
    external_id: str
    external_source: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: str = "lead"
    type: str = "buyer"  # buyer, seller, both, investor
    source: Optional[str] = None
    assigned_agent: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    
    # Scoring
    heat_score: int = 0
    value_score: int = 0
    relationship_score: int = 0
    priority_score: int = 0
    
    # Buyer requirements (if applicable)
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_beds: Optional[int] = None
    min_baths: Optional[float] = None
    min_sqft: Optional[int] = None
    min_acreage: Optional[float] = None
    preferred_cities: List[str] = field(default_factory=list)
    preferred_features: List[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'id': self.id,
            'external_id': self.external_id,
            'external_source': self.external_source,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'stage': self.stage,
            'type': self.type,
            'source': self.source,
            'assigned_agent': self.assigned_agent,
            'tags': json.dumps(self.tags),
            'notes': self.notes,
            'heat_score': self.heat_score,
            'value_score': self.value_score,
            'relationship_score': self.relationship_score,
            'priority_score': self.priority_score,
            'min_price': self.min_price,
            'max_price': self.max_price,
            'min_beds': self.min_beds,
            'min_baths': self.min_baths,
            'min_sqft': self.min_sqft,
            'min_acreage': self.min_acreage,
            'preferred_cities': json.dumps(self.preferred_cities),
            'preferred_features': json.dumps(self.preferred_features),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


@dataclass
class Activity:
    """Canonical activity/event representation"""
    id: str
    lead_id: str
    activity_type: str  # search, save, favorite, inquiry, view, email_open, call, etc.
    activity_source: str  # fub, real_geeks, zillow, manual
    activity_data: Dict[str, Any] = field(default_factory=dict)
    property_id: Optional[str] = None
    occurred_at: datetime = field(default_factory=datetime.now)
    imported_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'activity_type': self.activity_type,
            'activity_source': self.activity_source,
            'activity_data': json.dumps(self.activity_data),
            'property_id': self.property_id,
            'occurred_at': self.occurred_at.isoformat(),
            'imported_at': self.imported_at.isoformat(),
        }


@dataclass
class Property:
    """Canonical property representation"""
    id: str
    address: str
    city: str
    state: str
    zip: str
    price: int
    beds: int
    baths: float
    sqft: int
    status: str = "active"
    
    # Identifiers
    mls_number: Optional[str] = None
    parcel_id: Optional[str] = None
    zillow_id: Optional[str] = None
    
    # Details
    acreage: Optional[float] = None
    year_built: Optional[int] = None
    property_type: str = "single_family"
    style: Optional[str] = None
    county: Optional[str] = None
    
    # Features (JSON arrays)
    views: List[str] = field(default_factory=list)
    water_features: List[str] = field(default_factory=list)
    amenities: List[str] = field(default_factory=list)
    
    # Market data
    days_on_market: Optional[int] = None
    list_date: Optional[str] = None
    initial_price: Optional[int] = None
    price_history: List[Dict] = field(default_factory=list)
    
    # Agent info
    listing_agent_name: Optional[str] = None
    listing_agent_phone: Optional[str] = None
    listing_agent_email: Optional[str] = None
    listing_brokerage: Optional[str] = None
    
    # Links
    zillow_url: Optional[str] = None
    realtor_url: Optional[str] = None
    mls_url: Optional[str] = None
    idx_url: Optional[str] = None
    
    # Media
    photo_urls: List[str] = field(default_factory=list)
    virtual_tour_url: Optional[str] = None
    
    # Metadata
    source: str = "manual"
    notes: Optional[str] = None
    captured_by: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'mls_number': self.mls_number,
            'parcel_id': self.parcel_id,
            'zillow_id': self.zillow_id,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'zip': self.zip,
            'county': self.county,
            'price': self.price,
            'beds': self.beds,
            'baths': self.baths,
            'sqft': self.sqft,
            'acreage': self.acreage,
            'year_built': self.year_built,
            'property_type': self.property_type,
            'style': self.style,
            'views': json.dumps(self.views),
            'water_features': json.dumps(self.water_features),
            'amenities': json.dumps(self.amenities),
            'status': self.status,
            'days_on_market': self.days_on_market,
            'list_date': self.list_date,
            'initial_price': self.initial_price,
            'price_history': json.dumps(self.price_history),
            'listing_agent_name': self.listing_agent_name,
            'listing_agent_phone': self.listing_agent_phone,
            'listing_agent_email': self.listing_agent_email,
            'listing_brokerage': self.listing_brokerage,
            'zillow_url': self.zillow_url,
            'realtor_url': self.realtor_url,
            'mls_url': self.mls_url,
            'idx_url': self.idx_url,
            'photo_urls': json.dumps(self.photo_urls),
            'virtual_tour_url': self.virtual_tour_url,
            'source': self.source,
            'notes': self.notes,
            'captured_by': self.captured_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


@dataclass
class Match:
    """Buyer-property match representation"""
    id: str
    lead_id: str
    property_id: str
    total_score: float
    stated_score: float
    behavioral_score: float
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    match_status: str = "suggested"  # suggested, sent, viewed, interested, rejected, shown
    
    suggested_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    response_at: Optional[datetime] = None
    shown_at: Optional[datetime] = None
    
    lead_feedback: Optional[str] = None
    agent_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'property_id': self.property_id,
            'total_score': self.total_score,
            'stated_score': self.stated_score,
            'behavioral_score': self.behavioral_score,
            'score_breakdown': json.dumps(self.score_breakdown),
            'match_status': self.match_status,
            'suggested_at': self.suggested_at.isoformat(),
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'response_at': self.response_at.isoformat() if self.response_at else None,
            'shown_at': self.shown_at.isoformat() if self.shown_at else None,
            'lead_feedback': self.lead_feedback,
            'agent_notes': self.agent_notes,
        }


# ============================================
# ABSTRACT ADAPTER INTERFACES
# ============================================

class CRMAdapter(ABC):
    """
    Abstract interface for CRM integrations.
    
    Implementations must handle:
    - Authentication with the CRM
    - Fetching leads/contacts
    - Fetching activities/events
    - Pushing updates back to CRM (optional)
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to CRM.
        Returns True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connection resources."""
        pass
    
    @abstractmethod
    def fetch_leads(
        self,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Lead]:
        """
        Fetch leads from CRM.
        
        Args:
            since: Only fetch leads updated after this time
            limit: Maximum number of leads to fetch
            offset: Starting offset for pagination
            
        Returns:
            List of Lead objects in canonical format
        """
        pass
    
    @abstractmethod
    def fetch_lead(self, external_id: str) -> Optional[Lead]:
        """
        Fetch single lead by CRM ID.
        
        Args:
            external_id: The lead's ID in the source CRM
            
        Returns:
            Lead object or None if not found
        """
        pass
    
    @abstractmethod
    def fetch_activities(
        self,
        lead_id: str,
        since: Optional[datetime] = None,
        activity_types: Optional[List[str]] = None
    ) -> List[Activity]:
        """
        Fetch activities/events for a lead.
        
        Args:
            lead_id: The lead's external ID
            since: Only fetch activities after this time
            activity_types: Filter to specific activity types
            
        Returns:
            List of Activity objects
        """
        pass
    
    @abstractmethod
    def update_lead(self, lead: Lead) -> bool:
        """
        Push lead updates back to CRM.
        
        Args:
            lead: Lead object with updated fields
            
        Returns:
            True if update succeeded
        """
        pass
    
    @abstractmethod
    def create_note(self, lead_id: str, note: str) -> bool:
        """
        Add note to lead in CRM.
        
        Args:
            lead_id: External ID of the lead
            note: Note content
            
        Returns:
            True if note was created
        """
        pass


class PropertyAdapter(ABC):
    """
    Abstract interface for property data sources.
    
    Implementations must handle:
    - Searching properties by criteria
    - Fetching individual property details
    - Monitoring properties for changes
    """
    
    @abstractmethod
    def search_properties(
        self,
        city: Optional[str] = None,
        state: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_beds: Optional[int] = None,
        max_beds: Optional[int] = None,
        min_sqft: Optional[int] = None,
        property_type: Optional[str] = None,
        **kwargs
    ) -> List[Property]:
        """
        Search for properties matching criteria.
        
        Returns:
            List of Property objects matching criteria
        """
        pass
    
    @abstractmethod
    def fetch_property(self, url: str) -> Optional[Property]:
        """
        Fetch single property by URL.
        
        Args:
            url: Property listing URL
            
        Returns:
            Property object or None if not found
        """
        pass
    
    @abstractmethod
    def monitor_property(self, property_id: str) -> Optional[Property]:
        """
        Check for updates to tracked property.
        
        Args:
            property_id: Internal DREAMS property ID
            
        Returns:
            Updated Property object or None if unchanged/unavailable
        """
        pass


class PresentationAdapter(ABC):
    """
    Abstract interface for presentation layer systems.
    
    Implementations must handle:
    - Syncing data to presentation layer (Notion, Airtable, etc.)
    - Pulling user edits back
    - Managing views and formatting
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to presentation system."""
        pass
    
    @abstractmethod
    def sync_leads(self, leads: List[Lead]) -> int:
        """
        Push leads to presentation layer.
        
        Args:
            leads: List of Lead objects to sync
            
        Returns:
            Number of records successfully synced
        """
        pass
    
    @abstractmethod
    def sync_properties(self, properties: List[Property]) -> int:
        """
        Push properties to presentation layer.
        
        Args:
            properties: List of Property objects to sync
            
        Returns:
            Number of records successfully synced
        """
        pass
    
    @abstractmethod
    def sync_matches(self, matches: List[Match]) -> int:
        """
        Push matches to presentation layer.
        
        Args:
            matches: List of Match objects to sync
            
        Returns:
            Number of records successfully synced
        """
        pass
    
    @abstractmethod
    def get_user_updates(
        self,
        entity_type: str,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Pull manual edits from presentation layer.
        
        Args:
            entity_type: 'leads', 'properties', or 'matches'
            since: Only get updates after this time
            
        Returns:
            List of dictionaries with updated fields
        """
        pass
