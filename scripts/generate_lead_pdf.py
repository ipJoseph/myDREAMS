#!/usr/bin/env python3
"""
Generate professionally formatted PDF lead profiles.

Usage:
    python generate_lead_pdf.py "Lead Name"
    python generate_lead_pdf.py --email "email@example.com"
    python generate_lead_pdf.py --id "lead-uuid-here"

Requires: reportlab (pip install reportlab)
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.lib.enums import TA_CENTER

# Paths
DB_PATH = PROJECT_ROOT / "data" / "dreams.db"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Brand colors
BRAND_PRIMARY = colors.HexColor("#1e3a5f")  # Deep blue
BRAND_ACCENT = colors.HexColor("#e85d04")   # Orange
BRAND_LIGHT = colors.HexColor("#f8f9fa")    # Light gray
BRAND_SUCCESS = colors.HexColor("#2d6a4f")  # Green


def get_lead_from_db(name=None, email=None, lead_id=None):
    """Fetch lead data from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if lead_id:
        cursor.execute("SELECT * FROM leads WHERE id = ? OR fub_id = ?", (lead_id, lead_id))
    elif email:
        cursor.execute("SELECT * FROM leads WHERE email = ?", (email,))
    elif name:
        # Search by name (first or last or full)
        parts = name.strip().split()
        if len(parts) >= 2:
            cursor.execute(
                "SELECT * FROM leads WHERE first_name LIKE ? AND last_name LIKE ?",
                (f"%{parts[0]}%", f"%{parts[-1]}%")
            )
        else:
            cursor.execute(
                "SELECT * FROM leads WHERE first_name LIKE ? OR last_name LIKE ?",
                (f"%{name}%", f"%{name}%")
            )
    else:
        conn.close()
        return None

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_lead_activities(lead_id, limit=50):
    """Fetch recent activities for a lead."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM lead_activities
        WHERE lead_id = ?
        ORDER BY activity_date DESC
        LIMIT ?
    """, (lead_id, limit))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def format_phone(phone):
    """Format phone number for display."""
    if not phone:
        return "N/A"
    phone = str(phone).replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if len(phone) == 10:
        return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
    return phone


def format_currency(value):
    """Format number as currency."""
    if not value:
        return "N/A"
    return f"${value:,.0f}"


def create_styles():
    """Create custom paragraph styles."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='MainTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=BRAND_PRIMARY,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        name='SubTitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.gray,
        spaceAfter=20
    ))

    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
        fontName='Helvetica-Bold',
    ))

    styles.add(ParagraphStyle(
        name='LeadBodyText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name='LeadSmallText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.gray
    ))

    return styles


def create_score_table(scores):
    """Create a visual score display with progress bars."""
    data = []
    for label, score, max_score in scores:
        bar_width = int((score / max_score) * 20)
        bar = "█" * bar_width + "░" * (20 - bar_width)
        data.append([label, bar, f"{score}"])

    table = Table(data, colWidths=[1.5*inch, 2.5*inch, 0.5*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), BRAND_PRIMARY),
        ('TEXTCOLOR', (1, 0), (1, -1), BRAND_ACCENT),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.gray),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table


def create_info_table(data, col_widths=None):
    """Create a styled info table."""
    if col_widths is None:
        col_widths = [1.5*inch, 4*inch]

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.gray),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    return table


def create_stats_table(stats):
    """Create a 2-column stats display."""
    mid = len(stats) // 2 + len(stats) % 2
    col1 = stats[:mid]
    col2 = stats[mid:]

    while len(col2) < len(col1):
        col2.append(('', ''))

    data = []
    for (l1, v1), (l2, v2) in zip(col1, col2):
        data.append([l1, v1, l2, v2])

    table = Table(data, colWidths=[1.5*inch, 1*inch, 1.5*inch, 1*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.gray),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.gray),
        ('TEXTCOLOR', (1, 0), (1, -1), BRAND_PRIMARY),
        ('TEXTCOLOR', (3, 0), (3, -1), BRAND_PRIMARY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table


def generate_insights(lead):
    """Generate key insights based on lead data."""
    insights = []

    # Engagement level
    visits = lead.get('website_visits', 0) or 0
    viewed = lead.get('properties_viewed', 0) or 0
    favorited = lead.get('properties_favorited', 0) or 0

    if visits >= 30 or viewed >= 50:
        insights.append(f"<b>Very engaged buyer</b> — {visits} website visits, {viewed} properties viewed, {favorited} favorited")
    elif visits >= 10 or viewed >= 20:
        insights.append(f"<b>Active buyer</b> — {visits} website visits, {viewed} properties viewed")

    # Relationship score
    rel_score = lead.get('relationship_score', 0) or 0
    if rel_score >= 80:
        insights.append(f"<b>Strong relationship score ({rel_score:.0f})</b> — good rapport established")
    elif rel_score >= 50:
        insights.append(f"<b>Moderate relationship score ({rel_score:.0f})</b> — building rapport")

    # Price range
    min_price = lead.get('min_price')
    max_price = lead.get('max_price')
    avg_price = lead.get('avg_price_viewed')
    if min_price and max_price:
        insights.append(f"<b>Budget range</b> — {format_currency(min_price)} to {format_currency(max_price)}")
    if avg_price:
        insights.append(f"<b>Average price viewed</b> — {format_currency(avg_price)}")

    # Activity recency
    days = lead.get('days_since_activity', 999)
    if days <= 3:
        insights.append(f"<b>Recently active</b> — last activity {days} days ago")
    elif days <= 7:
        insights.append(f"<b>Active this week</b> — last activity {days} days ago")
    elif days <= 30:
        insights.append(f"<b>Active this month</b> — last activity {days} days ago")

    # Intent signals
    intent_count = lead.get('intent_signal_count', 0) or 0
    if intent_count >= 2:
        insights.append(f"<b>High intent signals ({intent_count})</b> — showing serious buying interest")
    elif intent_count == 1:
        insights.append("<b>Intent signal detected</b> — showing buying interest")

    return insights


def build_pdf(lead):
    """Build the complete PDF document for a lead."""
    full_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    safe_name = full_name.lower().replace(" ", "_")
    output_path = OUTPUT_DIR / f"{safe_name}_profile.pdf"

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    styles = create_styles()
    story = []

    # Header
    heat_score = lead.get('heat_score', 0) or 0
    heat_display = "🔥" if heat_score >= 70 else "🌡️" if heat_score >= 40 else "❄️"

    story.append(Paragraph(full_name, styles['MainTitle']))
    story.append(Paragraph(f"Lead Profile  •  Heat Score: {heat_score:.0f} {heat_display}", styles['SubTitle']))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PRIMARY, spaceAfter=20))

    # Contact Information
    story.append(Paragraph("Contact Information", styles['SectionHeader']))
    contact_data = [
        ['Phone', format_phone(lead.get('phone'))],
        ['Email', lead.get('email') or 'N/A'],
        ['Stage', lead.get('stage') or 'N/A'],
        ['Source', lead.get('source') or 'N/A'],
    ]
    if lead.get('fub_id'):
        contact_data.append(['FUB ID', str(lead.get('fub_id'))])
    story.append(create_info_table(contact_data))
    story.append(Spacer(1, 12))

    # Lead Scores
    story.append(Paragraph("Lead Scores", styles['SectionHeader']))
    scores = [
        ('Heat', lead.get('heat_score', 0) or 0, 100),
        ('Priority', lead.get('priority_score', 0) or 0, 100),
        ('Relationship', lead.get('relationship_score', 0) or 0, 100),
        ('Value', lead.get('value_score', 0) or 0, 100),
    ]
    story.append(create_score_table(scores))
    story.append(Spacer(1, 12))

    # Buying Profile
    story.append(Paragraph("Buying Profile", styles['SectionHeader']))

    min_price = lead.get('min_price')
    max_price = lead.get('max_price')
    budget = f"{format_currency(min_price)} - {format_currency(max_price)}" if min_price and max_price else "N/A"

    created = lead.get('created_at', '')
    if created:
        try:
            created_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
            created = created_date.strftime('%B %d, %Y')
        except:
            pass

    last_activity = lead.get('last_activity_at', '')
    if last_activity:
        try:
            activity_date = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
            last_activity = activity_date.strftime('%B %d, %Y')
        except:
            pass

    profile_data = [
        ['Budget Range', budget],
        ['Avg. Price Viewed', format_currency(lead.get('avg_price_viewed'))],
        ['Lead Type', (lead.get('type') or 'N/A').title()],
        ['Lead Since', created or 'N/A'],
        ['Last Activity', last_activity or 'N/A'],
    ]
    story.append(create_info_table(profile_data))
    story.append(Spacer(1, 12))

    # Engagement Statistics
    story.append(Paragraph("Engagement Statistics", styles['SectionHeader']))
    stats = [
        ('Website Visits', str(lead.get('website_visits', 0) or 0)),
        ('Properties Viewed', str(lead.get('properties_viewed', 0) or 0)),
        ('Properties Favorited', str(lead.get('properties_favorited', 0) or 0)),
        ('Outbound Calls', str(lead.get('calls_outbound', 0) or 0)),
        ('Emails Sent', str(lead.get('emails_sent', 0) or 0)),
        ('Emails Received', str(lead.get('emails_received', 0) or 0)),
    ]
    story.append(create_stats_table(stats))
    story.append(Spacer(1, 16))

    # Key Insights
    story.append(Paragraph("Key Insights", styles['SectionHeader']))
    insights = generate_insights(lead)
    if insights:
        for insight in insights:
            story.append(Paragraph(f"• {insight}", styles['LeadBodyText']))
    else:
        story.append(Paragraph("• No significant insights available yet", styles['LeadBodyText']))
    story.append(Spacer(1, 20))

    # Recommendation
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_SUCCESS, spaceBefore=10, spaceAfter=10))
    rec_style = ParagraphStyle(
        'Recommendation',
        parent=styles['LeadBodyText'],
        fontSize=11,
        textColor=BRAND_SUCCESS,
        fontName='Helvetica-Bold',
        spaceBefore=6,
        spaceAfter=6
    )
    story.append(Paragraph("RECOMMENDATION", rec_style))

    # Generate recommendation based on scores
    heat = lead.get('heat_score', 0) or 0
    priority = lead.get('priority_score', 0) or 0
    days = lead.get('days_since_activity', 999)

    if heat >= 70 and priority >= 70:
        rec = "High-priority lead — reach out immediately with personalized property recommendations."
    elif heat >= 50 or priority >= 50:
        rec = "Active lead — schedule a follow-up call to discuss their property search."
    elif days <= 7:
        rec = "Recently active — send a curated list of new listings matching their criteria."
    else:
        rec = "Consider a re-engagement campaign with market updates or new listings."

    story.append(Paragraph(rec, styles['LeadBodyText']))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_SUCCESS, spaceBefore=10, spaceAfter=20))

    # Footer
    story.append(Spacer(1, 20))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['LeadSmallText'],
        alignment=TA_CENTER
    )
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}  •  "
        "Jon Tharp Homes  •  Keller Williams",
        footer_style
    ))

    doc.build(story)
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate lead profile PDF')
    parser.add_argument('name', nargs='?', help='Lead name to search for')
    parser.add_argument('--email', '-e', help='Search by email address')
    parser.add_argument('--id', '-i', dest='lead_id', help='Search by lead ID')

    args = parser.parse_args()

    if not args.name and not args.email and not args.lead_id:
        parser.error("Please provide a lead name, --email, or --id")

    # Find the lead
    lead = get_lead_from_db(name=args.name, email=args.email, lead_id=args.lead_id)

    if not lead:
        print(f"Error: Lead not found", file=sys.stderr)
        sys.exit(1)

    full_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    print(f"Found lead: {full_name}")

    # Generate PDF
    output_path = build_pdf(lead)
    print(f"PDF created: {output_path}")

    return output_path


if __name__ == "__main__":
    main()
