"""
Monthly Lead Report

Generates and sends a monthly lead activity report on the 1st of each month.
Includes lead trends, stage transitions, and engagement analysis.

Cron: 0 7 1 * * (1st of month 7:00 AM)
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from calendar import monthrange

from apps.automation import config
from apps.automation.email_service import send_template_email

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_month_date_range(year: int, month: int) -> tuple:
    """Get start and end dates for a given month."""
    start_date = f"{year}-{month:02d}-01"
    _, last_day = monthrange(year, month)
    end_date = f"{year}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def get_previous_month(year: int, month: int) -> tuple:
    """Get year and month for the previous month."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def get_monthly_activity_summary(year: int, month: int) -> Dict[str, Any]:
    """
    Aggregate contact activity for a given month.

    Returns:
        Dictionary with total engagement metrics
    """
    start_date, end_date = get_month_date_range(year, month)
    conn = get_db_connection()

    try:
        # Total activity metrics
        activity = conn.execute('''
            SELECT
                SUM(website_visits) as total_visits,
                SUM(properties_viewed) as total_views,
                SUM(properties_favorited) as total_favorites,
                SUM(calls_inbound + calls_outbound) as total_calls,
                SUM(texts_inbound + texts_outbound) as total_texts,
                SUM(emails_received + emails_sent) as total_emails,
                COUNT(DISTINCT contact_id) as active_contacts
            FROM contact_daily_activity
            WHERE activity_date BETWEEN ? AND ?
        ''', [start_date, end_date]).fetchone()

        # Average heat score at end of month
        avg_heat = conn.execute('''
            SELECT AVG(heat_score_snapshot) as avg_heat
            FROM contact_daily_activity
            WHERE activity_date = ?
        ''', [end_date]).fetchone()

        return {
            'total_visits': activity['total_visits'] or 0,
            'total_views': activity['total_views'] or 0,
            'total_favorites': activity['total_favorites'] or 0,
            'total_calls': activity['total_calls'] or 0,
            'total_texts': activity['total_texts'] or 0,
            'total_emails': activity['total_emails'] or 0,
            'active_contacts': activity['active_contacts'] or 0,
            'avg_heat_score': avg_heat['avg_heat'] or 0,
            'total_engagement': (
                (activity['total_visits'] or 0) +
                (activity['total_views'] or 0) +
                (activity['total_favorites'] or 0) +
                (activity['total_calls'] or 0) +
                (activity['total_texts'] or 0)
            )
        }

    finally:
        conn.close()


def get_stage_transitions(year: int, month: int) -> List[Dict[str, Any]]:
    """
    Get all stage transitions that occurred during the month.

    Returns:
        List of transition dictionaries with contact info
    """
    start_date, end_date = get_month_date_range(year, month)
    conn = get_db_connection()

    try:
        # Parse stage_history JSON from contact_workflow
        workflows = conn.execute('''
            SELECT
                cw.contact_id,
                l.first_name,
                l.last_name,
                cw.stage_history
            FROM contact_workflow cw
            JOIN leads l ON l.id = cw.contact_id
            WHERE cw.stage_history IS NOT NULL
        ''').fetchall()

        transitions = []
        for wf in workflows:
            if not wf['stage_history']:
                continue

            try:
                history = json.loads(wf['stage_history'])
                for entry in history:
                    entered_at = entry.get('entered_at', '')[:10]  # Get date part
                    if start_date <= entered_at <= end_date:
                        # Find previous stage
                        prev_stage = None
                        for i, h in enumerate(history):
                            if h == entry and i > 0:
                                prev_stage = history[i-1].get('stage')
                                break

                        if prev_stage:  # Only include if there was a previous stage
                            transitions.append({
                                'contact_id': wf['contact_id'],
                                'name': f"{wf['first_name']} {wf['last_name']}",
                                'from_stage': prev_stage,
                                'to_stage': entry.get('stage'),
                                'date': entered_at
                            })
            except json.JSONDecodeError:
                continue

        return sorted(transitions, key=lambda x: x['date'], reverse=True)

    finally:
        conn.close()


def get_pipeline_stages() -> List[Dict[str, Any]]:
    """Get current count of leads in each pipeline stage."""
    conn = get_db_connection()

    try:
        stages = conn.execute('''
            SELECT
                COALESCE(cw.current_stage, 'new_lead') as stage,
                COUNT(*) as count
            FROM leads l
            LEFT JOIN contact_workflow cw ON cw.contact_id = l.id
            WHERE l.type = 'buyer'
            GROUP BY COALESCE(cw.current_stage, 'new_lead')
        ''').fetchall()

        # Define stage order
        stage_order = [
            'new_lead',
            'nurturing',
            'actively_searching',
            'ready_to_buy',
            'under_contract',
            'closed'
        ]

        stage_names = {
            'new_lead': 'New Lead',
            'nurturing': 'Nurturing',
            'actively_searching': 'Active Search',
            'ready_to_buy': 'Ready to Buy',
            'under_contract': 'Under Contract',
            'closed': 'Closed'
        }

        stage_counts = {s['stage']: s['count'] for s in stages}

        result = []
        for stage in stage_order:
            if stage in stage_counts:
                result.append({
                    'name': stage_names.get(stage, stage),
                    'count': stage_counts[stage]
                })

        return result

    finally:
        conn.close()


def identify_hot_leads(year: int, month: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find leads whose heat score increased the most during the month.

    Returns:
        List of warming leads with activity details
    """
    start_date, end_date = get_month_date_range(year, month)
    conn = get_db_connection()

    try:
        # Get leads with positive heat score change
        hot_leads = conn.execute('''
            SELECT
                l.id,
                l.first_name || ' ' || l.last_name as name,
                COALESCE(cw.current_stage, l.stage) as stage,
                l.heat_score,
                start_scores.heat_score_snapshot as start_heat,
                end_scores.heat_score_snapshot as end_heat,
                (COALESCE(end_scores.heat_score_snapshot, 0) - COALESCE(start_scores.heat_score_snapshot, 0)) as heat_delta,
                activity.total_views,
                activity.total_visits
            FROM leads l
            LEFT JOIN contact_workflow cw ON cw.contact_id = l.id
            LEFT JOIN (
                SELECT contact_id, heat_score_snapshot
                FROM contact_daily_activity
                WHERE activity_date = ?
            ) start_scores ON start_scores.contact_id = l.id
            LEFT JOIN (
                SELECT contact_id, heat_score_snapshot
                FROM contact_daily_activity
                WHERE activity_date = ?
            ) end_scores ON end_scores.contact_id = l.id
            LEFT JOIN (
                SELECT
                    contact_id,
                    SUM(properties_viewed) as total_views,
                    SUM(website_visits) as total_visits
                FROM contact_daily_activity
                WHERE activity_date BETWEEN ? AND ?
                GROUP BY contact_id
            ) activity ON activity.contact_id = l.id
            WHERE (end_scores.heat_score_snapshot - start_scores.heat_score_snapshot) > 5
            ORDER BY heat_delta DESC
            LIMIT ?
        ''', [start_date, end_date, start_date, end_date, limit]).fetchall()

        results = []
        for lead in hot_leads:
            activity_parts = []
            if lead['total_views']:
                activity_parts.append(f"{lead['total_views']} properties viewed")
            if lead['total_visits']:
                activity_parts.append(f"{lead['total_visits']} site visits")

            results.append({
                'contact_id': lead['id'],
                'name': lead['name'],
                'stage': lead['stage'],
                'heat_score': lead['heat_score'] or lead['end_heat'] or 0,
                'heat_delta': lead['heat_delta'] or 0,
                'activity_summary': ', '.join(activity_parts) if activity_parts else 'General activity'
            })

        return results

    finally:
        conn.close()


def identify_cooling_leads(year: int, month: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find leads whose engagement is declining and need attention.

    Returns:
        List of cooling leads with days since activity
    """
    start_date, end_date = get_month_date_range(year, month)
    conn = get_db_connection()

    try:
        # Get leads with negative heat delta or no recent activity
        cooling_leads = conn.execute('''
            SELECT
                l.id,
                l.first_name || ' ' || l.last_name as name,
                COALESCE(cw.current_stage, l.stage) as stage,
                l.heat_score,
                start_scores.heat_score_snapshot as start_heat,
                end_scores.heat_score_snapshot as end_heat,
                (COALESCE(end_scores.heat_score_snapshot, 0) - COALESCE(start_scores.heat_score_snapshot, 0)) as heat_delta,
                l.days_since_activity
            FROM leads l
            LEFT JOIN contact_workflow cw ON cw.contact_id = l.id
            LEFT JOIN (
                SELECT contact_id, heat_score_snapshot
                FROM contact_daily_activity
                WHERE activity_date = ?
            ) start_scores ON start_scores.contact_id = l.id
            LEFT JOIN (
                SELECT contact_id, heat_score_snapshot
                FROM contact_daily_activity
                WHERE activity_date = ?
            ) end_scores ON end_scores.contact_id = l.id
            WHERE l.type = 'buyer'
            AND l.heat_score > 20
            AND (
                (end_scores.heat_score_snapshot - start_scores.heat_score_snapshot) < -5
                OR l.days_since_activity > 14
            )
            AND COALESCE(cw.current_stage, l.stage) NOT IN ('closed', 'lost')
            ORDER BY heat_delta ASC, l.days_since_activity DESC
            LIMIT ?
        ''', [start_date, end_date, limit]).fetchall()

        results = []
        for lead in cooling_leads:
            results.append({
                'contact_id': lead['id'],
                'name': lead['name'],
                'stage': lead['stage'],
                'heat_score': lead['heat_score'] or 0,
                'heat_delta': lead['heat_delta'] or 0,
                'days_since_activity': lead['days_since_activity'] or 0
            })

        return results

    finally:
        conn.close()


def get_new_leads(year: int, month: int) -> List[Dict[str, Any]]:
    """Get leads added during the month."""
    start_date, end_date = get_month_date_range(year, month)
    conn = get_db_connection()

    try:
        new_leads = conn.execute('''
            SELECT
                id,
                first_name || ' ' || l.last_name as name,
                source,
                type,
                heat_score,
                created_at
            FROM leads l
            WHERE DATE(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        ''', [start_date, end_date]).fetchall()

        return [{
            'contact_id': lead['id'],
            'name': lead['name'],
            'source': lead['source'],
            'type': lead['type'],
            'heat_score': lead['heat_score'] or 0,
            'created_date': lead['created_at'][:10]
        } for lead in new_leads]

    finally:
        conn.close()


def generate_monthly_report(year: Optional[int] = None, month: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate the full monthly report data.

    Args:
        year: Report year (defaults to previous month)
        month: Report month (defaults to previous month)

    Returns:
        Dictionary with all data needed for the email template
    """
    # Default to previous month
    if year is None or month is None:
        today = datetime.now()
        year, month = get_previous_month(today.year, today.month)

    prev_year, prev_month = get_previous_month(year, month)

    # Get activity summaries
    current_activity = get_monthly_activity_summary(year, month)
    previous_activity = get_monthly_activity_summary(prev_year, prev_month)

    # Get pipeline stages
    pipeline_stages = get_pipeline_stages()

    # Get new leads count
    new_leads = get_new_leads(year, month)

    # Build executive summary
    conn = get_db_connection()
    try:
        total_leads = conn.execute('SELECT COUNT(*) as count FROM leads WHERE type = "buyer"').fetchone()['count']
        active_leads = conn.execute('''
            SELECT COUNT(*) as count FROM leads l
            LEFT JOIN contact_workflow cw ON cw.contact_id = l.id
            WHERE l.type = "buyer"
            AND COALESCE(cw.workflow_status, "active") = "active"
        ''').fetchone()['count']

        # Count conversions (moved to under_contract or closed)
        start_date, end_date = get_month_date_range(year, month)
        conversions = 0  # Would need stage history parsing
    finally:
        conn.close()

    summary = {
        'total_leads': total_leads,
        'new_leads': len(new_leads),
        'active_leads': active_leads,
        'conversions': conversions
    }

    # Calculate month-over-month comparison
    def safe_delta_pct(current, previous):
        if not previous or previous == 0:
            return 0
        return round(((current - previous) / previous) * 100, 1)

    comparison = {
        'engagement_current': current_activity['total_engagement'],
        'engagement_previous': previous_activity['total_engagement'],
        'engagement_delta': safe_delta_pct(current_activity['total_engagement'], previous_activity['total_engagement']),
        'heat_current': current_activity['avg_heat_score'],
        'heat_previous': previous_activity['avg_heat_score'],
        'heat_delta': round(current_activity['avg_heat_score'] - previous_activity['avg_heat_score'], 1),
        'views_current': current_activity['total_views'],
        'views_previous': previous_activity['total_views'],
        'views_delta': safe_delta_pct(current_activity['total_views'], previous_activity['total_views']),
        'transitions_current': len(get_stage_transitions(year, month)),
        'transitions_previous': len(get_stage_transitions(prev_year, prev_month)),
        'transitions_delta': 0  # Calculate later
    }
    comparison['transitions_delta'] = safe_delta_pct(comparison['transitions_current'], comparison['transitions_previous'])

    # Generate insights
    insights = []

    if len(new_leads) > 0:
        insights.append(f"Added {len(new_leads)} new leads this month")

    if comparison['engagement_delta'] > 10:
        insights.append(f"Overall engagement up {comparison['engagement_delta']}% - leads are more active!")
    elif comparison['engagement_delta'] < -10:
        insights.append(f"Engagement down {abs(comparison['engagement_delta'])}% - consider outreach campaign")

    hot_leads = identify_hot_leads(year, month, 5)
    if hot_leads:
        insights.append(f"{len(hot_leads)} leads are warming up significantly")

    cooling_leads = identify_cooling_leads(year, month, 5)
    if cooling_leads:
        insights.append(f"{len(cooling_leads)} leads need attention - declining engagement")

    if not insights:
        insights.append("Steady month with consistent lead activity")

    # Get month name
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    return {
        'report_month': month_names[month - 1],
        'report_year': year,
        'summary': summary,
        'pipeline_stages': pipeline_stages,
        'comparison': comparison,
        'insights': insights,
        'hot_leads': identify_hot_leads(year, month),
        'cooling_leads': identify_cooling_leads(year, month),
        'new_leads': new_leads[:20],  # Limit display
        'stage_transitions': get_stage_transitions(year, month)[:15],
        'agent_name': config.AGENT_NAME,
        'agent_email': config.AGENT_EMAIL,
        'agent_phone': config.AGENT_PHONE,
        'brokerage_name': config.BROKERAGE_NAME
    }


def send_monthly_report(year: Optional[int] = None, month: Optional[int] = None) -> bool:
    """
    Generate and send the monthly lead report email.

    Args:
        year: Report year (defaults to previous month)
        month: Report month (defaults to previous month)

    Returns:
        True if sent successfully, False otherwise
    """
    logger.info("Generating monthly lead report...")

    try:
        report_data = generate_monthly_report(year, month)

        subject = f"Monthly Lead Report - {report_data['report_month']} {report_data['report_year']}"

        success = send_template_email(
            to=config.MONTHLY_REPORT_RECIPIENT,
            subject=subject,
            template_name='monthly_report.html',
            context=report_data,
            from_name='DREAMS Lead Reports'
        )

        if success:
            logger.info(f"Monthly report sent to {config.MONTHLY_REPORT_RECIPIENT}")
        else:
            logger.error("Failed to send monthly report email")

        return success

    except Exception as e:
        logger.error(f"Error generating monthly report: {e}")
        return False


def main():
    """Entry point for cron job."""
    import sys

    # Allow specifying year/month via args
    year = None
    month = None

    if len(sys.argv) > 2:
        year = int(sys.argv[1])
        month = int(sys.argv[2])

    success = send_monthly_report(year, month)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
