#!/usr/bin/env python3
"""
FUB Smart List Optimization Report — PDF Generator

Generates a professionally branded PDF analyzing Follow Up Boss smart list
configuration and recommending improvements aligned with FUB best practices.

Usage:
    python3 generate_fub_analysis_pdf.py
    python3 generate_fub_analysis_pdf.py --output /path/to/output.pdf

Requires: reportlab (pip install reportlab)
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, ListFlowable, ListItem
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF

# ── Brand Colors (Jon Tharp Homes) ────────────────────────────────────
NAVY = colors.HexColor("#082d40")
GOLD = colors.HexColor("#ddab4a")
GRAY = colors.HexColor("#4e4e4e")
LIGHT_GRAY = colors.HexColor("#f5f5f5")
WHITE = colors.white
MED_GRAY = colors.HexColor("#999999")
LIGHT_GOLD = colors.HexColor("#fdf6e3")
LIGHT_NAVY = colors.HexColor("#e8eef2")
SUCCESS = colors.HexColor("#2d6a4f")
WARNING = colors.HexColor("#b45309")
DANGER = colors.HexColor("#991b1b")

# ── Paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def build_styles():
    """Create the full style set for the report."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        'CoverTitle', fontName='Times-Bold', fontSize=28, leading=34,
        textColor=NAVY, alignment=TA_CENTER, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        'CoverSubtitle', fontName='Times-Roman', fontSize=14, leading=18,
        textColor=GOLD, alignment=TA_CENTER, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        'CoverMeta', fontName='Helvetica', fontSize=10, leading=14,
        textColor=GRAY, alignment=TA_CENTER, spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        'SectionHead', fontName='Times-Bold', fontSize=18, leading=22,
        textColor=NAVY, spaceBefore=18, spaceAfter=8,
        borderWidth=0, borderPadding=0
    ))
    styles.add(ParagraphStyle(
        'SubHead', fontName='Times-Bold', fontSize=13, leading=17,
        textColor=NAVY, spaceBefore=12, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        'SubHead2', fontName='Times-Roman', fontSize=11, leading=14,
        textColor=GRAY, spaceBefore=8, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        'Body', fontName='Helvetica', fontSize=10, leading=14,
        textColor=GRAY, spaceAfter=6, alignment=TA_JUSTIFY
    ))
    styles.add(ParagraphStyle(
        'BodyBold', fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=GRAY, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        'Callout', fontName='Helvetica', fontSize=10, leading=14,
        textColor=NAVY, spaceAfter=6, leftIndent=18, rightIndent=18,
        backColor=LIGHT_NAVY, borderPadding=8
    ))
    styles.add(ParagraphStyle(
        'CalloutGold', fontName='Helvetica', fontSize=10, leading=14,
        textColor=GRAY, spaceAfter=6, leftIndent=18, rightIndent=18,
        backColor=LIGHT_GOLD, borderPadding=8
    ))
    styles.add(ParagraphStyle(
        'Verdict', fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=WHITE, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'TableHead', fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=WHITE, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'TableCell', fontName='Helvetica', fontSize=9, leading=12,
        textColor=GRAY
    ))
    styles.add(ParagraphStyle(
        'TableCellCenter', fontName='Helvetica', fontSize=9, leading=12,
        textColor=GRAY, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'TableCellBold', fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=NAVY
    ))
    styles.add(ParagraphStyle(
        'SmallNote', fontName='Helvetica', fontSize=8, leading=10,
        textColor=MED_GRAY, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        'BulletBody', fontName='Helvetica', fontSize=10, leading=14,
        textColor=GRAY, spaceAfter=4, leftIndent=24, bulletIndent=12
    ))
    styles.add(ParagraphStyle(
        'Stat', fontName='Times-Bold', fontSize=36, leading=40,
        textColor=NAVY, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'StatLabel', fontName='Helvetica', fontSize=9, leading=12,
        textColor=GRAY, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'Footer', fontName='Helvetica', fontSize=8, leading=10,
        textColor=MED_GRAY
    ))
    return styles


def gold_rule():
    """A thin gold horizontal rule."""
    return HRFlowable(width="100%", thickness=1.5, color=GOLD,
                      spaceBefore=2, spaceAfter=8)


def navy_rule():
    """A thin navy horizontal rule."""
    return HRFlowable(width="100%", thickness=0.5, color=NAVY,
                      spaceBefore=2, spaceAfter=6)


def section_head(text, styles):
    """Section heading with gold underline."""
    return [Paragraph(text, styles['SectionHead']), gold_rule()]


def make_table(headers, rows, col_widths=None, highlight_col=None):
    """Build a branded table with navy header row."""
    style = getSampleStyleSheet()

    head_style = ParagraphStyle('_th', fontName='Helvetica-Bold', fontSize=9,
                                leading=11, textColor=WHITE, alignment=TA_CENTER)
    cell_style = ParagraphStyle('_tc', fontName='Helvetica', fontSize=9,
                                leading=11, textColor=GRAY)
    cell_center = ParagraphStyle('_tcc', fontName='Helvetica', fontSize=9,
                                 leading=11, textColor=GRAY, alignment=TA_CENTER)
    cell_bold = ParagraphStyle('_tcb', fontName='Helvetica-Bold', fontSize=9,
                               leading=11, textColor=NAVY)

    data = [[Paragraph(h, head_style) for h in headers]]
    for row in rows:
        cells = []
        for i, val in enumerate(row):
            if i == 0:
                cells.append(Paragraph(str(val), cell_bold))
            elif isinstance(val, str) and len(val) > 30:
                cells.append(Paragraph(str(val), cell_style))
            else:
                cells.append(Paragraph(str(val), cell_center))
        data.append(cells)

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]
    # Alternate row shading
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GRAY))

    # Highlight column (for before/after)
    if highlight_col is not None:
        for i in range(1, len(data)):
            cmds.append(('BACKGROUND', (highlight_col, i), (highlight_col, i),
                          LIGHT_GOLD))

    tbl.setStyle(TableStyle(cmds))
    return tbl


def stat_box(number, label, styles):
    """A single stat block for the KPI row."""
    data = [
        [Paragraph(str(number), styles['Stat'])],
        [Paragraph(label, styles['StatLabel'])]
    ]
    t = Table(data, colWidths=[1.8*inch])
    t.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def build_cover(styles):
    """Title page elements."""
    elements = []
    elements.append(Spacer(1, 1.5*inch))

    # Title
    elements.append(Paragraph("Smart List Optimization", styles['CoverTitle']))
    elements.append(Paragraph("Analysis &amp; Recommendations", styles['CoverTitle']))
    elements.append(Spacer(1, 0.15*inch))
    elements.append(gold_rule())
    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph(
        "Aligning Our Follow Up Boss Configuration with CRM Best Practices",
        styles['CoverSubtitle']))
    elements.append(Spacer(1, 0.5*inch))

    elements.append(Paragraph("Jon Tharp Homes  |  Keller Williams", styles['CoverMeta']))
    elements.append(Paragraph(datetime.now().strftime("February %Y"), styles['CoverMeta']))
    elements.append(Paragraph("Confidential \u2014 Internal Use Only", styles['CoverMeta']))

    elements.append(Spacer(1, 1.5*inch))

    # Key stats preview
    row_data = [[
        stat_box("89%", "Contacts\nUnbucketed", styles),
        stat_box("15", "Revenue Contacts\nWith No Bucket", styles),
        stat_box("5\u21928", "Proposed\nBuckets", styles),
    ]]
    preview = Table(row_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    preview.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEAFTER', (0, 0), (1, 0), 0.5, MED_GRAY),
    ]))
    elements.append(preview)

    elements.append(PageBreak())
    return elements


def build_executive_summary(styles):
    """Section 1: Executive Summary."""
    elements = []
    elements.extend(section_head("1. Executive Summary", styles))

    elements.append(Paragraph(
        "Our Follow Up Boss smart lists are a strong foundation for systematic prospecting. "
        "The structure \u2014 seven priority-ordered buckets worked to zero each session \u2014 "
        "is exactly the right framework. This analysis identifies specific configuration "
        "adjustments that can significantly increase how many contacts surface in those lists "
        "on any given day.",
        styles['Body']))

    elements.append(Paragraph(
        "The core finding: <b>approximately 89% of active contacts don\u2019t appear in any "
        "smart list at any given moment.</b> Most of that gap isn\u2019t a design flaw \u2014 it\u2019s "
        "the result of a few threshold settings that are stricter than FUB\u2019s own recommended "
        "defaults, plus two pipeline stages that don\u2019t have bucket coverage yet.",
        styles['Body']))

    elements.append(Paragraph(
        "The good news: the fixes are straightforward. Three filter adjustments (about "
        "30 minutes in FUB settings) can immediately surface an estimated 45 additional "
        "contacts per day. A phased rollout over 3\u20134 weeks could bring coverage from "
        "roughly 10% to over 50%, with zero disruption to the existing workflow.",
        styles['Body']))

    elements.append(Spacer(1, 0.15*inch))

    # Three opportunity areas
    elements.append(Paragraph("<b>Three Opportunity Areas</b>", styles['BodyBold']))

    bullets = [
        ("<b>Threshold Alignment</b> \u2014 Several lastComm thresholds are stricter than "
         "FUB\u2019s recommended defaults, causing contacts to stay invisible longer than intended."),
        ("<b>Pipeline Coverage</b> \u2014 Active Clients and Under Contract contacts have "
         "no bucket, meaning our highest-revenue relationships rely entirely on memory for follow-up timing."),
        ("<b>Transition Gaps</b> \u2014 Leads between the New Leads window and the Unresponsive "
         "threshold fall into a dead zone with no list visibility."),
    ]
    for b in bullets:
        elements.append(Paragraph(b, styles['BulletBody'], bulletText='\u2022'))

    elements.append(PageBreak())
    return elements


def build_how_smartlists_work(styles):
    """Section 2: How FUB Smart Lists Work."""
    elements = []
    elements.extend(section_head("2. How Our Smart Lists Work Today", styles))

    elements.append(Paragraph(
        "Every FUB smart list filters contacts along three axes:",
        styles['Body']))

    tbl = make_table(
        ["Axis", "What It Controls", "Example"],
        [
            ["Stage", "Which pipeline stage the contact is in", "Lead, Nurture, Hot Prospect"],
            ["Last Communication", "How long since the last call, text, or email", ">7 days, >30 days, >90 days"],
            ["Timeframe", "The contact\u2019s self-reported buying timeline", "0\u20133 months, 3\u20136 months"],
        ],
        col_widths=[1.4*inch, 2.6*inch, 2.5*inch]
    )
    elements.append(tbl)
    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph(
        "The workflow is disciplined and effective: open each list during Power Hour, "
        "work it to zero, move to the next. When a contact is called, they drop off "
        "(because Last Communication resets) and reappear when their cadence comes due again. "
        "This only works optimally when <b>every active contact lands in some bucket.</b>",
        styles['Body']))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("<b>Current 7 Smart Lists</b>", styles['SubHead']))

    tbl2 = make_table(
        ["#", "Bucket", "Filter Logic", "Cadence", "Est. Count"],
        [
            ["1", "New Leads", "Stage=Lead + Created <14d + LastComm >12hrs", "Daily", "~18"],
            ["2", "Priority", "Stage=Hot Prospect + LastComm >3d", "Semiweekly", "0"],
            ["3", "Hot", "Stage=Nurture + Timeframe 0\u20133mo + LastComm >7d", "Weekly", "~8"],
            ["4", "Warm", "Stage=Nurture + Timeframe 3\u20136mo + LastComm >30d", "Monthly", "~9"],
            ["5", "Cool", "Stage=Nurture + Timeframe 6\u201312/12+/No Plans + LastComm >90d", "Quarterly", "~1"],
            ["6", "Unresponsive", "Stage=Lead + Created >14d + LastComm >14d", "Biweekly", "~1"],
            ["7", "Timeframe Empty", "Stage=Nurture + No timeframe set", "As needed", "~0"],
        ],
        col_widths=[0.3*inch, 1.1*inch, 2.8*inch, 0.9*inch, 0.8*inch]
    )
    elements.append(tbl2)
    elements.append(Spacer(1, 0.08*inch))
    elements.append(Paragraph(
        "Total currently in buckets: ~37 of ~367 active contacts",
        styles['SmallNote']))

    elements.append(PageBreak())
    return elements


def build_bucket_analysis(styles):
    """Section 3: Bucket-by-Bucket Analysis."""
    elements = []
    elements.extend(section_head("3. Bucket-by-Bucket Analysis", styles))

    elements.append(Paragraph(
        "Each bucket is evaluated against FUB\u2019s recommended defaults and real "
        "contact distribution data from our database.",
        styles['Body']))

    buckets = [
        {
            'name': 'New Leads',
            'verdict': 'Working Well',
            'verdict_color': SUCCESS,
            'count': '~18',
            'summary': (
                "This bucket correctly captures fresh IDX registrations and surfaces them for "
                "immediate follow-up. The daily cadence aligns with speed-to-lead best practices. "
                "One refinement to consider: FUB\u2019s recommended default is a <b>10-day window</b> "
                "(we use 14 days). Tightening this would create a cleaner handoff to downstream buckets."
            ),
        },
        {
            'name': 'Priority',
            'verdict': 'Opportunity to Repurpose',
            'verdict_color': WARNING,
            'count': '0',
            'summary': (
                "This bucket monitors the Hot Prospect stage, which isn\u2019t actively used in our pipeline. "
                "Result: the second-highest call cadence (semiweekly) is allocated to a bucket that "
                "consistently shows zero contacts. <b>This is prime real estate in our workflow</b> \u2014 "
                "repurposing it for Active Clients and Under Contract contacts would cover our "
                "highest-revenue relationships."
            ),
        },
        {
            'name': 'Hot',
            'verdict': 'Partially Effective',
            'verdict_color': WARNING,
            'count': '~8',
            'summary': (
                "Captures Nurture contacts with a 0\u20133 month buying timeframe who haven\u2019t been "
                "contacted in a week. This works well for that specific group. However, <b>it only "
                "sees the Nurture stage</b>. High-activity contacts in the Lead or Active Client "
                "stage (some with maximum engagement scores) are invisible to this list."
            ),
        },
        {
            'name': 'Warm',
            'verdict': 'Threshold Too Strict',
            'verdict_color': WARNING,
            'count': '~9',
            'summary': (
                "Targets Nurture contacts in the 3\u20136 month window. Conceptually sound, but the "
                "<b>30-day lastComm threshold is twice FUB\u2019s recommended default of 14 days</b>. "
                "A buyer in the 3\u20136 month window going 30 days without contact risks losing "
                "engagement. Bringing this to 14 days would align with best practice and surface "
                "approximately 6 more contacts."
            ),
        },
        {
            'name': 'Cool',
            'verdict': 'Needs Adjustment',
            'verdict_color': DANGER,
            'count': '1',
            'summary': (
                "The concept is right: longer-timeframe contacts need less frequent touch. But the "
                "<b>90-day lastComm threshold is 3\u00d7 stricter than FUB\u2019s recommended 30-day default</b>. "
                "Of 102 Nurture contacts with a 6+ month timeframe, only 1 has gone 90 days without "
                "contact. Adjusting to 30 days would immediately surface an estimated 20\u201325 contacts. "
                "This is the single highest-impact adjustment available."
            ),
        },
        {
            'name': 'Unresponsive',
            'verdict': 'Surge Pattern',
            'verdict_color': WARNING,
            'count': '~1 (spikes to 150+)',
            'summary': (
                "The 14-day lastComm threshold synchronizes with bulk action plans. When a drip "
                "campaign fires for a large batch, all contacts cross the Unresponsive threshold on "
                "the same day \u2014 creating spikes of 150+ contacts. The list is either nearly empty "
                "or overwhelmingly full. <b>Raising the threshold to 45 days</b> would smooth the distribution "
                "and catch genuinely unresponsive contacts rather than recently-dripped ones."
            ),
        },
        {
            'name': 'Timeframe Empty',
            'verdict': 'Good Concept, Expand Scope',
            'verdict_color': WARNING,
            'count': '~0',
            'summary': (
                "Excellent idea \u2014 flagging contacts who need a buying timeline captured. Currently "
                "scoped to Nurture stage only (6 contacts without timeframes). But <b>160 Lead-stage "
                "contacts also lack timeframes</b> and are the ones most needing a qualification call. "
                "Expanding to include Leads would dramatically increase this list\u2019s value."
            ),
        },
    ]

    for b in buckets:
        # Bucket header with verdict badge
        name_para = Paragraph(
            f"<b>{b['name']}</b> &nbsp;&nbsp; <font size='8'>Est. count: {b['count']}</font>",
            styles['SubHead'])

        verdict_data = [[Paragraph(b['verdict'], styles['Verdict'])]]
        verdict_tbl = Table(verdict_data, colWidths=[1.8*inch], rowHeights=[0.25*inch])
        verdict_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), b['verdict_color']),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('VALIGN', (0, 0), (0, 0), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (0, 0), 3),
            ('BOTTOMPADDING', (0, 0), (0, 0), 3),
            ('ROUNDEDCORNERS', [3, 3, 3, 3]),
        ]))

        header_row = Table(
            [[name_para, verdict_tbl]],
            colWidths=[4.5*inch, 2*inch]
        )
        header_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        elements.append(header_row)
        elements.append(Paragraph(b['summary'], styles['Body']))
        elements.append(Spacer(1, 0.08*inch))
        elements.append(navy_rule())

    elements.append(PageBreak())
    return elements


def build_coverage_gap(styles):
    """Section 4: The Coverage Gap."""
    elements = []
    elements.extend(section_head("4. Where Contacts Fall Through", styles))

    elements.append(Paragraph(
        "Working backward from our 367 active contacts, here\u2019s how the current filters "
        "narrow down to ~37 in buckets:",
        styles['Body']))

    # Funnel table
    funnel = make_table(
        ["Filter Step", "Contacts Remaining", "What\u2019s Excluded"],
        [
            ["All active contacts", "367", "\u2014"],
            ["Stage filter applied", "351", "14 Active Clients + 1 Under Contract (no bucket exists)"],
            ["Lead buckets (New + Unresponsive)", "~19 of 198 Leads", "169 Leads between 14-day thresholds (\u201cLead Limbo\u201d)"],
            ["Nurture buckets (Hot/Warm/Cool)", "~18 of 153 Nurture", "6 lack timeframe; rest contacted too recently for threshold"],
            ["Cool (90d threshold)", "1 of 102 eligible", "101 contacted within 90 days (FUB default: 30 days)"],
        ],
        col_widths=[1.8*inch, 1.3*inch, 3.4*inch]
    )
    elements.append(funnel)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph("<b>Stages With Zero Bucket Coverage</b>", styles['SubHead']))

    stages_tbl = make_table(
        ["Stage", "Contacts", "Avg Deal Priority", "Current Bucket Coverage"],
        [
            ["Active Client", "14", "35.4", "None"],
            ["Under Contract", "1", "74.9", "None"],
        ],
        col_widths=[1.4*inch, 1.0*inch, 1.3*inch, 2.8*inch]
    )
    elements.append(stages_tbl)
    elements.append(Spacer(1, 0.1*inch))

    elements.append(Paragraph(
        "These are the contacts closest to a closing table. Their follow-up timing currently "
        "depends entirely on agent memory \u2014 no smart list prompts a check-in. "
        "Adding a bucket for these stages is the most impactful single change we can make.",
        styles['Callout']))

    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("<b>The Timeframe Gap</b>", styles['SubHead']))
    elements.append(Paragraph(
        "The Hot, Warm, and Cool buckets all require a buying timeframe to be set. "
        "However, <b>178 of 367 active contacts (49%) don\u2019t have a timeframe</b>. "
        "Among Leads specifically, 81% are missing this field. These contacts can\u2019t enter "
        "the Hot/Warm/Cool pipeline until someone sets their timeframe \u2014 but there\u2019s no "
        "list prompting that qualification call (Timeframe Empty only covers Nurture, not Leads).",
        styles['Body']))

    tf_tbl = make_table(
        ["Stage", "No Timeframe", "Total", "% Missing"],
        [
            ["Lead", "160", "198", "81%"],
            ["Active Client", "12", "14", "86%"],
            ["Nurture", "6", "153", "4%"],
        ],
        col_widths=[1.4*inch, 1.3*inch, 1.0*inch, 1.0*inch]
    )
    elements.append(tf_tbl)

    elements.append(PageBreak())
    return elements


def build_five_patterns(styles):
    """Section 5: Five Patterns to Address."""
    elements = []
    elements.extend(section_head("5. Five Patterns to Address", styles))

    patterns = [
        {
            'title': '1. Lead Transition Gap',
            'scale': '169 contacts (46% of active)',
            'detail': (
                "Leads older than 14 days who were contacted within the last 14 days. "
                "Too old for New Leads, too recently contacted for Unresponsive. These contacts "
                "are in follow-up sequences but have no smart list visibility if the sequence "
                "stalls or the agent wants to manually check in."
            ),
            'fix': 'A new "Attempted" bucket bridges this gap (see recommendations).'
        },
        {
            'title': '2. Unresponsive Surge',
            'scale': '150 contacts on a single day',
            'detail': (
                "Bulk action plans reset lastComm for large batches. Exactly 14 days later, "
                "the entire batch crosses the Unresponsive threshold simultaneously. "
                "The list swings between nearly empty and overwhelmingly full."
            ),
            'fix': 'Raising the threshold from 14 to 45 days smooths the distribution.'
        },
        {
            'title': '3. Unused Priority Slot',
            'scale': '0 contacts, permanently',
            'detail': (
                "The Priority bucket monitors the Hot Prospect stage, which isn\u2019t part of our active workflow. "
                "The semiweekly cadence \u2014 our second-most-aggressive \u2014 goes unused."
            ),
            'fix': 'Repurpose for Active Client + Under Contract contacts.'
        },
        {
            'title': '4. Revenue Stage Blind Spot',
            'scale': '15 contacts with zero coverage',
            'detail': (
                "Active Client and Under Contract contacts don\u2019t match any smart list filter. "
                "These are the highest-revenue contacts in the database, yet they receive no "
                "automated follow-up prompts."
            ),
            'fix': 'The repurposed Priority bucket covers these immediately.'
        },
        {
            'title': '5. Timeframe Qualification Loop',
            'scale': '49% of contacts affected',
            'detail': (
                "Hot/Warm/Cool require a timeframe. Setting a timeframe requires a qualification call. "
                "Getting prompted for that call requires being on a list. Being on those lists "
                "requires a timeframe. The loop breaks when Timeframe Empty is expanded to include Leads."
            ),
            'fix': 'Expand Timeframe Empty to Stage IN (Lead, Nurture).'
        },
    ]

    for p in patterns:
        elements.append(Paragraph(f"<b>{p['title']}</b>", styles['SubHead']))
        elements.append(Paragraph(
            f"<i>Scale: {p['scale']}</i>", styles['SmallNote']))
        elements.append(Paragraph(p['detail'], styles['Body']))
        elements.append(Paragraph(
            f"<b>Recommendation:</b> {p['fix']}", styles['CalloutGold']))
        elements.append(Spacer(1, 0.05*inch))

    elements.append(PageBreak())
    return elements


def build_best_practices(styles):
    """Section 6: Best Practice Comparison."""
    elements = []
    elements.extend(section_head("6. FUB Best Practice Comparison", styles))

    elements.append(Paragraph(
        "Follow Up Boss publishes recommended default thresholds for smart list configuration. "
        "The table below compares our current settings against those defaults and industry standards.",
        styles['Body']))

    tbl = make_table(
        ["Parameter", "FUB Recommended", "Our Setting", "Gap"],
        [
            ["New Lead window", "10 days", "14 days", "4 days longer"],
            ["Warm lastComm threshold", "14 days", "30 days", "2\u00d7 slower"],
            ["Cool lastComm threshold", "30 days", "90 days", "3\u00d7 slower"],
            ["Unresponsive threshold", "30 days", "14 days", "2\u00d7 faster (surge risk)"],
            ["Active Client coverage", "Dedicated bucket", "No bucket", "Revenue stage invisible"],
        ],
        col_widths=[1.8*inch, 1.4*inch, 1.3*inch, 2.0*inch]
    )
    elements.append(tbl)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph("<b>Industry Standard Cadences</b>", styles['SubHead']))

    tbl2 = make_table(
        ["Contact Type", "Industry Standard", "Our Cadence", "Status"],
        [
            ["Speed-to-lead (new)", "Daily for 7\u201310 days", "Daily for 14 days", "On track"],
            ["Active buyer (0\u20133mo)", "Every 3\u20135 days", "Weekly", "Slightly slower"],
            ["Active client (deal in progress)", "Every 2\u20133 days", "No cadence", "Gap"],
            ["Warm pipeline (3\u20136mo)", "Biweekly", "Monthly", "2\u00d7 slower"],
            ["Long-term nurture (6mo+)", "Monthly", "Quarterly (effectively never)", "Gap"],
            ["Unresponsive re-engagement", "Monthly", "Biweekly (but surge pattern)", "Execution gap"],
        ],
        col_widths=[1.8*inch, 1.5*inch, 1.7*inch, 1.5*inch]
    )
    elements.append(tbl2)
    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph(
        "The takeaway: our bucket <i>structure</i> is solid. The adjustments are in the "
        "<i>thresholds</i> and <i>stage coverage</i> \u2014 tuning the dials, not redesigning the machine.",
        styles['Callout']))

    elements.append(PageBreak())
    return elements


def build_recommendations(styles):
    """Section 7: Recommended Bucket Redesign."""
    elements = []
    elements.extend(section_head("7. Recommended Configuration", styles))

    elements.append(Paragraph(
        "The proposed 8-bucket system keeps the existing workflow intact while closing "
        "the coverage gaps. Changes are highlighted in the table below.",
        styles['Body']))

    tbl = make_table(
        ["#", "Bucket", "Filter", "Cadence", "Change"],
        [
            ["1", "New Leads", "Stage=Lead + Created <10d + LastComm >12hrs",
             "Daily", "Window 14d \u2192 10d"],
            ["2", "Active Pipeline", "Stage IN (Active Client, Under Contract) + LastComm >3d",
             "Every 3 days", "NEW \u2014 replaces Priority"],
            ["3", "Hot", "Nurture + Timeframe 0\u20133mo + LastComm >7d",
             "Weekly", "No change"],
            ["4", "Warm", "Nurture + Timeframe 3\u20136mo + LastComm >14d",
             "Biweekly", "Threshold 30d \u2192 14d"],
            ["5", "Cool", "Nurture + Timeframe 6+mo + LastComm >30d",
             "Monthly", "Threshold 90d \u2192 30d"],
            ["6", "Attempted", "Stage=Lead + Created >10d + LastComm 5\u201345d",
             "Every 5 days", "NEW \u2014 fills transition gap"],
            ["7", "Unresponsive", "Stage=Lead + Created >10d + LastComm >45d",
             "Biweekly", "Threshold 14d \u2192 45d"],
            ["8", "Timeframe Empty", "Stage IN (Lead, Nurture) + No timeframe + LastComm >14d",
             "As needed", "Add Lead stage"],
        ],
        col_widths=[0.3*inch, 1.05*inch, 2.4*inch, 0.8*inch, 1.4*inch]
    )
    elements.append(tbl)
    elements.append(Spacer(1, 0.2*inch))

    # Key design rationale
    elements.append(Paragraph("<b>Design Rationale</b>", styles['SubHead']))

    rationale = [
        ("<b>Active Pipeline replaces Priority</b> \u2014 The Hot Prospect stage is unused. "
         "Active Clients and Under Contract are the highest-revenue contacts with zero coverage. "
         "This semiweekly slot now monitors the contacts closest to closing."),
        ("<b>Attempted fills the transition gap</b> \u2014 169 contacts currently vanish between "
         "New Leads and Unresponsive. \u201cAttempted\u201d captures leads that have been contacted but "
         "haven\u2019t responded yet \u2014 the active follow-up window."),
        ("<b>Unresponsive raised to 45 days</b> \u2014 At 14 days, contacts still in active drip "
         "campaigns flood this list. At 45 days, a contact has genuinely gone cold. This also "
         "eliminates the 150-contact surge pattern."),
        ("<b>Cool threshold aligned to FUB default</b> \u2014 Moving from 90 to 30 days is the "
         "single highest-impact change: ~24 more contacts visible immediately."),
    ]
    for r in rationale:
        elements.append(Paragraph(r, styles['BulletBody'], bulletText='\u2022'))

    elements.append(PageBreak())
    return elements


def build_before_after(styles):
    """Section 8: Before/After Projection."""
    elements = []
    elements.extend(section_head("8. Projected Impact", styles))

    elements.append(Paragraph(
        "Estimated bucket populations based on current contact distribution:",
        styles['Body']))

    tbl = make_table(
        ["Bucket", "Current", "Projected", "Change"],
        [
            ["New Leads", "~18", "~15", "\u20133 (tighter window)"],
            ["Priority \u2192 Active Pipeline", "0", "~15", "+15 (revenue contacts)"],
            ["Hot", "~8", "~8", "\u2014"],
            ["Warm", "~9", "~15", "+6 (lower threshold)"],
            ["Cool", "1", "~25", "+24 (30d vs 90d)"],
            ["Attempted", "\u2014", "~80", "NEW"],
            ["Unresponsive", "~1*", "~40", "Smoothed (no surge)"],
            ["Timeframe Empty", "~0", "~30", "+30 (Leads included)"],
        ],
        col_widths=[1.8*inch, 0.9*inch, 0.9*inch, 2.4*inch],
        highlight_col=2
    )
    elements.append(tbl)
    elements.append(Paragraph(
        "* Current Unresponsive averages ~1 but spikes to 150+ on surge days.",
        styles['SmallNote']))

    elements.append(Spacer(1, 0.25*inch))

    # Summary stats
    elements.append(Paragraph("<b>Coverage Summary</b>", styles['SubHead']))

    summary_tbl = make_table(
        ["Metric", "Before", "After", "Improvement"],
        [
            ["Contacts in any bucket", "~37", "~195", "5\u00d7 increase"],
            ["Coverage rate", "~10%", "~53%", "+43 points"],
            ["Active Clients covered", "0 of 15", "15 of 15", "Full coverage"],
            ["Lead transition gap", "169", "0", "Eliminated"],
            ["Surge max (single day)", "150", "~40", "73% reduction"],
            ["Stages with no coverage", "2", "0", "Full pipeline"],
        ],
        col_widths=[1.8*inch, 1.1*inch, 1.1*inch, 2.0*inch],
        highlight_col=2
    )
    elements.append(summary_tbl)
    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph(
        "The remaining ~47% unbucketed contacts are <b>by design</b> \u2014 they were recently "
        "contacted and haven\u2019t hit their next cadence threshold. The critical difference: "
        "before, 89% unbucketed included contacts that would <i>never</i> appear in any bucket. "
        "After, all unbucketed contacts are simply between touches.",
        styles['Callout']))

    elements.append(PageBreak())
    return elements


def build_implementation(styles):
    """Section 9: Implementation Sequence."""
    elements = []
    elements.extend(section_head("9. Implementation Plan", styles))

    elements.append(Paragraph(
        "A phased approach lets us capture quick wins immediately and validate each change "
        "before moving to the next.",
        styles['Body']))

    # Phase 1
    elements.append(Paragraph("<b>Phase 1 \u2014 Quick Wins</b> (Week 1, ~30 minutes)", styles['SubHead']))
    elements.append(Paragraph(
        "Three filter edits to existing smart lists. No new lists needed.",
        styles['Body']))

    p1_tbl = make_table(
        ["Action", "Bucket", "Change", "Immediate Impact"],
        [
            ["Fix Cool threshold", "Cool", "90d \u2192 30d", "+24 contacts visible"],
            ["Repurpose Priority", "Priority \u2192 Active Pipeline",
             "Hot Prospect \u2192 Active Client + Under Contract", "15 revenue contacts covered"],
            ["Fix Warm threshold", "Warm", "30d \u2192 14d", "+6 contacts, aligns with FUB default"],
        ],
        col_widths=[1.2*inch, 1.5*inch, 1.8*inch, 2.0*inch]
    )
    elements.append(p1_tbl)
    elements.append(Spacer(1, 0.15*inch))

    # Phase 2
    elements.append(Paragraph("<b>Phase 2 \u2014 New Buckets</b> (Week 2, ~45 minutes)", styles['SubHead']))

    p2_tbl = make_table(
        ["Action", "Bucket", "Details", "Impact"],
        [
            ["Create Attempted list", "Attempted (NEW)",
             "Stage=Lead + Created >10d + LastComm 5\u201345d, every 5 days",
             "Fills 169-contact gap"],
            ["Adjust Unresponsive", "Unresponsive",
             "LastComm threshold 14d \u2192 45d",
             "Eliminates surge pattern"],
            ["Expand Timeframe Empty", "Timeframe Empty",
             "Add Stage=Lead to filter",
             "+160 Leads needing qualification"],
        ],
        col_widths=[1.3*inch, 1.3*inch, 2.2*inch, 1.7*inch]
    )
    elements.append(p2_tbl)
    elements.append(Spacer(1, 0.15*inch))

    # Phase 3
    elements.append(Paragraph("<b>Phase 3 \u2014 Refinement</b> (Weeks 3\u20134)", styles['SubHead']))

    p3_bullets = [
        "Tighten New Leads window from 14 to 10 days for cleaner handoff to Attempted",
        "Review Active Pipeline cadence based on team feedback (is every 3 days right?)",
        "Consider adding IDX activity tags to inform Hot list beyond stage + timeframe",
    ]
    for b in p3_bullets:
        elements.append(Paragraph(b, styles['BulletBody'], bulletText='\u2022'))

    elements.append(Spacer(1, 0.15*inch))

    # Phase 4
    elements.append(Paragraph("<b>Phase 4 \u2014 Ongoing Monitoring</b>", styles['SubHead']))

    p4_tbl = make_table(
        ["Action", "Frequency", "Purpose"],
        [
            ["Bucket population audit", "Weekly (first month), then monthly",
             "Verify counts match projections"],
            ["Threshold tuning", "Monthly",
             "Adjust lastComm thresholds based on call capacity"],
            ["Surge monitoring", "After each bulk action plan",
             "Confirm Attempted absorbs the load"],
            ["Stage hygiene", "Monthly",
             "Move stale Active Clients to Nurture, close completed deals"],
        ],
        col_widths=[1.5*inch, 1.8*inch, 3.2*inch]
    )
    elements.append(p4_tbl)

    elements.append(Spacer(1, 0.3*inch))

    # Closing
    elements.append(Paragraph(
        "The framework we\u2019ve built is strong. These adjustments are about tuning the instrument, "
        "not replacing it. Every recommendation aligns with FUB\u2019s own best practices and can be "
        "implemented without disrupting the team\u2019s existing Power Hour workflow.",
        styles['Callout']))

    return elements


def add_footer(canvas, doc):
    """Page footer with branding."""
    canvas.saveState()
    width, height = letter

    # Footer line
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.5)
    canvas.line(0.75*inch, 0.55*inch, width - 0.75*inch, 0.55*inch)

    # Left: team name
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MED_GRAY)
    canvas.drawString(0.75*inch, 0.38*inch, "Jon Tharp Homes  |  Smart List Optimization")

    # Right: page number
    canvas.drawRightString(width - 0.75*inch, 0.38*inch,
                           f"Page {doc.page}")

    # Confidential
    canvas.setFont('Helvetica', 7)
    canvas.drawCentredString(width / 2, 0.38*inch, "Confidential \u2014 Internal Use Only")

    canvas.restoreState()


def add_first_page_footer(canvas, doc):
    """Cover page has minimal footer."""
    canvas.saveState()
    width, height = letter
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MED_GRAY)
    canvas.drawCentredString(width / 2, 0.38*inch, "Confidential \u2014 Internal Use Only")
    canvas.restoreState()


def generate_report(output_path=None):
    """Build the complete PDF report."""
    if output_path is None:
        output_path = str(OUTPUT_DIR / "FUB_Smart_List_Optimization_Report.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )

    styles = build_styles()
    elements = []

    # Build all sections
    elements.extend(build_cover(styles))
    elements.extend(build_executive_summary(styles))
    elements.extend(build_how_smartlists_work(styles))
    elements.extend(build_bucket_analysis(styles))
    elements.extend(build_coverage_gap(styles))
    elements.extend(build_five_patterns(styles))
    elements.extend(build_best_practices(styles))
    elements.extend(build_recommendations(styles))
    elements.extend(build_before_after(styles))
    elements.extend(build_implementation(styles))

    # Build PDF
    doc.build(elements,
              onFirstPage=add_first_page_footer,
              onLaterPages=add_footer)

    print(f"Report generated: {output_path}")
    return output_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate FUB Smart List Optimization PDF")
    parser.add_argument('--output', '-o', help="Output file path",
                        default=None)
    args = parser.parse_args()
    generate_report(args.output)
