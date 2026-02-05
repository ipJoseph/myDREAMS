
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
from typing import Dict, List, Optional, Set, Tuple, Any
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
import re


def normalize_phone(phone: str) -> Optional[str]:
    """
    Normalize phone number to 10 digits for database storage.

    Args:
        phone: Raw phone number in any format

    Returns:
        10-digit string or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)

    # Remove leading 1 if 11 digits
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]

    # Must be exactly 10 digits
    if len(digits) != 10:
        return None

    # First digit can't be 0 or 1 (not valid US area codes)
    if digits[0] in ('0', '1'):
        return None

    return digits


def format_phone_display(phone: str) -> str:
    """
    Format phone number for display as (XXX) XXX-XXXX.

    Args:
        phone: 10-digit phone number

    Returns:
        Formatted string or original if not 10 digits
    """
    if not phone:
        return ''

    # Remove any non-digits first
    digits = re.sub(r'\D', '', phone)

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    return phone


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

    # Scoring Weights - Inactivity Decay Multipliers
    # These reduce scores for leads that have gone quiet
    DECAY_MULTIPLIER_0_7_DAYS = float(os.getenv("DECAY_MULTIPLIER_0_7_DAYS", "1.0"))      # No decay
    DECAY_MULTIPLIER_8_14_DAYS = float(os.getenv("DECAY_MULTIPLIER_8_14_DAYS", "0.95"))   # 5% decay
    DECAY_MULTIPLIER_15_30_DAYS = float(os.getenv("DECAY_MULTIPLIER_15_30_DAYS", "0.85")) # 15% decay
    DECAY_MULTIPLIER_31_60_DAYS = float(os.getenv("DECAY_MULTIPLIER_31_60_DAYS", "0.70")) # 30% decay
    DECAY_MULTIPLIER_61_90_DAYS = float(os.getenv("DECAY_MULTIPLIER_61_90_DAYS", "0.50")) # 50% decay
    DECAY_MULTIPLIER_90_PLUS_DAYS = float(os.getenv("DECAY_MULTIPLIER_90_PLUS_DAYS", "0.30")) # 70% decay

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

    @classmethod
    def get_scoring_config_snapshot(cls) -> dict:
        """Get a snapshot of all scoring configuration for audit trail."""
        return {
            "heat_weights": {
                "website_visit": cls.HEAT_WEIGHT_WEBSITE_VISIT,
                "property_viewed": cls.HEAT_WEIGHT_PROPERTY_VIEWED,
                "property_favorited": cls.HEAT_WEIGHT_PROPERTY_FAVORITED,
                "property_shared": cls.HEAT_WEIGHT_PROPERTY_SHARED,
                "call_inbound": cls.HEAT_WEIGHT_CALL_INBOUND,
                "text_inbound": cls.HEAT_WEIGHT_TEXT_INBOUND,
            },
            "recency_bonuses": {
                "0_3_days": cls.RECENCY_BONUS_0_3_DAYS,
                "4_7_days": cls.RECENCY_BONUS_4_7_DAYS,
                "8_14_days": cls.RECENCY_BONUS_8_14_DAYS,
                "15_30_days": cls.RECENCY_BONUS_15_30_DAYS,
            },
            "decay_multipliers": {
                "0_7_days": cls.DECAY_MULTIPLIER_0_7_DAYS,
                "8_14_days": cls.DECAY_MULTIPLIER_8_14_DAYS,
                "15_30_days": cls.DECAY_MULTIPLIER_15_30_DAYS,
                "31_60_days": cls.DECAY_MULTIPLIER_31_60_DAYS,
                "61_90_days": cls.DECAY_MULTIPLIER_61_90_DAYS,
                "90_plus_days": cls.DECAY_MULTIPLIER_90_PLUS_DAYS,
            },
            "priority_weights": {
                "heat": cls.PRIORITY_WEIGHT_HEAT,
                "value": cls.PRIORITY_WEIGHT_VALUE,
                "relationship": cls.PRIORITY_WEIGHT_RELATIONSHIP,
            },
            "stage_multipliers": {
                "hot_lead": cls.STAGE_MULTIPLIER_HOT_LEAD,
                "active_buyer": cls.STAGE_MULTIPLIER_ACTIVE_BUYER,
                "active_seller": cls.STAGE_MULTIPLIER_ACTIVE_SELLER,
                "nurture": cls.STAGE_MULTIPLIER_NURTURE,
                "new_lead": cls.STAGE_MULTIPLIER_NEW_LEAD,
                "cold": cls.STAGE_MULTIPLIER_COLD,
                "closed": cls.STAGE_MULTIPLIER_CLOSED,
                "trash": cls.STAGE_MULTIPLIER_TRASH,
            },
            "call_list": {
                "min_priority": cls.CALL_LIST_MIN_PRIORITY,
                "max_rows": cls.CALL_LIST_MAX_ROWS,
            }
        }


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

    # Inactivity Decay (days -> multiplier) - loaded from Config
    # Reduces scores for leads that have gone quiet
    DECAY_TIERS = [
        (7, Config.DECAY_MULTIPLIER_0_7_DAYS),      # 0-7 days: no decay
        (14, Config.DECAY_MULTIPLIER_8_14_DAYS),    # 8-14 days: 5% decay
        (30, Config.DECAY_MULTIPLIER_15_30_DAYS),   # 15-30 days: 15% decay
        (60, Config.DECAY_MULTIPLIER_31_60_DAYS),   # 31-60 days: 30% decay
        (90, Config.DECAY_MULTIPLIER_61_90_DAYS),   # 61-90 days: 50% decay
        (float('inf'), Config.DECAY_MULTIPLIER_90_PLUS_DAYS)  # 90+ days: 70% decay
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

        # Inactivity decay - reduces scores for leads that have gone quiet
        decay_multiplier = 1.0
        for threshold, multiplier in self.config.DECAY_TIERS:
            if days_since_last_touch <= threshold:
                decay_multiplier = multiplier
                break

        raw_score = (engagement + recency_bonus) * intent_multiplier * decay_multiplier
        final_score = max(0, min(100, round(raw_score, 1)))

        breakdown = {
            "engagement": round(engagement, 1),
            "recency_bonus": recency_bonus,
            "intent_multiplier": round(intent_multiplier, 2),
            "intent_signals": intent_flags,
            "decay_multiplier": round(decay_multiplier, 2),
            "days_inactive": days_since_last_touch,
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
        # FUB API uses 'assignedUserId', not 'ownerId' - map to ownerId for compatibility
        "ownerId": person.get("assignedUserId") or person.get("ownerId", ""),
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
    emails: List[Dict] = None,
    excluded_pids: Set[str] = None
) -> Dict[str, Dict]:
    """Build per-person statistics from activities.

    Args:
        excluded_pids: Person IDs to exclude from IDX event counting.
            These people's website visits, property views, favorites, and
            shares will NOT be counted. Calls/texts/emails are still counted
            since those are real interactions, not cookie-based attribution.
    """
    logger.info("Building person statistics...")
    emails = emails or []
    excluded_pids = excluded_pids or set()
    excluded_event_count = 0

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

    # Process events (with scoring guard: skip excluded people)
    for event in events:
        pid = event.get("personId")
        if not pid:
            continue

        # Ensure pid is string for consistency
        pid = str(pid)

        # Guard: Skip IDX events from excluded people (stale cookie prevention)
        if pid in excluded_pids:
            excluded_event_count += 1
            continue

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

        # Guard: Skip excluded people
        if pid in excluded_pids:
            continue

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

        # Guard: Skip excluded people
        if str(pid) in excluded_pids:
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


    if excluded_event_count > 0:
        logger.info(
            f"⛔ Excluded {excluded_event_count} events from "
            f"{len(excluded_pids)} filtered people in person stats"
        )
    logger.info(f"✓ Built statistics for {len(stats)} people")
    return dict(stats)


def compute_daily_activity_stats(
    events: List[Dict],
    people_by_id: Dict[str, Dict],
    excluded_pids: Set[str] = None,
    person_stats: Dict[str, Dict] = None
) -> Dict:
    """Compute daily activity statistics for email reporting.

    Includes scoring guards to prevent false attribution from stale cookies.
    Events from excluded person IDs (stage/tag filter) are skipped entirely.
    After counting, anomaly detection flags high-activity people with zero
    inbound communication as suspicious (likely stale cookie attribution).
    """
    logger.info("Computing daily activity statistics...")
    excluded_pids = excluded_pids or set()

    today = datetime.now(timezone.utc).date()

    stats = {
        "total_events_today": 0,
        "website_visits_today": 0,
        "properties_viewed_today": 0,
        "unique_visitors_today": set(),
        "top_active_leads": [],
        "excluded_event_count": 0,
        "suspicious_pids": set(),
        "excluded_pids": excluded_pids,
    }

    activity_by_person = defaultdict(int)

    for event in events:
        event_time = parse_datetime_safe(event.get("created"))
        if not event_time or event_time.date() != today:
            continue

        pid = event.get("personId")
        if pid:
            pid = str(pid)

        # Guard: Skip events from excluded people (stage/tag filter)
        if pid and pid in excluded_pids:
            stats["excluded_event_count"] += 1
            continue

        stats["total_events_today"] += 1

        # Normalize event type
        event_type_raw = event.get("type", "")
        event_type = event_type_raw.lower().replace(" ", "_")

        if event_type == "visited_website":
            stats["website_visits_today"] += 1
            if pid:
                stats["unique_visitors_today"].add(pid)

        elif event_type == "viewed_property":
            stats["properties_viewed_today"] += 1

        if pid:
            activity_by_person[pid] += 1

    # Guard: Anomaly detection - flag suspicious attribution patterns
    suspicious_pids = set()
    if person_stats:
        suspicious_pids, suspicious_reasons = detect_suspicious_attribution(
            activity_by_person, people_by_id, person_stats
        )
        stats["suspicious_pids"] = suspicious_pids

    # Combine all filtered person IDs
    all_filtered = excluded_pids | suspicious_pids

    # Top 5 most active today (excluding filtered people)
    filtered_activity = {
        pid: count for pid, count in activity_by_person.items()
        if pid not in all_filtered
    }
    top_active = sorted(
        filtered_activity.items(),
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

    stats["unique_visitors_today"] = len(stats["unique_visitors_today"] - all_filtered)

    if stats["excluded_event_count"] > 0:
        logger.info(
            f"⛔ Excluded {stats['excluded_event_count']} events from "
            f"{len(excluded_pids)} filtered people"
        )

    # Get new contacts from the last 3 days (from SQLite)
    try:
        from src.core.database import DREAMSDatabase
        db = DREAMSDatabase(Config.DREAMS_DB_PATH)
        new_contacts = db.get_recent_contacts(days=3)
        stats["new_contacts"] = new_contacts
        logger.info(f"✓ Found {len(new_contacts)} new contacts in last 3 days")

        # Get recently reassigned leads (leads lost in last 7 days)
        my_user_id = int(os.getenv('FUB_MY_USER_ID', 8))
        reassigned_leads = db.get_recently_reassigned_leads(
            from_user_id=my_user_id,
            days=7,
            limit=20
        )
        stats["reassigned_leads"] = reassigned_leads
        if reassigned_leads:
            logger.info(f"⚠️  Found {len(reassigned_leads)} leads reassigned in last 7 days")
    except Exception as e:
        logger.warning(f"Could not fetch new contacts: {e}")
        stats["new_contacts"] = []
        stats["reassigned_leads"] = []

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


# === SCORING GUARDS: False Attribution Prevention ===
# Prevents stale RealGeeks cookies from inflating scores for opted-out contacts.
# See: Barbara O'Hara incident (2026-02-04) - 30 false events from stale cookie.

# Stages whose IDX events should not count toward scoring
SCORING_EXCLUDED_STAGES = {"Trash"}

# Tags that indicate the person should be excluded from event-based scoring
SCORING_EXCLUDED_TAGS = {"unsubscribed", "dnc", "do not contact", "do not call"}

# Minimum events/day to trigger anomaly detection
ACTIVITY_SPIKE_THRESHOLD = 15


def build_scoring_exclusions(
    people_by_id: Dict[str, Dict]
) -> Tuple[Set[str], Dict[str, str]]:
    """
    Build set of person IDs whose IDX events should be excluded from scoring.

    Catches opted-out contacts, DNC contacts, and trashed leads whose stale
    browser cookies may still generate false activity via RealGeeks/IDX.

    Returns:
        (excluded_ids, reasons) - set of excluded person IDs and reason mapping
    """
    excluded = set()
    reasons = {}

    for pid, person in people_by_id.items():
        # Guard 1: Stage exclusion
        stage = (person.get("stage") or "").strip()
        if stage in SCORING_EXCLUDED_STAGES:
            name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
            excluded.add(pid)
            reasons[pid] = f"excluded_stage:{stage}"
            logger.info(f"  Excluding {name or pid}: stage={stage}")
            continue

        # Guard 2: Tag exclusion (case-insensitive)
        tags = person.get("tags") or []
        tag_names = set()
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, str):
                    tag_names.add(t.strip().lower())
                elif isinstance(t, dict):
                    tag_names.add((t.get("name", "") or "").strip().lower())
        elif isinstance(tags, str):
            tag_names = {t.strip().lower() for t in tags.split(",")}

        matched = tag_names & SCORING_EXCLUDED_TAGS
        if matched:
            name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
            excluded.add(pid)
            reasons[pid] = f"excluded_tags:{','.join(matched)}"
            logger.info(f"  Excluding {name or pid}: tags={','.join(matched)}")
            continue

    if excluded:
        logger.info(f"⛔ Scoring exclusions: {len(excluded)} people excluded by stage/tags")
    else:
        logger.info("✓ No scoring exclusions from stage/tags")

    return excluded, reasons


def detect_suspicious_attribution(
    activity_by_person: Dict[str, int],
    people_by_id: Dict[str, Dict],
    person_stats: Dict[str, Dict],
    threshold: int = ACTIVITY_SPIKE_THRESHOLD
) -> Tuple[Set[str], Dict[str, str]]:
    """
    Detect anomalous activity patterns suggesting false cookie-based attribution.

    Flags people who have high event counts but ZERO inbound communication,
    which indicates stale RealGeeks cookie attribution rather than genuine
    engagement. Example: Barbara O'Hara had 30 property views in one day
    attributed via stale cookie, despite having opted out a month prior.

    Args:
        activity_by_person: {pid: event_count} for today
        people_by_id: FUB person records
        person_stats: Per-person communication stats from build_person_stats
        threshold: Minimum events/day to trigger anomaly check

    Returns:
        (suspicious_ids, reasons)
    """
    suspicious = set()
    reasons = {}

    for pid, count in activity_by_person.items():
        if count < threshold:
            continue

        # Check for ANY inbound communication (calls, texts, emails)
        stats = person_stats.get(pid, {})
        has_inbound = (
            stats.get("calls_inbound", 0) > 0
            or stats.get("texts_inbound", 0) > 0
            or stats.get("emails_received", 0) > 0
        )

        if not has_inbound:
            person = people_by_id.get(pid, {})
            name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
            stage = person.get("stage", "")
            suspicious.add(pid)
            reasons[pid] = (
                f"anomaly:{count}_events_zero_inbound_communication"
            )
            logger.warning(
                f"⚠️ SUSPICIOUS ATTRIBUTION: {name or pid} (stage={stage}) "
                f"has {count} events today with zero inbound communication - "
                f"likely stale cookie attribution"
            )

    if suspicious:
        logger.warning(
            f"⚠️ {len(suspicious)} people flagged for suspicious activity attribution"
        )

    return suspicious, reasons


def detect_ghost_activity(
    person_stats: Dict[str, Dict],
    people_by_id: Dict[str, Dict],
    min_views: int = 15
) -> Tuple[Set[str], Dict[str, str]]:
    """
    Detect 'ghost' activity: high property views across the full event window
    with ZERO inbound communication. This catches stale cookie attribution
    that the daily anomaly check misses (e.g., events spread across multiple days).

    Unlike detect_suspicious_attribution (which checks one day), this examines
    the full person_stats accumulated from all fetched events.

    Args:
        person_stats: Per-person stats from build_person_stats (all events)
        people_by_id: FUB person records
        min_views: Minimum total property views to trigger the check

    Returns:
        (ghost_ids, reasons)
    """
    ghosts = set()
    reasons = {}

    for pid, stats in person_stats.items():
        total_views = stats.get("properties_viewed", 0) + stats.get("website_visits", 0)
        if total_views < min_views:
            continue

        # Check for ANY inbound communication
        has_inbound = (
            stats.get("calls_inbound", 0) > 0
            or stats.get("texts_inbound", 0) > 0
            or stats.get("emails_received", 0) > 0
        )

        if not has_inbound:
            person = people_by_id.get(pid, {})
            name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
            stage = person.get("stage", "")
            ghosts.add(pid)
            reasons[pid] = (
                f"ghost_activity:{total_views}_views_zero_inbound"
            )
            logger.warning(
                f"⚠️ GHOST ACTIVITY: {name or pid} (stage={stage}) "
                f"has {total_views} views/visits with zero inbound communication - "
                f"likely stale cookie, not genuine engagement"
            )

    if ghosts:
        logger.warning(
            f"⚠️ {len(ghosts)} people flagged as ghost activity (high views, zero communication)"
        )

    return ghosts, reasons


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

    # New contacts in the last 3 days
    if daily_stats.get('new_contacts'):
        body_lines.extend([
            "<h3>🆕 New Contacts (Last 3 Days)</h3>",
            "<ul style='list-style: none; padding-left: 0;'>",
        ])
        for contact in daily_stats['new_contacts']:
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or "Unknown"
            days_ago = contact.get('days_ago', 0)
            source = contact.get('source', '')
            source_str = f" <span style='color: #666; font-size: 12px;'>({source})</span>" if source else ""

            # Format the time indicator
            if days_ago == 0:
                time_str = "<strong style='color: #10b981;'>Today</strong>"
            elif days_ago == 1:
                time_str = "<span style='color: #3b82f6;'>Yesterday</span>"
            else:
                time_str = f"<span style='color: #6b7280;'>{days_ago} days ago</span>"

            body_lines.append(f"<li style='padding: 4px 0;'>{name} - {time_str}{source_str}</li>")
        body_lines.append("</ul>")

    # Reassigned leads (leads lost via round-robin or transfer)
    if daily_stats.get('reassigned_leads'):
        body_lines.extend([
            "<h3>⚠️ Leads Reassigned (Last 7 Days)</h3>",
            "<p style='color: #666; font-size: 13px; margin-bottom: 10px;'>These leads were reassigned away from you (round-robin timeout or transfer):</p>",
            "<ul style='list-style: none; padding-left: 0;'>",
        ])
        for lead in daily_stats['reassigned_leads']:
            name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Unknown"
            reason = lead.get('reassigned_reason', 'unknown')
            reassigned_at = lead.get('reassigned_at', '')

            # Format the reassignment date
            if reassigned_at:
                try:
                    dt = parse_datetime_safe(reassigned_at)
                    if dt:
                        days_ago = (datetime.now(timezone.utc) - dt).days
                        if days_ago == 0:
                            time_str = "<strong style='color: #ef4444;'>Today</strong>"
                        elif days_ago == 1:
                            time_str = "<span style='color: #f97316;'>Yesterday</span>"
                        else:
                            time_str = f"<span style='color: #6b7280;'>{days_ago} days ago</span>"
                    else:
                        time_str = ""
                except Exception:
                    time_str = ""
            else:
                time_str = ""

            reason_str = f" <span style='color: #666; font-size: 12px;'>({reason})</span>" if reason else ""
            body_lines.append(f"<li style='padding: 4px 0; color: #dc2626;'>{name} - {time_str}{reason_str}</li>")
        body_lines.append("</ul>")

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
        phone = format_phone_display(row[idx['primaryPhone']] or "")

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
    db,
    excluded_pids: Set[str] = None
) -> int:
    """
    Sync individual event records to SQLite.

    Args:
        events: List of event records from FUB
        db: DREAMSDatabase instance
        excluded_pids: Person IDs to skip (excluded by scoring guards)

    Returns:
        Number of events synced
    """
    import uuid

    events_synced = 0
    events_excluded = 0
    excluded_pids = excluded_pids or set()

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

            # Guard: Skip events from excluded people (false attribution prevention)
            if person_id in excluded_pids:
                events_excluded += 1
                continue

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

    if events_excluded > 0:
        logger.info(
            f"⛔ Skipped {events_excluded} events from "
            f"{len(excluded_pids)} excluded people"
        )
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


def sync_to_sqlite(contact_rows: List[List], person_stats: Dict[str, Dict], user_lookup: Dict[int, str] = None):
    """
    Sync contacts to SQLite database for unified DREAMS dashboard.

    Args:
        contact_rows: List of contact rows (same format as Google Sheets)
        person_stats: Dictionary of person stats keyed by person ID
        user_lookup: Dictionary mapping FUB user IDs to user names (for assignment tracking)
    """
    if not Config.SQLITE_SYNC_ENABLED:
        logger.info("SQLite sync disabled, skipping")
        return

    logger.info("Syncing contacts to SQLite database...")
    user_lookup = user_lookup or {}

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
    assignment_changes = 0

    # Track FUB IDs assigned to the current user for reassignment detection
    my_user_id = int(os.getenv('FUB_MY_USER_ID', 8))
    current_user_fub_ids = set()  # FUB IDs currently assigned to my_user_id

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            # Get person stats for this contact
            stats = person_stats.get(fub_id, {})

            # Get owner/assignment info
            owner_id = row[idx["ownerId"]]
            owner_id_int = int(owner_id) if owner_id else None
            owner_name = user_lookup.get(owner_id_int) if owner_id_int else None

            # Build contact dict for database
            contact_data = {
                "id": fub_id,  # Use FUB ID as primary key
                "fub_id": fub_id,
                "external_id": fub_id,
                "external_source": "followupboss",
                "first_name": row[idx["firstName"]] or None,
                "last_name": row[idx["lastName"]] or None,
                "email": row[idx["primaryEmail"]] or None,
                "phone": normalize_phone(row[idx["primaryPhone"]]),
                "stage": row[idx["stage"]] or None,
                "source": row[idx["source"]] or None,
                "lead_type_tags": row[idx["leadTypeTags"]] or None,
                # Assignment fields
                "assigned_user_id": owner_id_int,
                "assigned_user_name": owner_name,
                # Scoring fields
                "heat_score": float(row[idx["heat_score"]] or 0),
                "value_score": float(row[idx["value_score"]] or 0),
                "relationship_score": float(row[idx["relationship_score"]] or 0),
                "priority_score": float(row[idx["priority_score"]] or 0),
                # Activity stats
                "website_visits": int(row[idx["website_visits"]] or 0),
                "properties_viewed": int(row[idx["properties_viewed"]] or 0),
                "properties_favorited": int(row[idx["properties_favorited"]] or 0),
                "properties_shared": int(row[idx["properties_shared"]] or 0),
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

            # Track assignment changes (after upsert to ensure contact exists)
            if owner_id_int and owner_name:
                changed = db.update_contact_assignment(
                    contact_id=fub_id,
                    new_user_id=owner_id_int,
                    new_user_name=owner_name,
                    source='sync'
                )
                if changed:
                    assignment_changes += 1

                # Track if this contact is assigned to the current user
                if owner_id_int == my_user_id:
                    current_user_fub_ids.add(str(fub_id))

        except Exception as e:
            error_count += 1
            logger.debug(f"Error syncing contact: {e}")

    # Detect reassigned leads (leads that were assigned to user but no longer are)
    reassigned_count = 0
    try:
        reassigned_leads = db.detect_reassigned_leads(my_user_id, current_user_fub_ids)
        if reassigned_leads:
            lead_ids = [lead['id'] for lead in reassigned_leads]
            reassigned_count = db.mark_leads_as_reassigned(
                lead_ids=lead_ids,
                from_user_id=my_user_id,
                reason='round_robin'  # Most likely reason for automatic reassignment
            )
            logger.info(f"⚠️  Detected {reassigned_count} leads reassigned away from user {my_user_id}")

            # Log the names for visibility
            for lead in reassigned_leads[:5]:  # Show up to 5
                name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                logger.info(f"   - {name} (ID: {lead.get('fub_id') or lead.get('id')})")
            if len(reassigned_leads) > 5:
                logger.info(f"   ... and {len(reassigned_leads) - 5} more")
    except Exception as e:
        logger.error(f"Error detecting reassigned leads: {e}")

    logger.info(f"✓ SQLite sync complete: {success_count} synced, {error_count} errors, {assignment_changes} assignment changes, {reassigned_count} reassigned")


def evaluate_contact_trends(db, contact_rows: List[List]) -> Dict[str, str]:
    """
    Evaluate trends for all contacts by comparing current scores to historical averages.

    Args:
        db: DREAMSDatabase instance
        contact_rows: List of contact rows with current scores

    Returns:
        Dict mapping contact_id to trend direction ('warming', 'cooling', 'stable')
    """
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}
    trends = {}
    trend_alerts = []

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            current_heat = float(row[idx["heat_score"]] or 0)
            current_priority = float(row[idx["priority_score"]] or 0)

            # Get 7-day average from scoring history
            history = db.get_scoring_history(fub_id, days=7)

            if len(history) >= 2:
                # Calculate average excluding most recent (which might be today)
                past_scores = history[1:] if len(history) > 1 else history
                avg_heat = sum(h.get('heat_score', 0) for h in past_scores) / len(past_scores)
                avg_priority = sum(h.get('priority_score', 0) for h in past_scores) / len(past_scores)

                # Determine trend based on heat score change
                heat_delta = current_heat - avg_heat
                heat_pct_change = (heat_delta / avg_heat * 100) if avg_heat > 0 else 0

                if heat_pct_change >= 15:  # 15% increase = warming
                    trends[fub_id] = 'warming'
                    # Alert for significant warming
                    if heat_delta >= 20:
                        name = f"{row[idx['firstName']] or ''} {row[idx['lastName']] or ''}".strip()
                        trend_alerts.append({
                            'contact_id': fub_id,
                            'name': name,
                            'type': 'warming',
                            'delta': heat_delta,
                            'current': current_heat,
                            'avg': avg_heat
                        })
                elif heat_pct_change <= -15:  # 15% decrease = cooling
                    trends[fub_id] = 'cooling'
                    # Alert for significant cooling of high-value contacts
                    if heat_delta <= -20 and current_priority >= 60:
                        name = f"{row[idx['firstName']] or ''} {row[idx['lastName']] or ''}".strip()
                        trend_alerts.append({
                            'contact_id': fub_id,
                            'name': name,
                            'type': 'cooling',
                            'delta': heat_delta,
                            'current': current_heat,
                            'avg': avg_heat
                        })
                else:
                    trends[fub_id] = 'stable'
            else:
                # Not enough history, mark as stable
                trends[fub_id] = 'stable'

        except Exception as e:
            logger.debug(f"Error evaluating trend for {fub_id}: {e}")

    # Log trend summary
    warming_count = sum(1 for t in trends.values() if t == 'warming')
    cooling_count = sum(1 for t in trends.values() if t == 'cooling')
    stable_count = sum(1 for t in trends.values() if t == 'stable')

    logger.info(f"✓ Trend evaluation: {warming_count} warming, {cooling_count} cooling, {stable_count} stable")

    if trend_alerts:
        logger.info(f"  Trend alerts ({len(trend_alerts)} significant changes):")
        for alert in trend_alerts[:5]:  # Show top 5
            direction = "↑" if alert['type'] == 'warming' else "↓"
            logger.info(f"    {direction} {alert['name']}: heat {alert['avg']:.0f} → {alert['current']:.0f} ({alert['delta']:+.0f})")

    return trends


def update_contact_trends_in_db(db, trends: Dict[str, str]):
    """
    Update the score_trend field in leads table for all contacts.

    Args:
        db: DREAMSDatabase instance
        trends: Dict mapping contact_id to trend direction
    """
    with db._get_connection() as conn:
        for contact_id, trend in trends.items():
            try:
                conn.execute(
                    'UPDATE leads SET score_trend = ?, updated_at = ? WHERE id = ?',
                    (trend, datetime.now(timezone.utc).isoformat(), contact_id)
                )
            except Exception as e:
                logger.debug(f"Error updating trend for {contact_id}: {e}")
        conn.commit()

    logger.info(f"✓ Updated score_trend for {len(trends)} contacts")


def populate_daily_activity(db, contact_rows: List[List]):
    """
    Populate contact_daily_activity table with today's aggregated activity.

    Args:
        db: DREAMSDatabase instance
        contact_rows: List of contact rows with current scores
    """
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}
    today = datetime.now().strftime('%Y-%m-%d')
    records_created = 0

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            # Get today's activity from events/communications
            activity = db.aggregate_daily_activity_from_events(fub_id, today)

            # Skip if no activity today
            total_activity = sum(activity.values())
            if total_activity == 0:
                continue

            # Record with current scores as snapshot
            db.record_daily_activity(
                contact_id=fub_id,
                activity_date=today,
                website_visits=activity['website_visits'],
                properties_viewed=activity['properties_viewed'],
                properties_favorited=activity['properties_favorited'],
                properties_shared=activity['properties_shared'],
                calls_inbound=activity['calls_inbound'],
                calls_outbound=activity['calls_outbound'],
                texts_inbound=activity['texts_inbound'],
                texts_outbound=activity['texts_outbound'],
                emails_received=activity['emails_received'],
                emails_sent=activity['emails_sent'],
                heat_score=float(row[idx["heat_score"]] or 0),
                value_score=float(row[idx["value_score"]] or 0),
                relationship_score=float(row[idx["relationship_score"]] or 0),
                priority_score=float(row[idx["priority_score"]] or 0)
            )
            records_created += 1

        except Exception as e:
            logger.debug(f"Error recording daily activity for {fub_id}: {e}")

    logger.info(f"✓ Daily activity: {records_created} contact-day records for {today}")


def migrate_next_actions_to_contact_actions(db, contact_rows: List[List]):
    """
    Migrate any existing next_action/next_action_date from leads table
    to the new contact_actions table (one-time migration).

    Only creates actions for contacts that don't already have pending actions.

    Args:
        db: DREAMSDatabase instance
        contact_rows: List of contact rows
    """
    idx = {name: i for i, name in enumerate(CONTACTS_HEADER)}
    migrated = 0

    # Get contacts with existing pending actions
    existing_actions = db.get_action_counts_by_contact()

    for row in contact_rows:
        try:
            fub_id = str(row[idx["id"]]) if row[idx["id"]] else None
            if not fub_id:
                continue

            # Skip if already has pending actions
            if existing_actions.get(fub_id, 0) > 0:
                continue

            next_action = row[idx["next_action"]] if row[idx["next_action"]] else None
            next_action_date = row[idx["next_action_date"]] if row[idx["next_action_date"]] else None

            # Skip if no action to migrate
            if not next_action:
                continue

            # Determine action type from description
            action_lower = next_action.lower()
            if 'call' in action_lower:
                action_type = 'call'
            elif 'email' in action_lower or 'send' in action_lower:
                action_type = 'email'
            elif 'text' in action_lower or 'sms' in action_lower:
                action_type = 'text'
            elif 'meeting' in action_lower or 'showing' in action_lower:
                action_type = 'meeting'
            else:
                action_type = 'follow_up'

            db.add_contact_action(
                contact_id=fub_id,
                action_type=action_type,
                description=next_action,
                due_date=next_action_date,
                priority=3,
                created_by='migration'
            )
            migrated += 1

        except Exception as e:
            logger.debug(f"Error migrating action for {fub_id}: {e}")

    if migrated > 0:
        logger.info(f"✓ Migrated {migrated} next_action entries to contact_actions table")


# =========================================================================
# MAIN EXECUTION
# =========================================================================

def main():
    """Main execution function"""
    start_time = time.time()
    scoring_run_id = None
    db = None
    fub_api_calls = 0

    try:
        logger.info("=" * 70)
        logger.info("FUB TO SHEETS v2.0 - Starting sync")
        logger.info("=" * 70)

        # Validate configuration
        Config.validate()
        logger.info("✓ Configuration validated")

        # Initialize database and start scoring run (for audit trail)
        if Config.SQLITE_SYNC_ENABLED:
            try:
                from src.core.database import DREAMSDatabase
                db = DREAMSDatabase(Config.DREAMS_DB_PATH)
                scoring_run_id = db.start_scoring_run(
                    source='scheduled',
                    config_snapshot=Config.get_scoring_config_snapshot()
                )
                logger.info(f"✓ Started scoring run #{scoring_run_id}")
            except Exception as e:
                logger.warning(f"Could not start scoring run tracking: {e}")

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

        # Fetch users and build lookup for assignment tracking
        users = fub.fetch_users()
        user_lookup = {u['id']: u['name'] for u in users if u.get('id') and u.get('name')}
        logger.info(f"✓ Fetched {len(users)} team members")

        # Sync users to database cache
        if db:
            try:
                db.sync_fub_users(users)
            except Exception as e:
                logger.warning(f"Could not sync FUB users to database: {e}")

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

        # === SCORING GUARDS ===
        # Guard 1 & 2: Build exclusion set from stage and tags
        # Prevents stale cookies from inflating scores for opted-out/DNC contacts
        scoring_excluded_pids, exclusion_reasons = build_scoring_exclusions(people_by_id)

        # Compute statistics (order matters: person_stats needed for anomaly detection)
        person_stats = build_person_stats(
            calls, texts, events, emails,
            excluded_pids=scoring_excluded_pids
        )

        # Guard 3: Ghost activity detection across full event window
        # Catches people with high views but zero communication (like Barbara O'Hara)
        ghost_pids, ghost_reasons = detect_ghost_activity(
            person_stats, people_by_id
        )

        # Guard 4: Daily anomaly detection (inside compute_daily_activity_stats)
        # Flags single-day spikes with zero inbound communication
        daily_stats = compute_daily_activity_stats(
            events, people_by_id,
            excluded_pids=scoring_excluded_pids | ghost_pids,
            person_stats=person_stats
        )

        # Combine all filtered person IDs
        suspicious_pids = daily_stats.get("suspicious_pids", set()) | ghost_pids
        all_filtered_pids = scoring_excluded_pids | suspicious_pids

        # Guard: Zero out event-based stats for suspicious people
        # Their events were counted in build_person_stats (before anomaly detection),
        # so we need to neutralize them to prevent inflated heat scores.
        if suspicious_pids:
            for pid in suspicious_pids:
                if pid in person_stats:
                    person = people_by_id.get(pid, {})
                    name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
                    logger.info(
                        f"  Zeroing event stats for {name or pid} (suspicious attribution)"
                    )
                    person_stats[pid]["website_visits"] = 0
                    person_stats[pid]["website_visits_last_7"] = 0
                    person_stats[pid]["properties_viewed"] = 0
                    person_stats[pid]["properties_viewed_last_7"] = 0
                    person_stats[pid]["properties_favorited"] = 0
                    person_stats[pid]["properties_shared"] = 0
                    person_stats[pid]["repeat_property_views"] = False
                    person_stats[pid]["recent_activity_burst"] = False
                    person_stats[pid]["high_favorite_count"] = False
                    person_stats[pid]["active_property_sharing"] = False

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
        sync_to_sqlite(contact_rows, person_stats, user_lookup)

        # Enhanced FUB data sync: individual records, scoring, trends, and daily activity
        contacts_new = 0
        contacts_updated = len(contact_rows)

        if Config.SQLITE_SYNC_ENABLED:
            try:
                # Ensure db is initialized
                if db is None:
                    from src.core.database import DREAMSDatabase
                    db = DREAMSDatabase(Config.DREAMS_DB_PATH)

                # Sync individual communications (calls/texts)
                sync_communications_to_sqlite(calls, texts, db)

                # Sync individual events (with scoring guard exclusions)
                sync_events_to_sqlite(events, db, excluded_pids=all_filtered_pids)

                # Sync scoring history (once per day per contact)
                sync_scoring_history_to_sqlite(contact_rows, person_stats, db)

                # === NEW: Trend Evaluation ===
                # Compare current scores to historical averages
                trends = evaluate_contact_trends(db, contact_rows)
                update_contact_trends_in_db(db, trends)

                # === NEW: Daily Activity Aggregation ===
                # Populate contact_daily_activity table for today
                populate_daily_activity(db, contact_rows)

                # === NEW: Migrate next_action to contact_actions (one-time) ===
                # This preserves user-created actions across syncs
                migrate_next_actions_to_contact_actions(db, contact_rows)

            except Exception as e:
                logger.error(f"Enhanced FUB data sync failed: {e}")

        # Complete scoring run with final stats
        if scoring_run_id and db:
            try:
                db.complete_scoring_run(
                    run_id=scoring_run_id,
                    contacts_processed=len(people),
                    contacts_scored=len(contact_rows),
                    contacts_new=contacts_new,
                    contacts_updated=contacts_updated,
                    fub_api_calls=fub_api_calls,
                    status='success'
                )
                logger.info(f"✓ Completed scoring run #{scoring_run_id}")
            except Exception as e:
                logger.warning(f"Could not complete scoring run tracking: {e}")

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
        # Mark scoring run as failed if interrupted
        if scoring_run_id and db:
            try:
                db.complete_scoring_run(
                    run_id=scoring_run_id,
                    status='failed',
                    error_message='Process interrupted by user'
                )
            except Exception:
                pass
        sys.exit(1)

    except Exception as e:
        logger.error("=" * 70)
        logger.error("FATAL ERROR")
        logger.error("=" * 70)
        logger.error(str(e), exc_info=True)
        # Mark scoring run as failed
        if scoring_run_id and db:
            try:
                db.complete_scoring_run(
                    run_id=scoring_run_id,
                    status='failed',
                    error_message=str(e)
                )
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
