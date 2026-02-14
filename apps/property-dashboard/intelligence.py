"""
Intelligence Briefing Engine for Mission Control

Generates one-sentence intelligence briefings for contacts based on
activity data, scoring trends, and relationship signals. Each briefing
includes a category, urgency level, and suggested conversation opener.

Rule chain is prioritized (first match wins):
1. Activity Burst   — 3+ property views in 24h
2. New Lead         — Created < 24h ago
3. Warming Trend    — score_trend=warming, heat_delta > 10
4. Going Cold       — 14+ days since last contact, value >= 40
5. Follow-Up Due    — Pending action due today
6. High Intent      — 2+ intent signals
7. Needs Properties — Has intake form, no recent packages
8. Default          — Generic prospect summary
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Urgency levels for sorting within mission groups
URGENCY_ACT_NOW = 'act_now'
URGENCY_FOLLOW_UP = 'follow_up'
URGENCY_TOUCH_BASE = 'touch_base'

# Conversation openers by category
OPENERS = {
    'activity_burst': "I noticed you've been looking at some great properties in {area}. Anything catching your eye?",
    'new_lead': "Welcome! I saw you were checking out some properties on our site. What are you looking for?",
    'warming': "Good to see you back! Has anything changed in your search since we last talked?",
    'going_cold': "Just checking in — still thinking about real estate in the area?",
    'follow_up_due': "Following up on our last conversation. Any updates on your end?",
    'high_intent': "You've been doing a lot of research lately. Are you getting closer to making a move?",
    'needs_properties': "I've been putting together some listings that match what you're looking for. When's a good time to go over them?",
    'default': "Touching base — how's your property search going?",
}


def generate_briefing(contact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an intelligence briefing for a single contact.

    Args:
        contact: Enriched contact dict from get_morning_briefing_contacts().
            Expected fields: first_name, last_name, heat_score, value_score,
            priority_score, days_since_activity, score_trend, heat_delta,
            property_views_24h, property_views_7d, favorites_7d,
            last_comm_at, pending_action_due, has_intake, created_at,
            intent_signal_count, recent_cities, price_range_label, source

    Returns:
        Dict with keys: text, category, urgency, opener, sort_key
    """
    # Run rules in priority order — first match wins
    rules = [
        _rule_activity_burst,
        _rule_new_lead,
        _rule_warming_trend,
        _rule_going_cold,
        _rule_follow_up_due,
        _rule_high_intent,
        _rule_needs_properties,
        _rule_default,
    ]

    for rule in rules:
        result = rule(contact)
        if result:
            return result

    # Should never reach here (_rule_default always matches)
    return _rule_default(contact)


def generate_briefings(contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate briefings for a list of contacts and return them
    sorted into urgency groups.

    Returns list of contacts with 'briefing' key added.
    """
    for contact in contacts:
        contact['briefing'] = generate_briefing(contact)

    # Sort: act_now first, then follow_up, then touch_base
    # Within each group, sort by sort_key (higher = more urgent)
    urgency_order = {URGENCY_ACT_NOW: 0, URGENCY_FOLLOW_UP: 1, URGENCY_TOUCH_BASE: 2}
    contacts.sort(key=lambda c: (
        urgency_order.get(c['briefing']['urgency'], 3),
        -c['briefing']['sort_key']
    ))

    return contacts


def group_by_urgency(contacts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group briefed contacts into urgency buckets.
    Contacts must already have 'briefing' key from generate_briefings().
    """
    groups = {
        URGENCY_ACT_NOW: [],
        URGENCY_FOLLOW_UP: [],
        URGENCY_TOUCH_BASE: [],
    }

    for contact in contacts:
        urgency = contact.get('briefing', {}).get('urgency', URGENCY_TOUCH_BASE)
        groups.get(urgency, groups[URGENCY_TOUCH_BASE]).append(contact)

    return groups


# ─── Rule functions ───────────────────────────────────────────────

def _rule_activity_burst(contact: Dict) -> Optional[Dict]:
    """3+ property views in the last 24 hours."""
    views_24h = contact.get('property_views_24h', 0) or 0
    if views_24h < 3:
        return None

    area = _format_area(contact)
    extra = ""
    if contact.get('financing_status') == 'cash':
        extra = " Cash buyer."
    elif contact.get('financing_status') == 'pre_approved':
        extra = f" Pre-approved."

    text = f"Activity burst: {views_24h} property views yesterday"
    if area:
        text += f" in {area}"
    text += f".{extra}"

    return {
        'text': text,
        'category': 'activity_burst',
        'urgency': URGENCY_ACT_NOW,
        'opener': OPENERS['activity_burst'].format(area=area or 'the area'),
        'sort_key': views_24h * 100 + (contact.get('heat_score') or 0),
    }


def _rule_new_lead(contact: Dict) -> Optional[Dict]:
    """Lead created less than 24 hours ago."""
    created_at = contact.get('created_at')
    if not created_at:
        return None

    try:
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        # Handle timezone-naive comparison
        if created.tzinfo:
            created = created.replace(tzinfo=None)
        age = datetime.now() - created
    except (ValueError, TypeError):
        return None

    if age > timedelta(hours=24):
        return None

    hours_ago = max(1, int(age.total_seconds() / 3600))
    source = contact.get('source') or 'website'
    views = contact.get('properties_viewed', 0) or 0

    text = f"New lead {hours_ago}h ago from {source}."
    if views > 0:
        text += f" Viewed {views} properties."

    return {
        'text': text,
        'category': 'new_lead',
        'urgency': URGENCY_ACT_NOW,
        'opener': OPENERS['new_lead'],
        'sort_key': 1000 - hours_ago,  # More recent = higher priority
    }


def _rule_warming_trend(contact: Dict) -> Optional[Dict]:
    """Score trend is warming and heat delta > 10 points."""
    trend = contact.get('score_trend')
    delta = contact.get('heat_delta') or 0

    if trend != 'warming' or delta < 10:
        return None

    views_7d = contact.get('property_views_7d', 0) or 0
    quiet_period = ""

    days_since = contact.get('days_since_activity')
    if days_since and days_since > 30:
        months = days_since // 30
        quiet_period = f" after {months}mo quiet"

    text = f"Warming up: Heat jumped {int(delta)}pts this week."
    if views_7d > 0:
        text += f" {views_7d} property views{quiet_period}."

    return {
        'text': text,
        'category': 'warming',
        'urgency': URGENCY_FOLLOW_UP,
        'opener': OPENERS['warming'],
        'sort_key': delta * 10 + (contact.get('priority_score') or 0),
    }


def _rule_going_cold(contact: Dict) -> Optional[Dict]:
    """14+ days since last contact, value score >= 30."""
    # Use days_since_last_comm if available, otherwise fall back to days_since_activity
    days_since = contact.get('days_since_last_comm')
    if days_since is None:
        days_since = contact.get('days_since_activity')
    if not days_since or days_since < 14:
        return None

    value = contact.get('value_score') or 0
    if value < 30:
        return None

    price_label = contact.get('price_range_label') or ''
    area = _format_area(contact)

    text = f"Going cold: Last contact {days_since}d ago."
    if price_label and area:
        text += f" Was viewing {price_label} homes in {area}."
    elif price_label:
        text += f" Was viewing {price_label} homes."
    elif area:
        text += f" Was searching in {area}."

    return {
        'text': text,
        'category': 'going_cold',
        'urgency': URGENCY_FOLLOW_UP,
        'opener': OPENERS['going_cold'],
        'sort_key': value + (100 - min(days_since, 100)),  # Higher value, fewer days = more urgent
    }


def _rule_follow_up_due(contact: Dict) -> Optional[Dict]:
    """Has a pending action due today or overdue."""
    due = contact.get('pending_action_due')
    if not due:
        return None

    try:
        due_date = datetime.strptime(due, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None

    if due_date > datetime.now().date():
        return None

    action_desc = contact.get('pending_action_desc') or 'Follow-up'
    area = _format_area(contact)
    extras = []

    if contact.get('financing_status') == 'pre_approved':
        amount = contact.get('pre_approval_amount')
        if amount:
            extras.append(f"Pre-approved ${amount:,}")
    if area:
        extras.append(f"wants {area}")

    text = f"{action_desc} due today."
    if extras:
        text += f" {'. '.join(extras)}."

    return {
        'text': text,
        'category': 'follow_up_due',
        'urgency': URGENCY_FOLLOW_UP,
        'opener': OPENERS['follow_up_due'],
        'sort_key': (contact.get('priority_score') or 0) + 50,
    }


def _rule_high_intent(contact: Dict) -> Optional[Dict]:
    """2+ intent signals (repeat views, high favorites, activity burst, sharing)."""
    signals = contact.get('intent_signal_count') or 0
    if signals < 2:
        return None

    favs = contact.get('properties_favorited') or 0
    views = contact.get('properties_viewed') or 0

    parts = []
    if contact.get('intent_repeat_views'):
        parts.append("repeat views")
    if favs > 3:
        parts.append(f"{favs} favorites")
    if contact.get('intent_sharing'):
        parts.append("sharing with others")

    text = "High intent: " + ", ".join(parts[:2]) + "." if parts else f"High intent: {signals} buy signals detected."
    text += " Ready for outreach."

    return {
        'text': text,
        'category': 'high_intent',
        'urgency': URGENCY_ACT_NOW,
        'opener': OPENERS['high_intent'],
        'sort_key': signals * 50 + (contact.get('heat_score') or 0),
    }


def _rule_needs_properties(contact: Dict) -> Optional[Dict]:
    """Has an active intake form but no recent property packages."""
    has_intake = contact.get('has_intake')
    has_recent_package = contact.get('has_recent_package')

    if not has_intake or has_recent_package:
        return None

    need_type = contact.get('intake_need_type') or 'property'
    area = _format_area(contact)

    # Map need types to readable labels
    need_labels = {
        'primary_home': 'primary home',
        'second_home': 'second home',
        'str': 'short-term rental',
        'ltr': 'long-term rental',
        'investment': 'investment property',
        'land': 'land',
        'child_home': 'home for family member',
    }
    need_label = need_labels.get(need_type, need_type)

    text = f"Has requirements ({need_label})"
    if area:
        text += f" in {area}"
    text += ". Needs property suggestions."

    return {
        'text': text,
        'category': 'needs_properties',
        'urgency': URGENCY_TOUCH_BASE,
        'opener': OPENERS['needs_properties'],
        'sort_key': (contact.get('priority_score') or 0),
    }


def _rule_default(contact: Dict) -> Dict:
    """Fallback: generic prospect summary."""
    source = contact.get('source') or 'IDX'
    views = contact.get('properties_viewed') or 0
    area = _format_area(contact)

    text = f"Prospect from {source}."
    if views > 0:
        text += f" {views} total property views."
    if area:
        text += f" Searching {area}."

    return {
        'text': text,
        'category': 'default',
        'urgency': URGENCY_TOUCH_BASE,
        'opener': OPENERS['default'],
        'sort_key': (contact.get('priority_score') or 0),
    }


# ─── Helpers ──────────────────────────────────────────────────────

def _format_area(contact: Dict) -> str:
    """
    Format the contact's area of interest from recent_cities or preferred_cities.
    Returns a readable string like "Asheville" or "Asheville, Weaverville".
    """
    cities = contact.get('recent_cities') or []

    # If recent_cities is a string (JSON), parse it
    if isinstance(cities, str):
        try:
            cities = json.loads(cities)
        except (json.JSONDecodeError, TypeError):
            cities = [cities] if cities else []

    # Fallback to preferred_cities
    if not cities:
        pref = contact.get('preferred_cities') or ''
        if isinstance(pref, str):
            try:
                cities = json.loads(pref)
            except (json.JSONDecodeError, TypeError):
                cities = []

    if not cities:
        return ''

    # Show up to 2 cities
    clean = [c for c in cities if c and c.strip()]
    if len(clean) <= 2:
        return ', '.join(clean)
    return f"{clean[0]}, {clean[1]} area"


def format_price_range(min_price: Optional[int], max_price: Optional[int]) -> str:
    """Format a price range like '$300-400K' or '$500K+'."""
    if not min_price and not max_price:
        return ''

    def fmt(p):
        if p >= 1_000_000:
            return f"${p / 1_000_000:.1f}M"
        return f"${p // 1000}K"

    if min_price and max_price:
        return f"{fmt(min_price)}-{fmt(max_price)}"
    elif max_price:
        return f"up to {fmt(max_price)}"
    elif min_price:
        return f"{fmt(min_price)}+"
    return ''


def generate_overnight_narrative(overnight_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Transform overnight data (activity highlights, price drops, going cold, new leads)
    into grouped categories for the "While You Were Away" section.

    Returns a list of group dicts, each with: title, icon, css_class, items[]
    Groups with no items are omitted.
    """
    groups = []

    # Split activity highlights into sub-categories
    viewed_items = []
    favorited_items = []
    shared_items = []

    for highlight in overnight_data.get('activity_highlights', []):
        name = highlight.get('name', 'Someone')
        views = highlight.get('views', 0)
        favs = highlight.get('favorites', 0)
        shares = highlight.get('shares', 0)

        if views > 0:
            viewed_items.append(f"{name} — {views} propert{'ies' if views > 1 else 'y'}")
        if favs > 0:
            favorited_items.append(f"{name} — {favs} propert{'ies' if favs > 1 else 'y'}")
        if shares > 0:
            shared_items.append(f"{name} — {shares} propert{'ies' if shares > 1 else 'y'}")

    if viewed_items:
        groups.append({
            'title': 'Viewed Properties',
            'icon': '&#128065;',
            'css_class': 'activity',
            'entries': viewed_items,
        })

    if favorited_items:
        groups.append({
            'title': 'Saved Properties',
            'icon': '&#11088;',
            'css_class': 'favorited',
            'entries': favorited_items,
        })

    if shared_items:
        groups.append({
            'title': 'Shared Properties',
            'icon': '&#128228;',
            'css_class': 'shared',
            'entries': shared_items,
        })

    # Price drops
    price_items = []
    for drop in overnight_data.get('price_drops', []):
        address = drop.get('property_address', 'A property')
        new_price = drop.get('new_value')
        old_price = drop.get('old_value')
        buyer_match = drop.get('buyer_match_name')

        price_text = ""
        if new_price and old_price:
            try:
                price_text = f" now ${int(new_price):,} (was ${int(old_price):,})"
            except (ValueError, TypeError):
                pass

        text = f"{address}{price_text}"
        if buyer_match:
            text += f" — matches {buyer_match}"
        price_items.append(text)

    if price_items:
        groups.append({
            'title': 'Price Drops',
            'icon': '&#128181;',
            'css_class': 'price_drop',
            'entries': price_items,
        })

    # Going cold
    cold_items = []
    for cold in overnight_data.get('going_cold', []):
        name = f"{cold.get('first_name', '')} {cold.get('last_name', '')}".strip()
        days = cold.get('days_since_activity', '?')
        cold_items.append(f"{name} — {days} days inactive")

    if cold_items:
        groups.append({
            'title': 'Going Cold',
            'icon': '&#129398;',
            'css_class': 'going_cold',
            'entries': cold_items,
        })

    # New leads
    lead_items = []
    for lead in overnight_data.get('new_leads', []):
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        source = lead.get('source', 'website')
        created = lead.get('created_at', '')

        hours_ago = ''
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                if created_dt.tzinfo:
                    created_dt = created_dt.replace(tzinfo=None)
                age = datetime.now() - created_dt
                h = int(age.total_seconds() / 3600)
                if h < 1:
                    hours_ago = 'just now'
                elif h < 24:
                    hours_ago = f"{h}h ago"
                else:
                    hours_ago = f"{h // 24}d ago"
            except (ValueError, TypeError):
                pass

        text = f"{name} from {source}"
        if hours_ago:
            text += f", {hours_ago}"
        lead_items.append(text)

    if lead_items:
        groups.append({
            'title': 'New Leads',
            'icon': '&#128100;',
            'css_class': 'new_lead',
            'entries': lead_items,
        })

    return groups


def generate_eod_narrative(eod_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform end-of-day report data into display-ready structures.
    Follows the generate_overnight_narrative() pattern.

    Returns dict with: warming, cooling, week_trend_pct, week_trend_arrow,
    disposition_labels, tomorrow_briefings, empty_states.
    """
    result = {}

    # Split score movers into warming vs cooling
    warming = []
    cooling = []
    for mover in eod_data.get('score_movers', []):
        delta = mover.get('heat_delta', 0)
        entry = {
            'id': mover.get('id'),
            'name': f"{mover.get('first_name', '')} {mover.get('last_name', '')}".strip(),
            'fub_id': mover.get('fub_id'),
            'heat_score': mover.get('heat_score', 0),
            'delta': abs(delta),
            'direction': mover.get('trend_direction', ''),
        }
        if delta > 0:
            warming.append(entry)
        elif delta < 0:
            cooling.append(entry)
    result['warming'] = warming
    result['cooling'] = cooling

    # Week-over-week trend as percentage
    week = eod_data.get('week_trend', {})
    this_wk = week.get('this_week', 0)
    last_wk = week.get('last_week', 0)
    if last_wk > 0:
        pct = round(((this_wk - last_wk) / last_wk) * 100)
    elif this_wk > 0:
        pct = 100
    else:
        pct = 0

    direction = week.get('direction', 'flat')
    arrows = {'up': '↑', 'down': '↓', 'flat': '→'}
    result['week_trend_pct'] = pct
    result['week_trend_arrow'] = arrows.get(direction, '→')
    result['week_trend_direction'] = direction

    # Disposition labels for display
    disp_labels = {
        'called': 'Reached',
        'left_vm': 'Voicemails',
        'texted': 'Texts Sent',
        'appointment': 'Appointments',
        'skipped': 'Skipped',
        'no_answer': 'No Answer',
    }
    result['disposition_labels'] = disp_labels

    # Generate briefings for tomorrow's priorities
    tomorrow = eod_data.get('tomorrow_priorities', [])
    if tomorrow:
        try:
            result['tomorrow_briefings'] = generate_briefings(tomorrow)
        except Exception:
            result['tomorrow_briefings'] = tomorrow
    else:
        result['tomorrow_briefings'] = []

    # Empty-state messages for sections with no data
    empty = {}
    if not eod_data.get('score_movers'):
        empty['score_movers'] = 'No score changes today'
    if not eod_data.get('property_activity'):
        empty['property_activity'] = 'No property views today'
    if not eod_data.get('high_intent'):
        empty['high_intent'] = 'No favorites or shares today'
    if not eod_data.get('accountability_gaps'):
        empty['accountability_gaps'] = 'All high-priority contacts reached — nice work!'
    if not eod_data.get('disposition_breakdown'):
        empty['disposition_breakdown'] = 'No Power Hour sessions today'
    call_stats = eod_data.get('call_stats', {})
    if call_stats.get('calls_attempted', 0) == 0:
        empty['call_stats'] = 'No calls logged today'
    result['empty_states'] = empty

    return result
