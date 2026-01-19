
"""
FUB to Sheets - Version 2.0
Complete rewrite with enhanced features, security, and maintainability

Author: Joseph "Eugy" Williams
Date: December 2024
"""

import os
import sys
import time
import math
import json
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # myDREAMS root
CACHE_DIR = SCRIPT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Add project root to path for imports
sys.path.insert(0, str(PROJECT_ROOT))

from typing import Optional, Any
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from fub_core import FUBClient, DataCache
from fub_core import FUBError, FUBAPIError, RateLimitExceeded



# Load environment variables
load_dotenv()

# =========================================================================
# CONFIGURATION
# =========================================================================

class Config:
    """Centralized configuration with validation"""

    # Follow Up Boss
    FUB_API_KEY = os.getenv("FUB_API_KEY")
    FUB_BASE_URL = "https://api.followupboss.com/v1"

    # Google Sheets

    SCRIPT_DIR = Path(__file__).resolve().parent
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(SCRIPT_DIR / "service_account.json"),
    )
    GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

    # SMTP Email
    SMTP_ENABLED = os.getenv("SMTP_ENABLED", "true").lower() == "true"
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    EMAIL_TO = os.getenv("EMAIL_TO", os.getenv("SMTP_USERNAME"))
    EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[FUB Daily]")

    # SQLite Database Sync
    SQLITE_SYNC_ENABLED = os.getenv("SQLITE_SYNC_ENABLED", "true").lower() == "true"
    DREAMS_DB_PATH = os.getenv("DREAMS_DB_PATH", str(PROJECT_ROOT / "data" / "dreams.db"))

    # Performance Settings
    REQUEST_SLEEP_SECONDS = float(os.getenv("REQUEST_SLEEP_SECONDS", "0.2"))
    DEFAULT_FETCH_LIMIT = int(os.getenv("DEFAULT_FETCH_LIMIT", "100"))
    MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "5"))
    ENABLE_STAGE_SYNC = os.getenv("ENABLE_STAGE_SYNC", "false").lower() == "true"

    # Caching
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    CACHE_MAX_AGE_MINUTES = int(os.getenv("CACHE_MAX_AGE_MINUTES", "30"))

# Scoring Weights - Heat Score
    HEAT_WEIGHT_WEBSITE_VISIT = float(os.getenv("HEAT_WEIGHT_WEBSITE_VISIT", "1.5"))
    HEAT_WEIGHT_PROPERTY_VIEWED = float(os.getenv("HEAT_WEIGHT_PROPERTY_VIEWED", "3.0"))
    HEAT_WEIGHT_PROPERTY_FAVORITED = float(os.getenv("HEAT_WEIGHT_PROPERTY_FAVORITED", "5.0"))
    HEAT_WEIGHT_PROPERTY_SHARED = float(os.getenv("HEAT_WEIGHT_PROPERTY_SHARED", "1.5"))
    HEAT_WEIGHT_CALL_INBOUND = float(os.getenv("HEAT_WEIGHT_CALL_INBOUND", "5.0"))
    HEAT_WEIGHT_TEXT_INBOUND = float(os.getenv("HEAT_WEIGHT_TEXT_INBOUND", "3.0"))

    # Scoring Weights - Recency Bonuses
    RECENCY_BONUS_0_3_DAYS = int(os.getenv("RECENCY_BONUS_0_3_DAYS", "25"))
    RECENCY_BONUS_4_7_DAYS = int(os.getenv("RECENCY_BONUS_4_7_DAYS", "15"))
    RECENCY_BONUS_8_14_DAYS = int(os.getenv("RECENCY_BONUS_8_14_DAYS", "10"))
    RECENCY_BONUS_15_30_DAYS = int(os.getenv("RECENCY_BONUS_15_30_DAYS", "5"))

    # Scoring Weights - Priority Composite
    PRIORITY_WEIGHT_HEAT = float(os.getenv("PRIORITY_WEIGHT_HEAT", "0.50"))
    PRIORITY_WEIGHT_VALUE = float(os.getenv("PRIORITY_WEIGHT_VALUE", "0.20"))
    PRIORITY_WEIGHT_RELATIONSHIP = float(os.getenv("PRIORITY_WEIGHT_RELATIONSHIP", "0.30"))

    # Scoring Weights - Stage Multipliers
    STAGE_MULTIPLIER_HOT_LEAD = float(os.getenv("STAGE_MULTIPLIER_HOT_LEAD", "1.3"))
    STAGE_MULTIPLIER_ACTIVE_BUYER = float(os.getenv("STAGE_MULTIPLIER_ACTIVE_BUYER", "1.2"))
    STAGE_MULTIPLIER_ACTIVE_SELLER = float(os.getenv("STAGE_MULTIPLIER_ACTIVE_SELLER", "1.2"))
    STAGE_MULTIPLIER_NURTURE = float(os.getenv("STAGE_MULTIPLIER_NURTURE", "1.0"))
    STAGE_MULTIPLIER_NEW_LEAD = float(os.getenv("STAGE_MULTIPLIER_NEW_LEAD", "0.9"))
    STAGE_MULTIPLIER_COLD = float(os.getenv("STAGE_MULTIPLIER_COLD", "0.7"))
    STAGE_MULTIPLIER_CLOSED = float(os.getenv("STAGE_MULTIPLIER_CLOSED", "0.0"))
    STAGE_MULTIPLIER_TRASH = float(os.getenv("STAGE_MULTIPLIER_TRASH", "0.0"))

    # Call List Settings
    CALL_LIST_MIN_PRIORITY = int(os.getenv("CALL_LIST_MIN_PRIORITY", "45"))
    CALL_LIST_MAX_ROWS = int(os.getenv("CALL_LIST_MAX_ROWS", "50"))

    # Exclusion Filters
    EXCLUDE_LEAD_IDS = os.getenv("EXCLUDE_LEAD_IDS", "")
    EXCLUDE_EMAILS = os.getenv("EXCLUDE_EMAILS", "")

    @classmethod
    def get_excluded_ids(cls) -> set:
        """Parse comma-separated excluded lead IDs into a set"""
        if not cls.EXCLUDE_LEAD_IDS:
            return set()
        return {id.strip() for id in cls.EXCLUDE_LEAD_IDS.split(",") if id.strip()}

    @classmethod
    def get_excluded_emails(cls) -> set:
        """Parse comma-separated excluded emails into a set (lowercase for comparison)"""
        if not cls.EXCLUDE_EMAILS:
            return set()
        return {email.strip().lower() for email in cls.EXCLUDE_EMAILS.split(",") if email.strip()}

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []

        if not cls.FUB_API_KEY:
            errors.append("FUB_API_KEY is required")

        if not cls.GOOGLE_SHEET_ID:
            errors.append("GOOGLE_SHEET_ID is required")

        if not Path(cls.GOOGLE_SERVICE_ACCOUNT_FILE).exists():
            errors.append(f"Google service account file not found: {cls.GOOGLE_SERVICE_ACCOUNT_FILE}")

        if cls.SMTP_ENABLED:
            if not cls.SMTP_USERNAME:
                errors.append("SMTP_USERNAME is required when SMTP is enabled")
            if not cls.SMTP_PASSWORD:
                errors.append("SMTP_PASSWORD is required when SMTP is enabled")

        if errors:
            raise RuntimeError(
                "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        return True


# =========================================================================
# LOGGING SETUP
# =========================================================================

def setup_logging() -> logging.Logger:
    """Configure comprehensive logging"""
    os.makedirs("logs", exist_ok=True)

    timestamp = datetime.now().strftime("%y%m%d.%H%M")
    log_filename = f"logs/{timestamp}.log"

    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Suppress noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)

    logger.info(f"Logging initialized → {log_filename}")
    return logger


# Initialize logger
logger = setup_logging()

cache = DataCache(CACHE_DIR)





# =========================================================================
# SCORING ENGINE
# =========================================================================

class ScoringConfig:
    """Configurable weights for lead scoring - now reads from environment"""

    # Heat Score Weights - loaded from Config
    HEAT_WEIGHTS = {
        "website_visit": Config.HEAT_WEIGHT_WEBSITE_VISIT,
        "property_viewed": Config.HEAT_WEIGHT_PROPERTY_VIEWED,
        "property_favorited": Config.HEAT_WEIGHT_PROPERTY_FAVORITED,
        "property_shared": Config.HEAT_WEIGHT_PROPERTY_SHARED,
        "call_inbound": Config.HEAT_WEIGHT_CALL_INBOUND,
        "text_inbound": Config.HEAT_WEIGHT_TEXT_INBOUND,
    }

    # Recency Bonuses (days -> bonus points) - loaded from Config
    RECENCY_TIERS = [
        (3, Config.RECENCY_BONUS_0_3_DAYS),
        (7, Config.RECENCY_BONUS_4_7_DAYS),
        (14, Config.RECENCY_BONUS_8_14_DAYS),
        (30, Config.RECENCY_BONUS_15_30_DAYS),
        (float('inf'), 0)
    ]

    # Priority Composite Weights - loaded from Config
    PRIORITY_WEIGHTS = {
        "heat": Config.PRIORITY_WEIGHT_HEAT,
        "value": Config.PRIORITY_WEIGHT_VALUE,
        "relationship": Config.PRIORITY_WEIGHT_RELATIONSHIP,
    }

    # Stage Multipliers - loaded from Config
    STAGE_MULTIPLIERS = {
        "Hot Lead": Config.STAGE_MULTIPLIER_HOT_LEAD,
        "Active Buyer": Config.STAGE_MULTIPLIER_ACTIVE_BUYER,
        "Active Seller": Config.STAGE_MULTIPLIER_ACTIVE_SELLER,
        "Nurture": Config.STAGE_MULTIPLIER_NURTURE,
        "New Lead": Config.STAGE_MULTIPLIER_NEW_LEAD,
        "Cold": Config.STAGE_MULTIPLIER_COLD,
        "Closed": Config.STAGE_MULTIPLIER_CLOSED,
        "Trash": Config.STAGE_MULTIPLIER_TRASH,
    }

class LeadScorer:
    """Enhanced lead scoring engine"""

    def __init__(self, config: ScoringConfig = None):
        self.config = config or ScoringConfig()

    def calculate_heat_score(
        self,
        website_visits_7d: int,
        properties_viewed_7d: int,
        properties_favorited: int,
        properties_shared: int,
        calls_inbound: int,
        texts_inbound: int,
        days_since_last_touch: int,
        intent_signals: Dict = None
    ) -> Tuple[float, Dict]:
        """Calculate heat score with breakdown"""
        w = self.config.HEAT_WEIGHTS

        engagement = (
            website_visits_7d * w["website_visit"]
            + properties_viewed_7d * w["property_viewed"]
            + properties_favorited * w["property_favorited"]
            + properties_shared * w["property_shared"]
            + calls_inbound * w["call_inbound"]
            + texts_inbound * w["text_inbound"]
        )

        # Recency bonus
        recency_bonus = 0
        for threshold, bonus in self.config.RECENCY_TIERS:
            if days_since_last_touch <= threshold:
                recency_bonus = bonus
                break


        # Intent multiplier
        intent_multiplier = 1.0
        intent_flags = []

        if intent_signals:
            if intent_signals.get("repeat_property_views"):
                intent_multiplier *= 1.15
                intent_flags.append("repeat_views")

            if intent_signals.get("high_favorite_count"):
                intent_multiplier *= 1.10
                intent_flags.append("high_favorites")

            if intent_signals.get("recent_activity_burst"):
                intent_multiplier *= 1.20
                intent_flags.append("activity_burst")

            if intent_signals.get("active_property_sharing"):
                intent_multiplier *= 1.05
                intent_flags.append("sharing")

        raw_score = (engagement + recency_bonus) * intent_multiplier
        final_score = max(0, min(100, round(raw_score, 1)))

        breakdown = {
            "engagement": round(engagement, 1),
            "recency_bonus": recency_bonus,
            "intent_multiplier": round(intent_multiplier, 2),
            "intent_signals": intent_flags,
            "final_score": final_score
        }

        return final_score, breakdown

    def calculate_value_score(
        self,
        avg_price_viewed: float,
        price_std_dev: float,
        max_avg_price: float
    ) -> Tuple[float, Dict]:
        """Calculate value score based on price point and consistency"""
        if avg_price_viewed <= 0 or max_avg_price <= 0:
            return 0.0, {"price_component": 0, "consistency_component": 0}

        # Price component
        price_component = (avg_price_viewed / max_avg_price) * 50.0

        # Consistency component
        cluster_confidence = 1.0 - (price_std_dev / avg_price_viewed)
        cluster_confidence = max(0.0, min(1.0, cluster_confidence))
        consistency_component = cluster_confidence * 50.0

        raw_score = price_component + consistency_component
        final_score = max(0, min(100, round(raw_score, 1)))

        breakdown = {
            "price_component": round(price_component, 1),
            "consistency_component": round(consistency_component, 1),
            "final_score": final_score
        }

        return final_score, breakdown

    def calculate_relationship_score(
        self,
        calls_inbound: int,
        calls_outbound: int,
        texts_inbound: int,
        texts_total: int,
        emails_received: int = 0,
        emails_sent: int = 0
    ) -> Tuple[float, Dict]:
        """Calculate relationship strength score including email communication"""
        # Include emails in inbound/total calculation
        inbound_contacts = calls_inbound + texts_inbound + emails_received
        total_contacts = calls_inbound + calls_outbound + texts_total + emails_received + emails_sent

        if total_contacts > 0:
            inbound_ratio = inbound_contacts / total_contacts
        else:
            inbound_ratio = 0.0

        inbound_ratio = max(0.0, min(1.0, inbound_ratio))
        ratio_component = inbound_ratio * 50.0

        # Volume component (capped)
        capped_contacts = min(inbound_contacts, 10)
        volume_component = capped_contacts * 5.0

        raw_score = ratio_component + volume_component
        final_score = max(0, min(100, round(raw_score, 1)))

        breakdown = {
            "inbound_ratio": round(inbound_ratio, 2),
            "ratio_component": round(ratio_component, 1),
            "volume_component": round(volume_component, 1),
            "emails_received": emails_received,
            "emails_sent": emails_sent,
            "final_score": final_score
        }

        return final_score, breakdown

    def calculate_priority_score(
        self,
        heat_score: float,
        value_score: float,
        relationship_score: float,
        stage: str = ""
    ) -> Tuple[float, Dict]:
        """Calculate composite priority score with stage multiplier"""
        w = self.config.PRIORITY_WEIGHTS
        stage_mult = self.config.STAGE_MULTIPLIERS.get(stage, 1.0)

        raw_score = (
            heat_score * w["heat"]
            + value_score * w["value"]
            + relationship_score * w["relationship"]
        ) * stage_mult

        final_score = max(0, min(100, round(raw_score, 1)))

        breakdown = {
            "heat_contribution": round(heat_score * w["heat"], 1),
            "value_contribution": round(value_score * w["value"], 1),
            "relationship_contribution": round(relationship_score * w["relationship"], 1),
            "stage_multiplier": stage_mult,
            "final_score": final_score
        }

        return final_score, breakdown


# =========================================================================
# DATA PROCESSING
# =========================================================================

def validate_person(person: Dict) -> bool:
    """Validate person record"""
    if not person.get("id"):
        logger.warning("Person missing ID field")
        return False
    return True


def parse_datetime_safe(dt_str: Any) -> Optional[datetime]:
    """Safely parse datetime string"""
    if not dt_str:
        return None

    if isinstance(dt_str, datetime):
        return dt_str

    try:
        # Try ISO format first
        return datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
    except Exception:
        pass

    # Try other common formats
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(str(dt_str), fmt)
        except ValueError:
            continue

    return None


def parse_date_safe(date_str: Any) -> Optional[date]:
    """Safely parse date string"""
    date_str = (date_str or "").strip()
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    logger.debug(f"Could not parse date: {date_str}")
    return None


def flatten_person_base(person: Dict) -> Dict:
    """Extract base person fields"""
    return {
        "id": person.get("id"),
        "firstName": person.get("firstName", ""),
        "lastName": person.get("lastName", ""),
        "stage": person.get("stage", ""),
        "source": person.get("source", ""),
        "leadTypeTags": ", ".join(person.get("leadTypeTags", [])) if person.get("leadTypeTags") else "",
        "created": person.get("created", ""),
        "updated": person.get("updated", ""),
        "ownerId": person.get("ownerId", ""),
        "primaryEmail": person.get("emails", [{}])[0].get("value", "") if person.get("emails") else "",
        "primaryPhone": person.get("phones", [{}])[0].get("value", "") if person.get("phones") else "",
        "company": person.get("company", ""),
        "website": person.get("website", ""),
        "lastActivity": person.get("lastActivity", ""),
    }


def build_person_stats(
    calls: List[Dict],
    texts: List[Dict],
    events: List[Dict],
    emails: List[Dict] = None
) -> Dict[str, Dict]:
    """Build per-person statistics from activities"""
    logger.info("Building person statistics...")
    emails = emails or []

    stats = defaultdict(lambda: {
        "calls_outbound": 0,
        "calls_inbound": 0,
        "texts_total": 0,
        "texts_inbound": 0,
        "emails_received": 0,
        "emails_sent": 0,
        "website_visits": 0,
        "website_visits_last_7": 0,
        "properties_viewed": 0,
        "properties_viewed_last_7": 0,
        "properties_favorited": 0,
        "properties_shared": 0,
        "last_website_visit": None,
        "avg_price_viewed": None,
        "price_view_std_dev": 0.0,
    })

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Process calls
    for call in calls:
        pid = call.get("personId")
        if not pid:
            continue

        pid = str(pid)  # Convert to string for consistency

        # FUB uses 'isIncoming' not 'direction'
        is_incoming = call.get("isIncoming")
        if is_incoming is True:
            stats[pid]["calls_inbound"] += 1
        elif is_incoming is False:
            stats[pid]["calls_outbound"] += 1

    # Process texts
    for text in texts:
        pid = text.get("personId")
        if not pid:
            continue

        stats[pid]["texts_total"] += 1

        direction = text.get("direction", "").lower()
        if direction == "inbound":
            stats[pid]["texts_inbound"] += 1

    # Process emails
    # FUB emails use relatedPeople[].personId and status field
    for email in emails:
        # Extract personId from relatedPeople array
        related_people = email.get("relatedPeople", [])
        if not related_people:
            continue

        pid = related_people[0].get("personId")
        if not pid:
            continue

        pid = str(pid)

        # FUB uses status: 'Sent' for outbound, 'Received' for inbound
        status = email.get("status", "").lower()
        if status == "received":
            stats[pid]["emails_received"] += 1
        elif status == "sent":
            stats[pid]["emails_sent"] += 1

    # Process events
    for event in events:
        pid = event.get("personId")
        if not pid:
            continue

        # Ensure pid is string for consistency
        pid = str(pid)

        # Normalize event type (FUB uses "Viewed Property" not "property_viewed")
        event_type_raw = event.get("type", "")
        event_type = event_type_raw.lower().replace(" ", "_")
        event_time = parse_datetime_safe(event.get("created"))

        if event_type == "visited_website":
            stats[pid]["website_visits"] += 1
            if event_time and event_time >= seven_days_ago:
                stats[pid]["website_visits_last_7"] += 1
            if event_time:
                if stats[pid]["last_website_visit"] is None or event_time > stats[pid]["last_website_visit"]:
                    stats[pid]["last_website_visit"] = event_time

        elif event_type == "viewed_property":
            stats[pid]["properties_viewed"] += 1
            if event_time and event_time >= seven_days_ago:
                stats[pid]["properties_viewed_last_7"] += 1

        elif event_type == "saved_property":
            stats[pid]["properties_favorited"] += 1

        elif event_type == "saved_property_search":
            stats[pid]["properties_shared"] += 1

    # Calculate average price and std dev per person
    for event in events:
        pid = event.get("personId")
        if not pid:
            continue

        pid = str(pid)
        event_type = event.get("type", "").lower().replace(" ", "_")

        if event_type != "viewed_property":
            continue

        # Extract price from property object
        property_obj = event.get("property", {})
        if isinstance(property_obj, dict):
            price = property_obj.get("price")
        else:
            price = None

        if price:
            try:
                price_val = float(price)
                # Track prices for this person
                if "price_list" not in stats[pid]:
                    stats[pid]["price_list"] = []
                stats[pid]["price_list"].append(price_val)
            except (ValueError, TypeError):
                pass

    # Compute avg and std dev
    for pid, data in stats.items():
        prices = data.get("price_list", [])
        if prices:
            avg = sum(prices) / len(prices)
            data["avg_price_viewed"] = avg

            if len(prices) > 1:
                variance = sum((p - avg) ** 2 for p in prices) / len(prices)
                data["price_view_std_dev"] = math.sqrt(variance)

        # Convert datetime to string for serialization
        if data["last_website_visit"]:
            data["last_website_visit"] = data["last_website_visit"].isoformat()

    # === INTENT SIGNAL DETECTION ===
    # Track property views for repeat detection
    property_views_by_person = defaultdict(lambda: defaultdict(int))
    activity_timestamps_by_person = defaultdict(list)

    for event in events:
        pid = event.get("personId")
        if not pid:
            continue

        event_time = parse_datetime_safe(event.get("created"))
        event_type = event.get("type", "")

        # Track property views per property
        if event_type == "viewed_property":
            property_obj = event.get("property", {})
            if isinstance(property_obj, dict):
                property_id = property_obj.get("id")
                if property_id:
                    property_views_by_person[pid][property_id] += 1

        # Track all activity timestamps for burst detection
        if event_time:
            activity_timestamps_by_person[pid].append(event_time)

    # Compute intent signals
    for pid, data in stats.items():
        # Signal 1: Repeat property views
        if pid in property_views_by_person:
            max_views = max(property_views_by_person[pid].values()) if property_views_by_person[pid] else 0
            data["repeat_property_views"] = max_views >= 2
            data["max_property_view_count"] = max_views
        else:
            data["repeat_property_views"] = False
            data["max_property_view_count"] = 0

        # Signal 2: High favorite count
        data["high_favorite_count"] = data.get("properties_favorited", 0) >= 3

        # Signal 3: Recent activity burst (3+ actions in 24 hours)
        data["recent_activity_burst"] = False
        if pid in activity_timestamps_by_person:
            timestamps = sorted(activity_timestamps_by_person[pid], reverse=True)
            if len(timestamps) >= 3:
                # Check if top 3 most recent are within 24 hours
                most_recent = timestamps[0]
                third_most_recent = timestamps[2]
                time_diff = (most_recent - third_most_recent).total_seconds() / 3600  # hours
                data["recent_activity_burst"] = time_diff <= 24

        # Signal 4: Property sharing activity
        data["active_property_sharing"] = data.get("properties_shared", 0) >= 2


    # DEBUG: Show sample stats
    if stats:
        # Show stats for person 5883 (known to have activity)
        sample_pid = "5883" if "5883" in stats else list(stats.keys())[0]
        sample_stats = stats[sample_pid]
        logger.info(f"=== DEBUG Sample stats for person {sample_pid} ===")
        logger.info(f"  website_visits: {sample_stats.get('website_visits', 0)}")
        logger.info(f"  website_visits_last_7: {sample_stats.get('website_visits_last_7', 0)}")
        logger.info(f"  properties_viewed: {sample_stats.get('properties_viewed', 0)}")
        logger.info(f"  properties_viewed_last_7: {sample_stats.get('properties_viewed_last_7', 0)}")
        logger.info(f"  properties_favorited: {sample_stats.get('properties_favorited', 0)}")
        logger.info(f"  calls_inbound: {sample_stats.get('calls_inbound', 0)}")
        logger.info(f"  calls_outbound: {sample_stats.get('calls_outbound', 0)}")
        logger.info(f"  avg_price_viewed: {sample_stats.get('avg_price_viewed', 'None')}")
        logger.info(f"=== END DEBUG ===")


    logger.info(f"✓ Built statistics for {len(stats)} people")
    return dict(stats)


def compute_daily_activity_stats(
    events: List[Dict],
    people_by_id: Dict[str, Dict]
) -> Dict:
    """Compute daily activity statistics for email reporting"""
    logger.info("Computing daily activity statistics...")

    today = datetime.now(timezone.utc).date()

    stats = {
        "total_events_today": 0,
        "website_visits_today": 0,
        "properties_viewed_today": 0,
        "unique_visitors_today": set(),
        "top_active_leads": [],
    }

    activity_by_person = defaultdict(int)

    for event in events:
        event_time = parse_datetime_safe(event.get("created"))
        if not event_time or event_time.date() != today:
            continue

        stats["total_events_today"] += 1

        # Normalize event type
        event_type_raw = event.get("type", "")
        event_type = event_type_raw.lower().replace(" ", "_")
        pid = event.get("personId")
        if pid:
            pid = str(pid)

        if event_type == "visited_website":
            stats["website_visits_today"] += 1
            if pid:
                stats["unique_visitors_today"].add(pid)

        elif event_type == "viewed_property":
            stats["properties_viewed_today"] += 1

        if pid:
            activity_by_person[pid] += 1

    # Top 5 most active today
    top_active = sorted(
        activity_by_person.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    for pid, count in top_active:
        person = people_by_id.get(str(pid), {})
        name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
        stats["top_active_leads"].append({
            "name": name or "Unknown",
            "activity_count": count
        })

    stats["unique_visitors_today"] = len(stats["unique_visitors_today"])

    logger.info(f"✓ Daily stats: {stats['total_events_today']} events, {stats['unique_visitors_today']} unique visitors")
    return stats


# =========================================================================
# GOOGLE SHEETS
# =========================================================================

# Contacts header definition
CONTACTS_HEADER = [
    "id", "firstName", "lastName", "stage", "source", "leadTypeTags",
    "created", "updated", "ownerId", "primaryEmail", "primaryPhone",
    "company", "website", "lastActivity", "last_website_visit",
    "avg_price_viewed", "website_visits", "properties_viewed",
    "properties_favorited", "properties_shared", "calls_outbound",
    "calls_inbound", "texts_total", "texts_inbound", "emails_received",
    "emails_sent", "heat_score", "value_score", "relationship_score",
    "priority_score",
    "intent_repeat_views", "intent_high_favorites", "intent_activity_burst", "intent_sharing",
    "next_action", "next_action_date"
]

def get_sheets_client():
    """Get Google Sheets client"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        creds = Credentials.from_service_account_file(
            Config.GOOGLE_SERVICE_ACCOUNT_FILE,
            scopes=scopes
        )
        return gspread.authorize(creds)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Google Sheets client: {e}")


def get_or_create_worksheet(spreadsheet, title: str):
    """Get existing worksheet or create new one"""
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        logger.info(f"Creating new worksheet: {title}")
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=50)


def write_table_to_worksheet(worksheet, header: List[str], rows: List[List]):
    """Write table data to worksheet with header"""
    if not rows:
        logger.warning(f"No rows to write to {worksheet.title}")
        return

    # Clear existing content
    worksheet.clear()

    # Write header + rows
    all_data = [header] + rows

    # Batch update for performance
    worksheet.update(all_data, value_input_option='USER_ENTERED')
    logger.info(f"✓ Wrote {len(rows)} rows to {worksheet.title}")


def should_exclude_person(person: Dict, excluded_ids: set, excluded_emails: set) -> bool:
    """
    Check if a person should be excluded based on ID or email
    
    Args:
        person: FUB person record
        excluded_ids: Set of lead IDs to exclude
        excluded_emails: Set of email addresses to exclude (lowercase)
    
    Returns:
        True if person should be excluded, False otherwise
    """
    # Check ID exclusion
    person_id = str(person.get("id", ""))
    if person_id in excluded_ids:
        return True
    
    # Check email exclusion
    emails = person.get("emails", [])
    if isinstance(emails, list):
        for email_obj in emails:
            if isinstance(email_obj, dict):
                email = email_obj.get("value", "").strip().lower()
                if email and email in excluded_emails:
                    return True
    
    return False


def build_contact_rows(
    people: List[Dict],
    person_stats: Dict[str, Dict],
    persisted_actions: Dict[str, Dict]
) -> List[List]:
    """Build contact rows with enhanced scoring"""
    logger.info(f"Building contact rows for {len(people)} people...")

    # Calculate max average price for normalization
    max_avg_price = 1.0
    for stats in person_stats.values():
        avg_price = stats.get("avg_price_viewed")
        if avg_price and avg_price > max_avg_price:
            max_avg_price = avg_price

    scorer = LeadScorer()
    rows = []
    now = datetime.now(timezone.utc)

    for i, person in enumerate(people):
        if not validate_person(person):
            continue

        base = flatten_person_base(person)
        pid = person.get("id")
        pid_str = str(pid)

        stats = person_stats.get(pid_str, {})
        saved = persisted_actions.get(pid_str, {})

        # Calculate days since last touch
        last_web_str = stats.get("last_website_visit")
        last_web = parse_datetime_safe(last_web_str)
        last_act = parse_datetime_safe(base.get("lastActivity"))
        last_touch = last_web or last_act

        if last_touch:
            days_since = (now - last_touch).days
        else:
            days_since = 365

        # Calculate scores
        # Build intent signals dict
        intent_signals = {
            "repeat_property_views": stats.get("repeat_property_views", False),
            "high_favorite_count": stats.get("high_favorite_count", False),
            "recent_activity_burst": stats.get("recent_activity_burst", False),
            "active_property_sharing": stats.get("active_property_sharing", False),
        }

        heat_score, _ = scorer.calculate_heat_score(
            website_visits_7d=int(stats.get("website_visits_last_7", 0)),
            properties_viewed_7d=int(stats.get("properties_viewed_last_7", 0)),
            properties_favorited=int(stats.get("properties_favorited", 0)),
            properties_shared=int(stats.get("properties_shared", 0)),
            calls_inbound=int(stats.get("calls_inbound", 0)),
            texts_inbound=int(stats.get("texts_inbound", 0)),
            days_since_last_touch=days_since,
            intent_signals=intent_signals
        )


        value_score, _ = scorer.calculate_value_score(
            avg_price_viewed=float(stats.get("avg_price_viewed", 0) or 0),
            price_std_dev=float(stats.get("price_view_std_dev", 0) or 0),
            max_avg_price=max_avg_price
        )

        relationship_score, _ = scorer.calculate_relationship_score(
            calls_inbound=int(stats.get("calls_inbound", 0)),
            calls_outbound=int(stats.get("calls_outbound", 0)),
            texts_inbound=int(stats.get("texts_inbound", 0)),
            texts_total=int(stats.get("texts_total", 0)),
            emails_received=int(stats.get("emails_received", 0)),
            emails_sent=int(stats.get("emails_sent", 0))
        )

        priority_score, _ = scorer.calculate_priority_score(
            heat_score=heat_score,
            value_score=value_score,
            relationship_score=relationship_score,
            stage=base.get("stage", "")
        )

        # Build row
        row = [
            base.get("id"),
            base.get("firstName"),
            base.get("lastName"),
            base.get("stage"),
            base.get("source"),
            base.get("leadTypeTags"),
            base.get("created"),
            base.get("updated"),
            base.get("ownerId"),
            base.get("primaryEmail"),
            base.get("primaryPhone"),
            base.get("company"),
            base.get("website"),
            base.get("lastActivity"),
            last_web_str,
            stats.get("avg_price_viewed"),
            stats.get("website_visits", 0),
            stats.get("properties_viewed", 0),
            stats.get("properties_favorited", 0),
            stats.get("properties_shared", 0),
            stats.get("calls_outbound", 0),
            stats.get("calls_inbound", 0),
            stats.get("texts_total", 0),
            stats.get("texts_inbound", 0),
            stats.get("emails_received", 0),
            stats.get("emails_sent", 0),
            heat_score,
            value_score,
            relationship_score,
            priority_score,
            "✓" if stats.get("repeat_property_views") else "",
            "✓" if stats.get("high_favorite_count") else "",
            "✓" if stats.get("recent_activity_burst") else "",
            "✓" if stats.get("active_property_sharing") else "",
            saved.get("next_action", ""),
            saved.get("next_action_date", ""),
        ]

        rows.append(row)

        if (i + 1) % 100 == 0:
            logger.info(f"  Processed {i + 1}/{len(people)} contacts")

    logger.info(f"✓ Built {len(rows)} contact rows")
    return rows


def build_top_n_by_column(
    contact_rows: List[List],
    column_name: str,
    n: int = 20
) -> List[List]:
    """Sort and return top N rows by column value"""
    try:
        idx = CONTACTS_HEADER.index(column_name)
    except ValueError:
        logger.error(f"Column {column_name} not found in header")
        return []

    usable = []
    for row in contact_rows:
        val = row[idx]
        if val in (None, "", "None"):
            continue
        try:
            num = float(val)
            usable.append((num, row))
        except (TypeError, ValueError):
            continue

    usable.sort(key=lambda t: t[0], reverse=True)
    top = [r for _, r in usable[:n]]

    logger.info(f"Built top {n} by {column_name}: {len(top)} rows")
    return top


def build_call_list_rows(
    contact_rows: List[List],
    max_rows: int = None
) -> List[List]:

    """Build daily call list"""

    if max_rows is None:
        max_rows = Config.CALL_LIST_MAX_ROWS

    logger.info("Building call list...")

    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}

    prio_i = idx["priority_score"]
    stage_i = idx["stage"]
    action_i = idx["next_action"]
    date_i = idx["next_action_date"]

    today = date.today()
    candidates = []

    for row in contact_rows:
        # Stage filter
        stage = (row[stage_i] or "").strip()
        if stage in ("Closed", "Trash"):
            continue

        # Priority filter
        try:
            prio = float(row[prio_i] or 0)
        except (ValueError, TypeError):
            prio = 0.0

        if prio < Config.CALL_LIST_MIN_PRIORITY:
            continue

        # Next action filter
        action = (row[action_i] or "").strip()
        if action and action.lower() != "call":
            continue

        # Date filter
        date_str = (row[date_i] or "").strip()
        due = parse_date_safe(date_str)
        if due and due > today:
            continue

        # Sort key
        overdue_rank = 1
        due_sort = 99999999
        if due:
            overdue_rank = 0
            due_sort = due.toordinal()

        candidates.append((prio, overdue_rank, due_sort, row))

    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
    result = [t[3] for t in candidates[:max_rows]]

    logger.info(f"✓ Built call list: {len(result)} contacts")
    return result


def format_contacts_sheet(spreadsheet, worksheet, num_data_rows: int):
    """Apply formatting to contacts sheet"""
    try:
        worksheet.freeze(rows=1)
        logger.debug("Froze header row")
    except Exception as e:
        logger.warning(f"Could not freeze header: {e}")

    try:
        worksheet.set_basic_filter()
        logger.debug("Applied basic filter")
    except Exception as e:
        logger.warning(f"Could not set filter: {e}")


def reorder_worksheets(spreadsheet):
    """Reorder worksheets with main tabs first, backups last"""
    logger.info("Reordering worksheets...")

    worksheets = spreadsheet.worksheets()

    main_order = [
        "Contacts",
        "Call List Today",
        "Top Priority 20",
        "Top Value 20",
        "Top Heat 20",
    ]

    def is_backup(title):
        if len(title) != 11 or "." not in title:
            return False
        try:
            datetime.strptime(title, "%y%m%d.%H%M")
            return True
        except ValueError:
            return False

    main_tabs = []
    backup_tabs = []
    other_tabs = []

    for ws in worksheets:
        if ws.title in main_order:
            main_tabs.append(ws)
        elif is_backup(ws.title):
            backup_tabs.append(ws)
        else:
            other_tabs.append(ws)

    # Sort main tabs by desired order
    main_sorted = []
    for title in main_order:
        for ws in main_tabs:
            if ws.title == title:
                main_sorted.append(ws)

    backup_sorted = sorted(backup_tabs, key=lambda w: w.title)
    new_order = main_sorted + other_tabs + backup_sorted

    if new_order and new_order != worksheets:
        try:
            spreadsheet.reorder_worksheets(new_order)
            logger.info("✓ Worksheets reordered")
        except Exception as e:
            logger.warning(f"Could not reorder worksheets: {e}")


# =========================================================================
# EMAIL REPORTING
# =========================================================================

def get_property_changes_for_email() -> Dict[str, Any]:
    """Get property changes from the last 24 hours for email report."""
    try:
        from src.core.database import DREAMSDatabase
        db = DREAMSDatabase(Config.DREAMS_DB_PATH)
        return db.get_change_summary(hours=24)
    except Exception as e:
        logger.warning(f"Could not get property changes: {e}")
        return {
            'total_changes': 0,
            'price_increases': [],
            'price_decreases': [],
            'status_changes': []
        }


def send_top_priority_email(
    contact_rows: List[List],
    top_priority_rows: List[List],
    daily_stats: Dict
):
    """Send email report with top priority contacts"""
    if not Config.SMTP_ENABLED:
        logger.info("SMTP disabled, skipping email")
        return

    logger.info("Preparing email report...")

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    # Get property changes for the report
    property_changes = get_property_changes_for_email()

    # Build email content
    subject = f"{Config.EMAIL_SUBJECT_PREFIX} Top Priority List - {datetime.now().strftime('%Y-%m-%d')}"

    body_lines = [
        "<html><body style='font-family: Arial, sans-serif;'>",
        f"<h2>Daily FUB Brief - {datetime.now().strftime('%B %d, %Y')}</h2>",
        "",
        "<h3>📊 Today's Activity</h3>",
        "<ul>",
        f"<li>Total Events: <strong>{daily_stats.get('total_events_today', 0)}</strong></li>",
        f"<li>Website Visits: <strong>{daily_stats.get('website_visits_today', 0)}</strong></li>",
        f"<li>Properties Viewed: <strong>{daily_stats.get('properties_viewed_today', 0)}</strong></li>",
        f"<li>Unique Visitors: <strong>{daily_stats.get('unique_visitors_today', 0)}</strong></li>",
        "</ul>",
        "",
    ]

    # Add property changes section if there are any
    if property_changes.get('total_changes', 0) > 0:
        body_lines.extend([
            "<h3>🏠 Property Changes (Last 24h)</h3>",
            "<div style='margin-bottom: 20px;'>",
        ])

        # Price decreases (reductions - most important)
        if property_changes.get('price_decreases'):
            body_lines.append("<p><strong>💰 Price Reductions:</strong></p>")
            body_lines.append("<ul>")
            for change in property_changes['price_decreases'][:5]:
                address = change.get('property_address', 'Unknown')
                old_val = change.get('old_value', '?')
                new_val = change.get('new_value', '?')
                amount = change.get('change_amount', 0)
                amount_str = f"-${abs(amount):,.0f}" if amount else ""
                body_lines.append(
                    f"<li><strong>{address}</strong>: {old_val} → {new_val} ({amount_str})</li>"
                )
            body_lines.append("</ul>")

        # Price increases
        if property_changes.get('price_increases'):
            body_lines.append("<p><strong>📈 Price Increases:</strong></p>")
            body_lines.append("<ul>")
            for change in property_changes['price_increases'][:5]:
                address = change.get('property_address', 'Unknown')
                old_val = change.get('old_value', '?')
                new_val = change.get('new_value', '?')
                amount = change.get('change_amount', 0)
                amount_str = f"+${abs(amount):,.0f}" if amount else ""
                body_lines.append(
                    f"<li><strong>{address}</strong>: {old_val} → {new_val} ({amount_str})</li>"
                )
            body_lines.append("</ul>")

        # Status changes
        if property_changes.get('status_changes'):
            body_lines.append("<p><strong>🏷️ Status Changes:</strong></p>")
            body_lines.append("<ul>")
            for change in property_changes['status_changes'][:5]:
                address = change.get('property_address', 'Unknown')
                old_val = change.get('old_value', '?')
                new_val = change.get('new_value', '?')
                body_lines.append(
                    f"<li><strong>{address}</strong>: {old_val} → {new_val}</li>"
                )
            body_lines.append("</ul>")

        body_lines.append("</div>")

    # Top active leads today
    if daily_stats.get('top_active_leads'):
        body_lines.extend([
            "<h3>🔥 Most Active Today</h3>",
            "<ol>",
        ])
        for lead in daily_stats['top_active_leads']:
            body_lines.append(f"<li>{lead['name']} - {lead['activity_count']} activities</li>")
        body_lines.append("</ol>")

    # Top priority contacts
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}

    body_lines.extend([
        "",
        f"<h3>⭐ Top {len(top_priority_rows)} Priority Contacts</h3>",
        "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse: collapse; width: 100%;'>",
        "<tr style='background-color: #4CAF50; color: white;'>",
        "<th>Name</th>",
        "<th>Stage</th>",
        "<th>Priority Score</th>",
        "<th>Heat</th>",
        "<th>Value</th>",
        "<th>Phone</th>",
        "</tr>",
    ])

    for row in top_priority_rows[:20]:
        name = f"{row[idx['firstName']]} {row[idx['lastName']]}".strip()
        stage = row[idx['stage']] or ""
        priority = row[idx['priority_score']] or 0
        heat = row[idx['heat_score']] or 0
        value = row[idx['value_score']] or 0
        phone = row[idx['primaryPhone']] or ""

        body_lines.append(
            f"<tr>"
            f"<td>{name}</td>"
            f"<td>{stage}</td>"
            f"<td style='text-align: center;'><strong>{priority}</strong></td>"
            f"<td style='text-align: center;'>{heat}</td>"
            f"<td style='text-align: center;'>{value}</td>"
            f"<td>{phone}</td>"
            f"</tr>"
        )

    body_lines.extend([
        "</table>",
        "",
        "<p style='margin-top: 30px; color: #666;'>",
        "This automated report was generated by your FUB to Sheets integration.",
        "</p>",
        "</body></html>",
    ])

    html_body = "\n".join(body_lines)

    # Send email
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"EUG Morning FUB Brief <{Config.SMTP_USERNAME}>"
        msg["To"] = Config.EMAIL_TO

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"✓ Email sent to {Config.EMAIL_TO}")

    except Exception as e:
        logger.error(f"Failed to send email: {e}")


# =========================================================================
# SQLITE DATABASE SYNC
# =========================================================================

def sync_communications_to_sqlite(
    calls: List[Dict],
    texts: List[Dict],
    db
) -> Tuple[int, int]:
    """
    Sync individual communication records to SQLite.

    Args:
        calls: List of call records from FUB
        texts: List of text records from FUB
        db: DREAMSDatabase instance

    Returns:
        Tuple of (calls_synced, texts_synced)
    """
    import uuid

    calls_synced = 0
    texts_synced = 0

    # Process calls
    for call in calls:
        try:
            fub_id = call.get("id")
            person_id = call.get("personId")
            if not person_id:
                continue

            person_id = str(person_id)

            # Determine direction
            is_incoming = call.get("isIncoming")
            direction = "inbound" if is_incoming else "outbound"

            # Create unique ID for this call
            comm_id = f"call_{fub_id}" if fub_id else f"call_{uuid.uuid4()}"

            # Get timestamp
            occurred_at = call.get("created") or call.get("timestamp")

            # Get duration
            duration = call.get("duration") or call.get("durationSeconds")

            # Get agent name
            agent_name = None
            user = call.get("user")
            if isinstance(user, dict):
                agent_name = user.get("name")

            # Get status
            status = call.get("outcome") or call.get("status") or "completed"

            if db.insert_communication(
                comm_id=comm_id,
                contact_id=person_id,
                comm_type="call",
                direction=direction,
                occurred_at=occurred_at,
                duration_seconds=duration,
                fub_id=str(fub_id) if fub_id else None,
                fub_user_name=agent_name,
                status=status
            ):
                calls_synced += 1

        except Exception as e:
            logger.debug(f"Error syncing call: {e}")

    # Process texts
    for text in texts:
        try:
            fub_id = text.get("id")
            person_id = text.get("personId")
            if not person_id:
                continue

            person_id = str(person_id)

            # Determine direction
            direction = text.get("direction", "").lower()
            if direction not in ("inbound", "outbound"):
                direction = "outbound"  # Default

            # Create unique ID for this text
            comm_id = f"text_{fub_id}" if fub_id else f"text_{uuid.uuid4()}"

            # Get timestamp
            occurred_at = text.get("created") or text.get("timestamp")

            # Get agent name
            agent_name = None
            user = text.get("user")
            if isinstance(user, dict):
                agent_name = user.get("name")

            if db.insert_communication(
                comm_id=comm_id,
                contact_id=person_id,
                comm_type="text",
                direction=direction,
                occurred_at=occurred_at,
                fub_id=str(fub_id) if fub_id else None,
                fub_user_name=agent_name,
                status="delivered"
            ):
                texts_synced += 1

        except Exception as e:
            logger.debug(f"Error syncing text: {e}")

    logger.info(f"✓ Communications synced: {calls_synced} calls, {texts_synced} texts")
    return calls_synced, texts_synced


def sync_events_to_sqlite(
    events: List[Dict],
    db
) -> int:
    """
    Sync individual event records to SQLite.

    Args:
        events: List of event records from FUB
        db: DREAMSDatabase instance

    Returns:
        Number of events synced
    """
    import uuid

    events_synced = 0

    # Map FUB event types to our normalized types
    event_type_map = {
        "visited_website": "website_visit",
        "viewed_property": "property_view",
        "saved_property": "property_favorite",
        "saved_property_search": "property_share",
    }

    for event in events:
        try:
            fub_event_id = event.get("id")
            person_id = event.get("personId")
            if not person_id:
                continue

            person_id = str(person_id)

            # Normalize event type
            event_type_raw = event.get("type", "")
            event_type_normalized = event_type_raw.lower().replace(" ", "_")
            event_type = event_type_map.get(event_type_normalized)

            # Skip unknown event types
            if not event_type:
                continue

            # Create unique ID for this event
            event_id = f"evt_{fub_event_id}" if fub_event_id else f"evt_{uuid.uuid4()}"

            # Get timestamp
            occurred_at = event.get("created")

            # Get property details if available
            property_address = None
            property_price = None
            property_mls = None

            property_obj = event.get("property", {})
            if isinstance(property_obj, dict):
                property_address = property_obj.get("address") or property_obj.get("streetAddress")
                property_price = property_obj.get("price")
                property_mls = property_obj.get("mlsNumber") or property_obj.get("id")

                # Try to get price as int
                if property_price:
                    try:
                        property_price = int(float(property_price))
                    except (ValueError, TypeError):
                        property_price = None

            if db.insert_event(
                event_id=event_id,
                contact_id=person_id,
                event_type=event_type,
                occurred_at=occurred_at,
                property_address=property_address,
                property_price=property_price,
                property_mls=str(property_mls) if property_mls else None,
                fub_event_id=str(fub_event_id) if fub_event_id else None
            ):
                events_synced += 1

        except Exception as e:
            logger.debug(f"Error syncing event: {e}")

    logger.info(f"✓ Events synced: {events_synced} events")
    return events_synced


def sync_scoring_history_to_sqlite(
    contact_rows: List[List],
    person_stats: Dict[str, Dict],
    db,
    sync_id: Optional[int] = None
) -> int:
    """
    Sync scoring history snapshots to SQLite (once per day per contact).

    Args:
        contact_rows: List of contact rows with scores
        person_stats: Dictionary of person stats keyed by person ID
        db: DREAMSDatabase instance
        sync_id: Optional sync log ID

    Returns:
        Number of scoring history records created
    """
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}
    scores_recorded = 0

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            stats = person_stats.get(fub_id, {})

            # Calculate intent signal count
            intent_count = sum([
                1 if row[idx["intent_repeat_views"]] == "✓" else 0,
                1 if row[idx["intent_high_favorites"]] == "✓" else 0,
                1 if row[idx["intent_activity_burst"]] == "✓" else 0,
                1 if row[idx["intent_sharing"]] == "✓" else 0,
            ])

            result = db.insert_scoring_history(
                contact_id=fub_id,
                heat_score=float(row[idx["heat_score"]] or 0),
                value_score=float(row[idx["value_score"]] or 0),
                relationship_score=float(row[idx["relationship_score"]] or 0),
                priority_score=float(row[idx["priority_score"]] or 0),
                website_visits=int(row[idx["website_visits"]] or 0),
                properties_viewed=int(row[idx["properties_viewed"]] or 0),
                calls_inbound=int(row[idx["calls_inbound"]] or 0),
                calls_outbound=int(row[idx["calls_outbound"]] or 0),
                texts_total=int(row[idx["texts_total"]] or 0),
                intent_signal_count=intent_count,
                sync_id=sync_id
            )

            if result is not None:  # None means skipped (already recorded today)
                scores_recorded += 1

        except Exception as e:
            logger.debug(f"Error recording scoring history: {e}")

    logger.info(f"✓ Scoring history: {scores_recorded} records created")
    return scores_recorded


def sync_to_sqlite(contact_rows: List[List], person_stats: Dict[str, Dict]):
    """
    Sync contacts to SQLite database for unified DREAMS dashboard.

    Args:
        contact_rows: List of contact rows (same format as Google Sheets)
        person_stats: Dictionary of person stats keyed by person ID
    """
    if not Config.SQLITE_SYNC_ENABLED:
        logger.info("SQLite sync disabled, skipping")
        return

    logger.info("Syncing contacts to SQLite database...")

    try:
        from src.core.database import DREAMSDatabase
        db = DREAMSDatabase(Config.DREAMS_DB_PATH)
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")
        return

    # Map sheet columns to database columns
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}

    success_count = 0
    error_count = 0

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            # Get person stats for this contact
            stats = person_stats.get(fub_id, {})

            # Build contact dict for database
            contact_data = {
                "id": fub_id,  # Use FUB ID as primary key
                "fub_id": fub_id,
                "external_id": fub_id,
                "external_source": "followupboss",
                "first_name": row[idx["firstName"]] or None,
                "last_name": row[idx["lastName"]] or None,
                "email": row[idx["primaryEmail"]] or None,
                "phone": row[idx["primaryPhone"]] or None,
                "stage": row[idx["stage"]] or None,
                "source": row[idx["source"]] or None,
                "lead_type_tags": row[idx["leadTypeTags"]] or None,
                # Scoring fields
                "heat_score": float(row[idx["heat_score"]] or 0),
                "value_score": float(row[idx["value_score"]] or 0),
                "relationship_score": float(row[idx["relationship_score"]] or 0),
                "priority_score": float(row[idx["priority_score"]] or 0),
                # Activity stats
                "website_visits": int(row[idx["website_visits"]] or 0),
                "properties_viewed": int(row[idx["properties_viewed"]] or 0),
                "properties_favorited": int(row[idx["properties_favorited"]] or 0),
                "calls_inbound": int(row[idx["calls_inbound"]] or 0),
                "calls_outbound": int(row[idx["calls_outbound"]] or 0),
                "texts_total": int(row[idx["texts_total"]] or 0),
                "emails_received": int(row[idx["emails_received"]] or 0),
                "emails_sent": int(row[idx["emails_sent"]] or 0),
                "avg_price_viewed": float(row[idx["avg_price_viewed"]]) if row[idx["avg_price_viewed"]] else None,
                "last_activity_at": row[idx["lastActivity"]] or None,
                # Intent signals
                "intent_repeat_views": 1 if row[idx["intent_repeat_views"]] == "✓" else 0,
                "intent_high_favorites": 1 if row[idx["intent_high_favorites"]] == "✓" else 0,
                "intent_activity_burst": 1 if row[idx["intent_activity_burst"]] == "✓" else 0,
                "intent_sharing": 1 if row[idx["intent_sharing"]] == "✓" else 0,
                "intent_signal_count": sum([
                    1 if row[idx["intent_repeat_views"]] == "✓" else 0,
                    1 if row[idx["intent_high_favorites"]] == "✓" else 0,
                    1 if row[idx["intent_activity_burst"]] == "✓" else 0,
                    1 if row[idx["intent_sharing"]] == "✓" else 0,
                ]),
                # Action tracking
                "next_action": row[idx["next_action"]] or None,
                "next_action_date": row[idx["next_action_date"]] or None,
            }

            # Calculate days since activity
            last_activity = row[idx["lastActivity"]]
            if last_activity:
                try:
                    last_act_dt = parse_datetime_safe(last_activity)
                    if last_act_dt:
                        days = (datetime.now(timezone.utc) - last_act_dt).days
                        contact_data["days_since_activity"] = days
                except Exception:
                    pass

            db.upsert_contact_dict(contact_data)
            success_count += 1

        except Exception as e:
            error_count += 1
            logger.debug(f"Error syncing contact: {e}")

    logger.info(f"✓ SQLite sync complete: {success_count} synced, {error_count} errors")


# =========================================================================
# MAIN EXECUTION
# =========================================================================

def main():
    """Main execution function"""
    start_time = time.time()

    try:
        logger.info("=" * 70)
        logger.info("FUB TO SHEETS v2.0 - Starting sync")
        logger.info("=" * 70)

        # Validate configuration
        Config.validate()
        logger.info("✓ Configuration validated")

        cache = DataCache(cache_dir=CACHE_DIR)


        # Initialize FUB client
        fub = FUBClient(
            api_key=Config.FUB_API_KEY,
            base_url=Config.FUB_BASE_URL,
            request_sleep_seconds=Config.REQUEST_SLEEP_SECONDS,
            default_fetch_limit=Config.DEFAULT_FETCH_LIMIT,
            max_parallel_workers=Config.MAX_PARALLEL_WORKERS,
            enable_stage_sync=Config.ENABLE_STAGE_SYNC,
            cache=cache,
            logger=logger,
        )

        # Fetch data from FUB
        people = fub.fetch_people()
        
        # Apply exclusion filters
        excluded_ids = Config.get_excluded_ids()
        excluded_emails = Config.get_excluded_emails()
        
        if excluded_ids or excluded_emails:
            original_count = len(people)
            people = [p for p in people if not should_exclude_person(p, excluded_ids, excluded_emails)]
            excluded_count = original_count - len(people)
            
            logger.info("Applied exclusion filters:")
            if excluded_ids:
                logger.info(f"  - Excluded IDs: {len(excluded_ids)} configured")
            if excluded_emails:
                logger.info(f"  - Excluded emails: {len(excluded_emails)} configured")
            logger.info(f"  - Filtered out: {excluded_count} contacts")
            logger.info(f"  - Remaining: {len(people)} contacts")
        else:
            logger.info("No exclusion filters configured")
        
        calls = fub.fetch_calls()
        texts = fub.fetch_text_messages_parallel(people)
        emails = fub.fetch_emails_parallel(people)
        events = fub.fetch_events()

        # Build lookups
        people_by_id = {str(p.get("id")): p for p in people if p.get("id")}

        # Compute statistics
        daily_stats = compute_daily_activity_stats(events, people_by_id)
        person_stats = build_person_stats(calls, texts, events, emails)

        # Initialize Google Sheets
        logger.info("Connecting to Google Sheets...")
        gc = get_sheets_client()
        sh = gc.open_by_key(Config.GOOGLE_SHEET_ID)
        logger.info(f"✓ Connected to sheet: {sh.title}")

        # Read persisted actions from existing Contacts sheet
        persisted_actions = {}
        try:
            existing_ws = sh.worksheet("Contacts")
            existing_values = existing_ws.get_all_values()
            if existing_values:
                header = existing_values[0]
                try:
                    id_idx = header.index("id")
                    action_idx = header.index("next_action")
                    date_idx = header.index("next_action_date")

                    for row in existing_values[1:]:
                        if id_idx < len(row):
                            pid = row[id_idx]
                            if pid:
                                rec = {}
                                if action_idx < len(row):
                                    rec["next_action"] = row[action_idx]
                                if date_idx < len(row):
                                    rec["next_action_date"] = row[date_idx]
                                if rec:
                                    persisted_actions[str(pid)] = rec

                    logger.info(f"✓ Loaded {len(persisted_actions)} persisted actions")
                except ValueError:
                    logger.warning("Could not find action columns in existing sheet")
        except gspread.exceptions.WorksheetNotFound:
            logger.info("No existing Contacts sheet found")

        # Build contact rows
        contact_rows = build_contact_rows(people, person_stats, persisted_actions)

        # Create backup with timestamp
        backup_name = datetime.now().strftime("%y%m%d.%H%M")
        logger.info(f"Creating backup: {backup_name}")
        backup_ws = sh.add_worksheet(
            title=backup_name,
            rows=len(contact_rows) + 1,
            cols=len(CONTACTS_HEADER)
        )
        write_table_to_worksheet(backup_ws, CONTACTS_HEADER, contact_rows)

        # Update main Contacts sheet
        contacts_ws = get_or_create_worksheet(sh, "Contacts")
        write_table_to_worksheet(contacts_ws, CONTACTS_HEADER, contact_rows)
        format_contacts_sheet(sh, contacts_ws, len(contact_rows))

        # Build and write call list
        call_list_rows = build_call_list_rows(contact_rows)
        call_list_ws = get_or_create_worksheet(sh, "Call List Today")
        write_table_to_worksheet(call_list_ws, CONTACTS_HEADER, call_list_rows)

        # Build and write top lists
        top_priority = build_top_n_by_column(contact_rows, "priority_score", n=20)
        top_priority_ws = get_or_create_worksheet(sh, "Top Priority 20")
        write_table_to_worksheet(top_priority_ws, CONTACTS_HEADER, top_priority)

        top_value = build_top_n_by_column(contact_rows, "value_score", n=20)
        top_value_ws = get_or_create_worksheet(sh, "Top Value 20")
        write_table_to_worksheet(top_value_ws, CONTACTS_HEADER, top_value)

        top_heat = build_top_n_by_column(contact_rows, "heat_score", n=20)
        top_heat_ws = get_or_create_worksheet(sh, "Top Heat 20")
        write_table_to_worksheet(top_heat_ws, CONTACTS_HEADER, top_heat)

        # Reorder worksheets
        reorder_worksheets(sh)

        # Send email report
        send_top_priority_email(contact_rows, top_priority, daily_stats)

        # Sync to SQLite database (for unified DREAMS dashboard)
        sync_to_sqlite(contact_rows, person_stats)

        # Enhanced FUB data sync: individual records and scoring history
        if Config.SQLITE_SYNC_ENABLED:
            try:
                from src.core.database import DREAMSDatabase
                db = DREAMSDatabase(Config.DREAMS_DB_PATH)

                # Sync individual communications (calls/texts)
                sync_communications_to_sqlite(calls, texts, db)

                # Sync individual events
                sync_events_to_sqlite(events, db)

                # Sync scoring history (once per day per contact)
                sync_scoring_history_to_sqlite(contact_rows, person_stats, db)

            except Exception as e:
                logger.error(f"Enhanced FUB data sync failed: {e}")

        # Summary
        elapsed = time.time() - start_time
        logger.info("=" * 70)
        logger.info("SYNC COMPLETED SUCCESSFULLY")
        logger.info(f"  Total contacts: {len(contact_rows)}")
        logger.info(f"  Call list: {len(call_list_rows)} contacts")
        logger.info(f"  Top priority: {len(top_priority)} contacts")
        logger.info(f"  Runtime: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Process interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error("=" * 70)
        logger.error("FATAL ERROR")
        logger.error("=" * 70)
        logger.error(str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
