#!/usr/bin/env python3
"""
FUB Smart List Optimization Report — PDF Generator (v2)

Generates a professionally branded PDF analyzing Follow Up Boss smart list
architecture and recommending improvements aligned with FUB best practices.

This version:
- Uses structural analysis (filter logic) rather than individual contact counts
- Frames the framework honestly — strengths AND limitations
- Positions recommendations as a team audit, not prescriptive mandates
- No personal data or agent-specific numbers

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
    HRFlowable, PageBreak, KeepTogether
)

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
    ))
    styles.add(ParagraphStyle(
        'SubHead', fontName='Times-Bold', fontSize=13, leading=17,
        textColor=NAVY, spaceBefore=12, spaceAfter=6
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
    return styles


def gold_rule():
    return HRFlowable(width="100%", thickness=1.5, color=GOLD,
                      spaceBefore=2, spaceAfter=8)


def navy_rule():
    return HRFlowable(width="100%", thickness=0.5, color=NAVY,
                      spaceBefore=2, spaceAfter=6)


def section_head(text, styles):
    return [Paragraph(text, styles['SectionHead']), gold_rule()]


def make_table(headers, rows, col_widths=None, highlight_col=None):
    """Build a branded table with navy header row."""
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
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (0, i), (-1, i), LIGHT_GRAY))
    if highlight_col is not None:
        for i in range(1, len(data)):
            cmds.append(('BACKGROUND', (highlight_col, i), (highlight_col, i),
                          LIGHT_GOLD))
    tbl.setStyle(TableStyle(cmds))
    return tbl


def stat_box(number, label, styles):
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


# ══════════════════════════════════════════════════════════════════════
# CONTENT SECTIONS
# ══════════════════════════════════════════════════════════════════════

def build_cover(styles):
    elements = []
    elements.append(Spacer(1, 1.5*inch))

    elements.append(Paragraph("Smart List Optimization", styles['CoverTitle']))
    elements.append(Paragraph("A Structural Analysis", styles['CoverTitle']))
    elements.append(Spacer(1, 0.15*inch))
    elements.append(gold_rule())
    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph(
        "Strengthening Our Follow Up Boss Configuration for Better Coverage",
        styles['CoverSubtitle']))
    elements.append(Spacer(1, 0.5*inch))

    elements.append(Paragraph("Jon Tharp Homes  |  Keller Williams", styles['CoverMeta']))
    elements.append(Paragraph(datetime.now().strftime("February %Y"), styles['CoverMeta']))
    elements.append(Paragraph("Confidential \u2014 Internal Use Only", styles['CoverMeta']))

    elements.append(Spacer(1, 1.2*inch))

    # Three framing stats — structural, not personal
    row_data = [[
        stat_box("3", "Filter Axes\nPer Bucket", styles),
        stat_box("7\u21928", "Current \u2192 Proposed\nBuckets", styles),
        stat_box("2", "Pipeline Stages\nWith No Coverage", styles),
    ]]
    preview = Table(row_data, colWidths=[2.2*inch, 2.2*inch, 2.2*inch])
    preview.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEAFTER', (0, 0), (1, 0), 0.5, MED_GRAY),
    ]))
    elements.append(preview)

    elements.append(Spacer(1, 0.8*inch))
    elements.append(Paragraph(
        "This report analyzes filter architecture, not individual agent data. "
        "Findings are based on FUB\u2019s published best practices and the structural "
        "logic of our smart list definitions. A team-wide audit is recommended "
        "to validate and calibrate.",
        styles['SmallNote']))

    elements.append(PageBreak())
    return elements


def build_executive_summary(styles):
    elements = []
    elements.extend(section_head("1. Executive Summary", styles))

    elements.append(Paragraph(
        "Our Follow Up Boss smart lists provide a solid daily discipline: seven "
        "priority-ordered buckets, worked to zero each Power Hour session. That workflow "
        "\u2014 the act of systematically clearing each list \u2014 is genuinely valuable. "
        "This analysis is not about replacing it.",
        styles['Body']))

    elements.append(Paragraph(
        "What this analysis does examine is a harder question: <b>are the filters feeding "
        "those lists surfacing the right contacts at the right time?</b> And an even harder one: "
        "is \u201cwho haven\u2019t I called recently?\u201d the only question our lists should be answering?",
        styles['Body']))

    elements.append(Paragraph(
        "The current system is built entirely around <b>communication cadence</b> \u2014 "
        "how long since the last call, text, or email. That\u2019s an important signal. But "
        "it\u2019s one-dimensional. It doesn\u2019t account for:",
        styles['Body']))

    limitations = [
        ("<b>Buyer intent</b> \u2014 A contact who viewed 40 properties yesterday gets the same "
         "treatment as one who registered six months ago and never returned. The lists have "
         "no concept of engagement intensity."),
        ("<b>Quality within buckets</b> \u2014 When an agent opens New Leads, it\u2019s a flat list. "
         "An $800K buyer with an urgent timeline sits next to a casual browser. There\u2019s no "
         "prioritization within the bucket."),
        ("<b>Speed-to-intent</b> \u2014 The system waits for communication to lapse before "
         "surfacing someone. It never says \u201ccall this person NOW because they\u2019re actively "
         "shopping.\u201d It only says \u201cyou haven\u2019t called this person in a while.\u201d"),
    ]
    for b in limitations:
        elements.append(Paragraph(b, styles['BulletBody'], bulletText='\u2022'))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph(
        "That said, the cadence model is the foundation we have, and it can be "
        "significantly improved without rebuilding anything. This report identifies "
        "<b>five structural gaps</b> in the current filter configuration \u2014 places where "
        "the architecture itself prevents contacts from surfacing \u2014 and proposes specific "
        "adjustments aligned with FUB\u2019s own recommended defaults.",
        styles['Body']))

    elements.append(Spacer(1, 0.08*inch))
    elements.append(Paragraph(
        "The recommendations fall into two categories: <b>quick fixes</b> (threshold "
        "adjustments, ~30 minutes in FUB settings) and <b>structural additions</b> "
        "(new buckets to close coverage gaps). We recommend a team-wide audit to validate "
        "these findings against each agent\u2019s actual contact distribution before implementing.",
        styles['Callout']))

    elements.append(PageBreak())
    return elements


def build_how_smartlists_work(styles):
    elements = []
    elements.extend(section_head("2. How the Current System Works", styles))

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
        "The workflow: open each list during Power Hour, work it to zero, move to the next. "
        "When a contact is called, they drop off (Last Communication resets) and reappear "
        "when their cadence comes due. This is a good discipline.",
        styles['Body']))

    elements.append(Paragraph(
        "But it only works when <b>every active contact can land in some bucket.</b> "
        "If the filter logic structurally excludes a contact from all seven lists, "
        "that contact is invisible to the workflow \u2014 not between touches, but "
        "permanently off the radar until something changes manually.",
        styles['Body']))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("<b>Current 7 Smart Lists</b>", styles['SubHead']))

    tbl2 = make_table(
        ["#", "Bucket", "Filter Logic", "Cadence"],
        [
            ["1", "New Leads", "Stage=Lead + Created <14d + LastComm >12hrs", "Daily"],
            ["2", "Priority", "Stage=Hot Prospect + LastComm >3d", "Semiweekly"],
            ["3", "Hot", "Stage=Nurture + Timeframe 0\u20133mo + LastComm >7d", "Weekly"],
            ["4", "Warm", "Stage=Nurture + Timeframe 3\u20136mo + LastComm >30d", "Monthly"],
            ["5", "Cool", "Stage=Nurture + Timeframe 6\u201312/12+/No Plans + LastComm >90d", "Quarterly"],
            ["6", "Unresponsive", "Stage=Lead + Created >14d + LastComm >14d", "Biweekly"],
            ["7", "Timeframe Empty", "Stage=Nurture + No timeframe set", "As needed"],
        ],
        col_widths=[0.3*inch, 1.1*inch, 3.5*inch, 1.0*inch]
    )
    elements.append(tbl2)

    elements.append(PageBreak())
    return elements


def build_bucket_analysis(styles):
    elements = []
    elements.extend(section_head("3. Bucket-by-Bucket Structural Analysis", styles))

    elements.append(Paragraph(
        "Each bucket is evaluated against FUB\u2019s recommended default configuration "
        "and the structural logic of its filters. The question for each: does this "
        "filter reliably surface the contacts it\u2019s intended to catch?",
        styles['Body']))

    buckets = [
        {
            'name': 'New Leads',
            'verdict': 'Effective',
            'verdict_color': SUCCESS,
            'summary': (
                "Captures fresh IDX registrations for immediate follow-up. Daily cadence "
                "aligns with speed-to-lead best practices. One consideration: FUB\u2019s "
                "recommended default window is <b>10 days</b> (ours is 14). A tighter window "
                "creates a cleaner handoff to downstream buckets and avoids overlap."
            ),
        },
        {
            'name': 'Priority',
            'verdict': 'Unused',
            'verdict_color': DANGER,
            'summary': (
                "Filters on Stage=Hot Prospect. If this stage is not actively used in the team\u2019s "
                "pipeline, this bucket will consistently return zero contacts. The semiweekly cadence "
                "\u2014 the second-most-aggressive in the system \u2014 is effectively wasted. "
                "<b>Audit question: does any agent actively use the Hot Prospect stage? If not, "
                "this slot should be repurposed.</b>"
            ),
        },
        {
            'name': 'Hot',
            'verdict': 'Partially Effective',
            'verdict_color': WARNING,
            'summary': (
                "Catches Nurture contacts with a 0\u20133 month timeframe who haven\u2019t been contacted "
                "in 7 days. For that specific slice, it works. The structural limitation: "
                "<b>it only sees the Nurture stage.</b> A Lead or Active Client with intense "
                "website activity will never appear here. The filter captures one dimension "
                "(timeframe urgency) but misses another (behavioral urgency)."
            ),
        },
        {
            'name': 'Warm',
            'verdict': 'Threshold Misaligned',
            'verdict_color': WARNING,
            'summary': (
                "Targets Nurture contacts in the 3\u20136 month window. Conceptually sound. "
                "The issue: our <b>30-day lastComm threshold is twice FUB\u2019s recommended "
                "default of 14 days</b>. In a 3\u20136 month buying window, a full month of silence "
                "risks losing engagement to a more responsive agent. FUB recommends biweekly "
                "contact for this tier."
            ),
        },
        {
            'name': 'Cool',
            'verdict': 'Severely Restrictive',
            'verdict_color': DANGER,
            'summary': (
                "The concept is right: longer-timeframe contacts need less frequent touch. "
                "But the <b>90-day lastComm threshold is 3\u00d7 stricter than FUB\u2019s recommended "
                "30-day default</b>. Any agent who contacts their cool leads even once a quarter "
                "will see virtually no one on this list. This is likely the single highest-impact "
                "threshold to adjust."
            ),
        },
        {
            'name': 'Unresponsive',
            'verdict': 'Surge Risk',
            'verdict_color': WARNING,
            'summary': (
                "Surfaces leads created >14 days ago with no communication in 14 days. The "
                "structural concern: <b>when bulk action plans fire, they reset lastComm for "
                "large batches simultaneously.</b> Exactly 14 days later, the entire batch crosses "
                "the threshold on the same day. The list swings between nearly empty and "
                "overwhelmingly full. FUB recommends a 30-day threshold for this tier."
            ),
        },
        {
            'name': 'Timeframe Empty',
            'verdict': 'Too Narrow',
            'verdict_color': WARNING,
            'summary': (
                "Good concept \u2014 flagging contacts who need a buying timeline captured so the "
                "team can prioritize qualification calls. But it\u2019s scoped to <b>Nurture stage "
                "only</b>. Most Nurture contacts already have timeframes (they were qualified to "
                "get to Nurture). It\u2019s <i>Leads</i> who overwhelmingly lack timeframes \u2014 and "
                "they\u2019re the ones most needing that qualification call."
            ),
        },
    ]

    for b in buckets:
        name_para = Paragraph(f"<b>{b['name']}</b>", styles['SubHead'])

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


def build_structural_gaps(styles):
    """Section 4: The five structural gaps — architecture, not data."""
    elements = []
    elements.extend(section_head("4. Five Structural Gaps", styles))

    elements.append(Paragraph(
        "These are architectural issues in the filter logic itself \u2014 they exist "
        "regardless of individual agent contact counts. Each can be verified by "
        "examining the filter definitions.",
        styles['Body']))

    # Gap 1
    elements.append(Paragraph("<b>1. The Lead Transition Dead Zone</b>", styles['SubHead']))
    elements.append(Paragraph(
        "New Leads catches Stage=Lead contacts created within 14 days. Unresponsive catches "
        "Stage=Lead contacts created over 14 days ago with lastComm over 14 days. "
        "<b>What about a lead created 20 days ago who was contacted 5 days ago?</b> "
        "Too old for New Leads, too recently contacted for Unresponsive. They\u2019re in "
        "no bucket. Not between touches \u2014 structurally excluded.",
        styles['Body']))
    elements.append(Paragraph(
        "Any lead that ages past 14 days and is in active follow-up (drip sequence, "
        "recent manual call) falls into this gap. Depending on team outreach volume, "
        "this could be a handful of contacts or the majority of the Lead stage.",
        styles['CalloutGold']))

    # Gap 2
    elements.append(Paragraph("<b>2. Revenue Stages Have No Bucket</b>", styles['SubHead']))
    elements.append(Paragraph(
        "Examine the seven filter definitions above. The stages covered are: "
        "<b>Lead</b> (New Leads, Unresponsive), <b>Hot Prospect</b> (Priority), and "
        "<b>Nurture</b> (Hot, Warm, Cool, Timeframe Empty). Notably absent:",
        styles['Body']))

    missing_tbl = make_table(
        ["Stage", "Description", "Bucket Coverage"],
        [
            ["Active Client", "Actively searching, showing properties, writing offers", "None"],
            ["Under Contract", "Offer accepted, moving toward closing", "None"],
        ],
        col_widths=[1.4*inch, 3.3*inch, 1.8*inch]
    )
    elements.append(missing_tbl)
    elements.append(Spacer(1, 0.08*inch))
    elements.append(Paragraph(
        "These are the contacts closest to generating revenue. Their follow-up timing \u2014 "
        "checking in on inspections, appraisals, financing contingencies, showing feedback "
        "\u2014 currently relies on agent memory. No smart list prompts a check-in.",
        styles['Callout']))

    # Gap 3
    elements.append(Paragraph("<b>3. The Timeframe Chicken-and-Egg</b>", styles['SubHead']))
    elements.append(Paragraph(
        "Hot, Warm, and Cool all require the Timeframe field to be populated. "
        "Timeframe Empty \u2014 the bucket designed to flag contacts needing that field \u2014 "
        "only covers the Nurture stage. But contacts are typically in the <b>Lead stage</b> "
        "when they need qualification. The cycle:",
        styles['Body']))

    cycle = [
        "To appear on Hot/Warm/Cool \u2192 a contact needs a timeframe set",
        "To get a timeframe set \u2192 someone needs to make a qualification call",
        "To prompt that call \u2192 the contact needs to appear on a list",
        "To appear on Timeframe Empty \u2192 the contact must be in Nurture (but they\u2019re a Lead)",
    ]
    for c in cycle:
        elements.append(Paragraph(c, styles['BulletBody'], bulletText='\u2192'))

    elements.append(Paragraph(
        "Leads without timeframes can\u2019t enter the Nurture-stage buckets, and the one "
        "bucket that could prompt their qualification doesn\u2019t include their stage.",
        styles['CalloutGold']))

    # Gap 4
    elements.append(Paragraph(
        "<b>4. Threshold Misalignment with FUB Defaults</b>", styles['SubHead']))
    elements.append(Paragraph(
        "FUB publishes recommended default thresholds. Three of our settings deviate significantly:",
        styles['Body']))

    thresh_tbl = make_table(
        ["Bucket", "FUB Default", "Our Setting", "Effect"],
        [
            ["Warm", "14 days", "30 days", "Contacts stay invisible 2\u00d7 longer than recommended"],
            ["Cool", "30 days", "90 days", "Contacts stay invisible 3\u00d7 longer than recommended"],
            ["Unresponsive", "30 days", "14 days", "Triggers 2\u00d7 earlier \u2014 catches drip contacts, not truly unresponsive"],
        ],
        col_widths=[1.1*inch, 1.1*inch, 1.1*inch, 3.2*inch]
    )
    elements.append(thresh_tbl)
    elements.append(Spacer(1, 0.08*inch))
    elements.append(Paragraph(
        "These aren\u2019t judgment calls \u2014 they\u2019re measurable deviations from the "
        "platform vendor\u2019s own recommendations. Aligning them is low-risk and high-return.",
        styles['Body']))

    # Gap 5
    elements.append(Paragraph(
        "<b>5. The Surge Pattern</b>", styles['SubHead']))
    elements.append(Paragraph(
        "When a bulk action plan fires (drip campaign, mass text, etc.), it resets "
        "lastComm for a large batch of contacts on the same day. With a 14-day "
        "Unresponsive threshold, the entire batch crosses the line simultaneously \u2014 "
        "creating a single-day spike that may be unworkable. The list alternates "
        "between near-empty and overwhelming, neither of which is useful.",
        styles['Body']))
    elements.append(Paragraph(
        "A longer threshold (e.g., 45 days) would spread re-entry over weeks instead "
        "of concentrating it on one day. The \u201cAttempted\u201d bucket proposed in Section 6 "
        "also absorbs this load.",
        styles['CalloutGold']))

    elements.append(PageBreak())
    return elements


def build_best_practices(styles):
    elements = []
    elements.extend(section_head("5. FUB Best Practices &amp; Industry Standards", styles))

    elements.append(Paragraph(
        "Follow Up Boss publishes recommended defaults for smart list thresholds. "
        "The following comparisons are based on those defaults and widely-cited "
        "industry cadence standards.",
        styles['Body']))

    elements.append(Paragraph("<b>Our Thresholds vs. FUB Defaults</b>", styles['SubHead']))

    tbl = make_table(
        ["Parameter", "FUB Default", "Our Setting", "Deviation"],
        [
            ["New Lead window", "10 days", "14 days", "4 days longer"],
            ["Warm lastComm", "14 days", "30 days", "2\u00d7 slower"],
            ["Cool lastComm", "30 days", "90 days", "3\u00d7 slower"],
            ["Unresponsive lastComm", "30 days", "14 days", "2\u00d7 faster"],
            ["Active Client bucket", "Recommended", "Not configured", "No coverage"],
        ],
        col_widths=[1.6*inch, 1.3*inch, 1.3*inch, 2.3*inch]
    )
    elements.append(tbl)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph("<b>Industry Cadence Standards</b>", styles['SubHead']))

    tbl2 = make_table(
        ["Contact Type", "Industry Standard", "Our Cadence", "Assessment"],
        [
            ["Speed-to-lead (new)", "Daily for 7\u201310 days", "Daily for 14 days", "Aligned"],
            ["Active buyer (0\u20133mo)", "Every 3\u20135 days", "Weekly", "Slightly slower"],
            ["Deal in progress", "Every 2\u20133 days", "No cadence", "Gap"],
            ["Warm pipeline (3\u20136mo)", "Biweekly", "Monthly", "2\u00d7 slower"],
            ["Long-term nurture", "Monthly", "Quarterly*", "Gap"],
            ["Unresponsive", "Monthly", "Biweekly**", "Execution gap"],
        ],
        col_widths=[1.6*inch, 1.4*inch, 1.5*inch, 2.0*inch]
    )
    elements.append(tbl2)
    elements.append(Paragraph(
        "* Cool\u2019s 90-day threshold means most contacts never appear. "
        "** Unresponsive cadence is biweekly, but surge pattern makes it unworkable on spike days.",
        styles['SmallNote']))

    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph("<b>What the Current Model Does Well</b>", styles['SubHead']))
    strengths = [
        "Speed-to-lead: New Leads at daily cadence is strong",
        "Timeframe segmentation: Hot/Warm/Cool separating by urgency is the right architecture",
        "The \u201czero out\u201d discipline: working lists systematically prevents leads from falling through the cracks",
    ]
    for s in strengths:
        elements.append(Paragraph(s, styles['BulletBody'], bulletText='\u2713'))

    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("<b>What\u2019s Missing from the Model</b>", styles['SubHead']))
    weaknesses = [
        "No behavioral signal: a contact\u2019s website activity doesn\u2019t influence their bucket placement",
        "No quality ranking within buckets: a high-value buyer is indistinguishable from a casual browser",
        "No revenue-stage coverage: the contacts closest to closing have the least systematic follow-up",
        "Thresholds that are stricter than the platform\u2019s own recommendations",
    ]
    for w in weaknesses:
        elements.append(Paragraph(w, styles['BulletBody'], bulletText='\u2022'))

    elements.append(PageBreak())
    return elements


def build_recommendations(styles):
    elements = []
    elements.extend(section_head("6. Recommended Configuration", styles))

    elements.append(Paragraph(
        "The proposed 8-bucket system preserves the existing zero-out workflow while "
        "closing the structural gaps identified above. Every change is either aligned "
        "with FUB\u2019s published defaults or addresses a documented coverage hole.",
        styles['Body']))

    tbl = make_table(
        ["#", "Bucket", "Filter", "Cadence", "What Changes"],
        [
            ["1", "New Leads", "Stage=Lead + Created <10d + LastComm >12hrs",
             "Daily", "Window 14d \u2192 10d (FUB default)"],
            ["2", "Active Pipeline", "Stage IN (Active Client, Under Contract) + LastComm >3d",
             "Every 3 days", "NEW \u2014 replaces unused Priority"],
            ["3", "Hot", "Nurture + Timeframe 0\u20133mo + LastComm >7d",
             "Weekly", "No change"],
            ["4", "Warm", "Nurture + Timeframe 3\u20136mo + LastComm >14d",
             "Biweekly", "Threshold 30d \u2192 14d (FUB default)"],
            ["5", "Cool", "Nurture + Timeframe 6+mo + LastComm >30d",
             "Monthly", "Threshold 90d \u2192 30d (FUB default)"],
            ["6", "Attempted", "Stage=Lead + Created >10d + LastComm 5\u201345d",
             "Every 5 days", "NEW \u2014 bridges transition gap"],
            ["7", "Unresponsive", "Stage=Lead + Created >10d + LastComm >45d",
             "Biweekly", "Threshold 14d \u2192 45d"],
            ["8", "Timeframe Empty", "Stage IN (Lead, Nurture) + No timeframe + LastComm >14d",
             "As needed", "Expanded to include Leads"],
        ],
        col_widths=[0.3*inch, 1.0*inch, 2.25*inch, 0.75*inch, 1.65*inch]
    )
    elements.append(tbl)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph("<b>Why These Changes</b>", styles['SubHead']))

    rationale = [
        ("<b>Active Pipeline replaces Priority</b> \u2014 If Hot Prospect isn\u2019t part of the "
         "active workflow, that semiweekly cadence slot is wasted. Active Clients and Under "
         "Contract contacts are the closest to revenue and currently have zero list coverage."),
        ("<b>Attempted fills the dead zone</b> \u2014 Any lead that\u2019s been contacted but hasn\u2019t "
         "responded yet falls between New Leads and Unresponsive. This bucket catches them "
         "during the active follow-up window."),
        ("<b>Three thresholds align to FUB defaults</b> \u2014 Warm (30d\u219214d), Cool (90d\u219230d), "
         "and New Leads (14d\u219210d) all move to the platform\u2019s own recommended settings."),
        ("<b>Unresponsive raised to 45 days</b> \u2014 At 14 days, contacts in active drip "
         "sequences flood the list. At 45 days, only genuinely unresponsive contacts appear. "
         "The Attempted bucket absorbs the transition period."),
        ("<b>Timeframe Empty expanded</b> \u2014 Including the Lead stage breaks the "
         "qualification chicken-and-egg: Leads without timeframes now surface for "
         "the calls that would set their timeframes."),
    ]
    for r in rationale:
        elements.append(Paragraph(r, styles['BulletBody'], bulletText='\u2022'))

    elements.append(PageBreak())
    return elements


def build_what_changes(styles):
    """Section 7: What this means structurally."""
    elements = []
    elements.extend(section_head("7. What This Changes Structurally", styles))

    elements.append(Paragraph(
        "Rather than projecting specific numbers (which vary by agent), here\u2019s what "
        "the architectural changes accomplish:",
        styles['Body']))

    changes_tbl = make_table(
        ["Gap", "Before", "After"],
        [
            ["Active Client / Under Contract coverage",
             "Zero buckets \u2014 relies on memory",
             "Active Pipeline bucket, every 3 days"],
            ["Lead transition (between New and Unresponsive)",
             "Dead zone \u2014 no bucket catches them",
             "Attempted bucket, every 5 days"],
            ["Cool lastComm threshold",
             "90 days (3\u00d7 FUB default)",
             "30 days (aligned with FUB default)"],
            ["Warm lastComm threshold",
             "30 days (2\u00d7 FUB default)",
             "14 days (aligned with FUB default)"],
            ["Unresponsive surge pattern",
             "14-day cliff syncs with bulk actions",
             "45-day threshold + Attempted absorbs transition"],
            ["Timeframe qualification loop",
             "Only Nurture (already qualified)",
             "Leads included \u2014 prompts the calls that set timeframes"],
            ["Stages with zero bucket coverage",
             "2 stages (Active Client, Under Contract)",
             "0 \u2014 full pipeline covered"],
            ["Pipeline stages covered by any bucket",
             "3 of 5 active stages",
             "5 of 5 active stages"],
        ],
        col_widths=[1.8*inch, 2.3*inch, 2.4*inch],
        highlight_col=2
    )
    elements.append(changes_tbl)
    elements.append(Spacer(1, 0.2*inch))

    elements.append(Paragraph(
        "The key shift: <b>every active contact now has a path into at least one bucket.</b> "
        "Before, some contacts were structurally excluded \u2014 no amount of time passing "
        "would surface them. After, any unbucketed contact is simply between cadence "
        "touches and will reappear on schedule.",
        styles['Callout']))

    elements.append(Spacer(1, 0.15*inch))

    elements.append(Paragraph("<b>The Bigger Opportunity</b>", styles['SubHead']))
    elements.append(Paragraph(
        "These recommendations optimize the current cadence-based model. But the highest-value "
        "improvement long-term would be layering in <b>behavioral signals</b> \u2014 website activity, "
        "property views, saved searches \u2014 so that a contact who\u2019s actively shopping surfaces "
        "for a call <i>because they\u2019re shopping</i>, not just because enough days have passed. "
        "That\u2019s a conversation for after the structural foundation is solid.",
        styles['Body']))

    elements.append(PageBreak())
    return elements


def build_implementation(styles):
    elements = []
    elements.extend(section_head("8. Implementation Plan", styles))

    elements.append(Paragraph(
        "A phased approach lets us capture quick wins, validate each change, and "
        "adjust before moving to the next phase.",
        styles['Body']))

    # Phase 1
    elements.append(Paragraph(
        "<b>Phase 1 \u2014 Threshold Alignment</b> (Week 1, ~30 minutes in FUB)", styles['SubHead']))
    elements.append(Paragraph(
        "Three filter edits to existing smart lists. No new lists needed. "
        "These bring our configuration in line with FUB\u2019s published defaults.",
        styles['Body']))

    p1_tbl = make_table(
        ["Action", "Bucket", "Change"],
        [
            ["Align Cool threshold", "Cool", "90 days \u2192 30 days"],
            ["Repurpose Priority", "Priority \u2192 Active Pipeline",
             "Stage=Hot Prospect \u2192 Stage IN (Active Client, Under Contract)"],
            ["Align Warm threshold", "Warm", "30 days \u2192 14 days"],
        ],
        col_widths=[1.5*inch, 1.5*inch, 3.5*inch]
    )
    elements.append(p1_tbl)
    elements.append(Spacer(1, 0.15*inch))

    # Phase 2
    elements.append(Paragraph(
        "<b>Phase 2 \u2014 Close Coverage Gaps</b> (Week 2, ~45 minutes)", styles['SubHead']))

    p2_tbl = make_table(
        ["Action", "Bucket", "Details"],
        [
            ["Create Attempted list", "Attempted (NEW)",
             "Stage=Lead + Created >10d + LastComm 5\u201345d, every 5 days"],
            ["Adjust Unresponsive", "Unresponsive",
             "LastComm threshold 14d \u2192 45d"],
            ["Expand Timeframe Empty", "Timeframe Empty",
             "Add Stage=Lead to filter criteria"],
        ],
        col_widths=[1.5*inch, 1.5*inch, 3.5*inch]
    )
    elements.append(p2_tbl)
    elements.append(Spacer(1, 0.15*inch))

    # Phase 3
    elements.append(Paragraph(
        "<b>Phase 3 \u2014 Refinement</b> (Weeks 3\u20134)", styles['SubHead']))
    p3 = [
        "Tighten New Leads window from 14 to 10 days (FUB default)",
        "Review Active Pipeline cadence with the team \u2014 is every 3 days the right fit?",
        "Evaluate whether IDX activity signals could inform bucket placement",
    ]
    for b in p3:
        elements.append(Paragraph(b, styles['BulletBody'], bulletText='\u2022'))

    elements.append(Spacer(1, 0.15*inch))

    # Phase 4
    elements.append(Paragraph("<b>Phase 4 \u2014 Ongoing</b>", styles['SubHead']))
    p4_tbl = make_table(
        ["Action", "Frequency", "Purpose"],
        [
            ["Bucket population check", "Weekly (month 1), then monthly",
             "Verify the changes are producing expected results"],
            ["Threshold tuning", "Monthly",
             "Adjust thresholds based on team call capacity"],
            ["Surge monitoring", "After each bulk action plan",
             "Confirm Attempted absorbs the transition load"],
            ["Stage hygiene", "Monthly",
             "Ensure contacts are in the correct pipeline stage"],
        ],
        col_widths=[1.5*inch, 1.8*inch, 3.2*inch]
    )
    elements.append(p4_tbl)

    elements.append(PageBreak())
    return elements


def build_next_steps(styles):
    """Section 9: Call to action — team audit."""
    elements = []
    elements.extend(section_head("9. Recommended Next Steps", styles))

    elements.append(Paragraph(
        "This analysis is based on filter architecture and FUB\u2019s published best "
        "practices. To move from analysis to action, we recommend:",
        styles['Body']))

    steps = [
        {
            'title': '1. Team Audit (30 minutes)',
            'detail': (
                "Each agent pulls up their smart lists in FUB and notes: how many contacts "
                "appear in each bucket? How many Active Clients and Under Contract contacts "
                "do they have? This gives us real team-wide numbers to validate the structural "
                "findings in this report."
            ),
        },
        {
            'title': '2. Confirm Hot Prospect Usage',
            'detail': (
                "If no one on the team actively uses the Hot Prospect stage, the Priority "
                "bucket is confirmed dead and can be repurposed. If someone does use it, "
                "we keep Priority and create Active Pipeline as an additional list."
            ),
        },
        {
            'title': '3. Phase 1 Implementation',
            'detail': (
                "If the audit confirms the gaps, the three threshold changes in Phase 1 can "
                "be made in a single ~30-minute session. These are the lowest-risk, "
                "highest-return adjustments: aligning our configuration with FUB\u2019s own "
                "recommended defaults."
            ),
        },
        {
            'title': '4. Measure and Iterate',
            'detail': (
                "After Phase 1, monitor bucket populations for two weeks. If the changes "
                "produce the expected results, proceed to Phase 2. If not, adjust before "
                "adding complexity."
            ),
        },
    ]

    for s in steps:
        elements.append(Paragraph(f"<b>{s['title']}</b>", styles['SubHead']))
        elements.append(Paragraph(s['detail'], styles['Body']))

    elements.append(Spacer(1, 0.2*inch))

    # Closing
    elements.append(Paragraph(
        "The daily zero-out workflow is a strong discipline that the team has built. "
        "The opportunity is in what feeds that workflow: the filter logic that decides "
        "who shows up and when. By aligning our thresholds with FUB\u2019s defaults "
        "and closing the structural coverage gaps, we can make sure every contact has "
        "a path onto a list \u2014 and that our highest-value relationships get the most "
        "systematic attention.",
        styles['Callout']))

    return elements


# ══════════════════════════════════════════════════════════════════════
# PDF ASSEMBLY
# ══════════════════════════════════════════════════════════════════════

def add_footer(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.5)
    canvas.line(0.75*inch, 0.55*inch, width - 0.75*inch, 0.55*inch)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(MED_GRAY)
    canvas.drawString(0.75*inch, 0.38*inch, "Jon Tharp Homes  |  Smart List Optimization")
    canvas.drawRightString(width - 0.75*inch, 0.38*inch, f"Page {doc.page}")
    canvas.setFont('Helvetica', 7)
    canvas.drawCentredString(width / 2, 0.38*inch, "Confidential \u2014 Internal Use Only")
    canvas.restoreState()


def add_first_page_footer(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(MED_GRAY)
    canvas.drawCentredString(width / 2, 0.38*inch, "Confidential \u2014 Internal Use Only")
    canvas.restoreState()


def generate_report(output_path=None):
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

    elements.extend(build_cover(styles))
    elements.extend(build_executive_summary(styles))
    elements.extend(build_how_smartlists_work(styles))
    elements.extend(build_bucket_analysis(styles))
    elements.extend(build_structural_gaps(styles))
    elements.extend(build_best_practices(styles))
    elements.extend(build_recommendations(styles))
    elements.extend(build_what_changes(styles))
    elements.extend(build_implementation(styles))
    elements.extend(build_next_steps(styles))

    doc.build(elements,
              onFirstPage=add_first_page_footer,
              onLaterPages=add_footer)

    print(f"Report generated: {output_path}")
    return output_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate FUB Smart List Optimization PDF")
    parser.add_argument('--output', '-o', help="Output file path", default=None)
    args = parser.parse_args()
    generate_report(args.output)
