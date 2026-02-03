"""Project templates for buyer journey phases.

Each phase (QUALIFY, CURATE, ACQUIRE, CLOSE) has a project template with:
- Milestones marking phase gates
- Pre-defined issues (tasks) within each milestone
- Priority levels and descriptions

Templates are defined in code and instantiated programmatically via the Linear API.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from .models import BuyerPhase, ProcessGroup, LinearPriority


@dataclass
class IssueTemplate:
    """Template for an issue within a milestone."""
    title: str
    priority: int = LinearPriority.MEDIUM.value  # 0=none, 1=urgent, 2=high, 3=medium, 4=low
    description: str = ''
    task_type: str = 'Todo'  # For FUB sync: Call, Email, Showing, Todo, etc.


@dataclass
class MilestoneTemplate:
    """Template for a milestone within a project."""
    name: str
    issues: list[IssueTemplate] = field(default_factory=list)
    description: str = ''


@dataclass
class ProjectTemplate:
    """Template for a buyer journey phase project."""
    phase: BuyerPhase
    name_suffix: str  # e.g., "QUALIFY" -> "Smith Family - QUALIFY"
    process_group: ProcessGroup  # Which Linear team this belongs to
    milestones: list[MilestoneTemplate] = field(default_factory=list)
    description: str = ''


# =============================================================================
# QUALIFY TEMPLATE
# Lead qualification - discovering if they're ready, willing, and able to buy
# =============================================================================

QUALIFY_TEMPLATE = ProjectTemplate(
    phase=BuyerPhase.QUALIFY,
    name_suffix='QUALIFY',
    process_group=ProcessGroup.DEVELOP,
    description='Lead qualification phase: Discover timeline, motivation, and financial readiness.',
    milestones=[
        MilestoneTemplate(
            name='Initial Contact',
            description='Make first contact and establish rapport.',
            issues=[
                IssueTemplate(
                    title='First response/call back',
                    priority=LinearPriority.HIGH.value,
                    description='Respond to lead within 5 minutes if possible. Speed to lead matters!',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Introduce myself and the team',
                    priority=LinearPriority.MEDIUM.value,
                    description='Brief intro: who I am, how I help buyers, what to expect.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Schedule discovery call',
                    priority=LinearPriority.HIGH.value,
                    description='Set up a dedicated time to discuss their home search in depth.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Discovery',
            description='Understand their situation, timeline, and motivation.',
            issues=[
                IssueTemplate(
                    title='Discovery call completed',
                    priority=LinearPriority.HIGH.value,
                    description='Conducted in-depth conversation about their home search goals.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Timeline established',
                    priority=LinearPriority.MEDIUM.value,
                    description='When do they need/want to move? Any lease expirations or contingencies?',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Motivation understood',
                    priority=LinearPriority.MEDIUM.value,
                    description='Why are they moving? Job relocation, growing family, investment, lifestyle?',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Pre-approval status checked',
                    priority=LinearPriority.HIGH.value,
                    description='Are they pre-approved? If not, do they have a lender? Refer if needed.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Qualification',
            description='Confirm they are ready, willing, and able to proceed.',
            issues=[
                IssueTemplate(
                    title='Pre-approval letter obtained',
                    priority=LinearPriority.HIGH.value,
                    description='Get copy of pre-approval letter or confirmation from lender.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Buyer agency agreement signed',
                    priority=LinearPriority.URGENT.value,
                    description='Execute buyer representation agreement. Required before showing properties.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Added to IDX property alerts',
                    priority=LinearPriority.MEDIUM.value,
                    description='Set up saved search on JonTharpHomes.com based on initial criteria.',
                    task_type='Todo',
                ),
            ],
        ),
    ],
)


# =============================================================================
# CURATE TEMPLATE
# Property search - helping them find the right home
# =============================================================================

CURATE_TEMPLATE = ProjectTemplate(
    phase=BuyerPhase.CURATE,
    name_suffix='CURATE',
    process_group=ProcessGroup.DEVELOP,
    description='Property search phase: Capture requirements, search, show, and refine until ready to offer.',
    milestones=[
        MilestoneTemplate(
            name='Requirements Capture',
            description='Document detailed requirements and preferences.',
            issues=[
                IssueTemplate(
                    title='Buyer intake form completed',
                    priority=LinearPriority.HIGH.value,
                    description='Have client complete detailed intake form with all requirements.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Must-haves vs nice-to-haves defined',
                    priority=LinearPriority.MEDIUM.value,
                    description='Distinguish non-negotiables from preferences. Document deal-breakers.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Budget confirmed with lender',
                    priority=LinearPriority.HIGH.value,
                    description='Verify purchase price range and monthly payment comfort level.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Target areas identified',
                    priority=LinearPriority.MEDIUM.value,
                    description='Which neighborhoods, school districts, or areas are they considering?',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Active Search',
            description='Actively searching and curating property options.',
            issues=[
                IssueTemplate(
                    title='Initial property list curated',
                    priority=LinearPriority.HIGH.value,
                    description='Compile first batch of properties matching their criteria.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='First showing tour scheduled',
                    priority=LinearPriority.HIGH.value,
                    description='Schedule first round of property showings.',
                    task_type='Showing',
                ),
                IssueTemplate(
                    title='Feedback system established',
                    priority=LinearPriority.LOW.value,
                    description='Set up way to collect and track feedback after each showing.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Showings',
            description='Conducting showings and gathering feedback.',
            issues=[
                IssueTemplate(
                    title='Showing round 1 completed',
                    priority=LinearPriority.HIGH.value,
                    description='First batch of showings done. Collect feedback and refine criteria.',
                    task_type='Showing',
                ),
                IssueTemplate(
                    title='Criteria refined based on feedback',
                    priority=LinearPriority.MEDIUM.value,
                    description='Adjust search parameters based on what they liked/disliked.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Top choices identified',
                    priority=LinearPriority.HIGH.value,
                    description='Narrow down to 2-3 properties they would consider making an offer on.',
                    task_type='Todo',
                ),
            ],
        ),
    ],
)


# =============================================================================
# ACQUIRE TEMPLATE
# Offer & negotiation - making and negotiating offers
# Property address should be included in project name
# =============================================================================

ACQUIRE_TEMPLATE = ProjectTemplate(
    phase=BuyerPhase.ACQUIRE,
    name_suffix='ACQUIRE',
    process_group=ProcessGroup.TRANSACT,
    description='Offer phase: Draft, submit, and negotiate offer to acceptance.',
    milestones=[
        MilestoneTemplate(
            name='Offer Preparation',
            description='Prepare and draft the offer.',
            issues=[
                IssueTemplate(
                    title='CMA completed',
                    priority=LinearPriority.HIGH.value,
                    description='Complete comparative market analysis to determine offer price strategy.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Offer strategy discussed',
                    priority=LinearPriority.HIGH.value,
                    description='Discuss offer terms: price, earnest money, closing date, contingencies.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Offer drafted',
                    priority=LinearPriority.URGENT.value,
                    description='Prepare purchase agreement with all agreed terms.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Client reviewed and signed offer',
                    priority=LinearPriority.URGENT.value,
                    description='Client reviews, asks questions, and signs the offer documents.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Negotiation',
            description='Submit offer and negotiate to acceptance.',
            issues=[
                IssueTemplate(
                    title='Offer submitted to listing agent',
                    priority=LinearPriority.URGENT.value,
                    description='Submit offer package to listing agent. Document submission time.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Counter offer received',
                    priority=LinearPriority.HIGH.value,
                    description='Review counter offer with client and prepare response.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Counter response sent',
                    priority=LinearPriority.HIGH.value,
                    description='Send counter response or acceptance.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Mutual acceptance reached',
                    priority=LinearPriority.URGENT.value,
                    description='Offer accepted! Get fully executed contract and confirm effective date.',
                    task_type='Todo',
                ),
            ],
        ),
    ],
)


# =============================================================================
# CLOSE TEMPLATE
# Under contract to closing - managing the transaction to close
# Property address should be included in project name
# =============================================================================

CLOSE_TEMPLATE = ProjectTemplate(
    phase=BuyerPhase.CLOSE,
    name_suffix='CLOSE',
    process_group=ProcessGroup.TRANSACT,
    description='Closing phase: Manage all steps from accepted offer to keys in hand.',
    milestones=[
        MilestoneTemplate(
            name='Contract Execution',
            description='Initial steps after offer acceptance.',
            issues=[
                IssueTemplate(
                    title='Earnest money deposited',
                    priority=LinearPriority.URGENT.value,
                    description='Ensure earnest money is deposited within contract deadline.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Contract sent to lender',
                    priority=LinearPriority.HIGH.value,
                    description='Send executed contract to lender to start loan process.',
                    task_type='Email',
                ),
                IssueTemplate(
                    title='Contract sent to title company',
                    priority=LinearPriority.HIGH.value,
                    description='Send executed contract to title company to start title work.',
                    task_type='Email',
                ),
                IssueTemplate(
                    title='Due diligence timeline documented',
                    priority=LinearPriority.MEDIUM.value,
                    description='Create timeline with all contract deadlines. Share with client.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Due Diligence',
            description='Inspections, appraisal, and contingency period.',
            issues=[
                IssueTemplate(
                    title='Home inspection scheduled',
                    priority=LinearPriority.URGENT.value,
                    description='Schedule home inspection within contingency period.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Inspection completed',
                    priority=LinearPriority.HIGH.value,
                    description='Attend inspection, receive report, review with client.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Repair request submitted',
                    priority=LinearPriority.HIGH.value,
                    description='Submit repair request/amendment based on inspection findings.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Repairs negotiated and agreed',
                    priority=LinearPriority.HIGH.value,
                    description='Negotiate repair credits or seller repairs. Get signed amendment.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Appraisal ordered',
                    priority=LinearPriority.HIGH.value,
                    description='Confirm lender has ordered appraisal.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Appraisal completed',
                    priority=LinearPriority.HIGH.value,
                    description='Receive appraisal report. Address any value issues if needed.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Financing',
            description='Loan approval and final underwriting.',
            issues=[
                IssueTemplate(
                    title='Loan processing complete',
                    priority=LinearPriority.HIGH.value,
                    description='All borrower documents submitted and processed.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Clear to close received',
                    priority=LinearPriority.URGENT.value,
                    description='Lender issues clear to close. Confirm with loan officer.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Closing disclosure reviewed',
                    priority=LinearPriority.HIGH.value,
                    description='Review CD with client. Verify numbers match expectations.',
                    task_type='Call',
                ),
                IssueTemplate(
                    title='Wire instructions received',
                    priority=LinearPriority.HIGH.value,
                    description='Get wire instructions from title company. VERIFY by phone!',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Closing',
            description='Final steps to close the transaction.',
            issues=[
                IssueTemplate(
                    title='Final walkthrough scheduled',
                    priority=LinearPriority.HIGH.value,
                    description='Schedule walkthrough within 24-48 hours of closing.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Final walkthrough completed',
                    priority=LinearPriority.HIGH.value,
                    description='Walk property with client. Verify condition and repairs.',
                    task_type='Showing',
                ),
                IssueTemplate(
                    title='Closing appointment confirmed',
                    priority=LinearPriority.HIGH.value,
                    description='Confirm closing time, location, and what to bring.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Closing attended',
                    priority=LinearPriority.URGENT.value,
                    description='Attend closing with client. Review and sign documents.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Keys handed over',
                    priority=LinearPriority.HIGH.value,
                    description='Congratulations! Hand over keys to new homeowner.',
                    task_type='Todo',
                ),
            ],
        ),
        MilestoneTemplate(
            name='Post-Closing',
            description='After the close - relationship building.',
            issues=[
                IssueTemplate(
                    title='Closing gift delivered',
                    priority=LinearPriority.MEDIUM.value,
                    description='Deliver closing gift within first week.',
                    task_type='Todo',
                ),
                IssueTemplate(
                    title='Review request sent',
                    priority=LinearPriority.MEDIUM.value,
                    description='Send request for Google/Zillow review after they settle in.',
                    task_type='Email',
                ),
                IssueTemplate(
                    title='Referral request made',
                    priority=LinearPriority.LOW.value,
                    description='Ask if they know anyone else looking to buy or sell.',
                    task_type='Call',
                ),
            ],
        ),
    ],
)


# =============================================================================
# TEMPLATE REGISTRY
# =============================================================================

PHASE_TEMPLATES: dict[BuyerPhase, ProjectTemplate] = {
    BuyerPhase.QUALIFY: QUALIFY_TEMPLATE,
    BuyerPhase.CURATE: CURATE_TEMPLATE,
    BuyerPhase.ACQUIRE: ACQUIRE_TEMPLATE,
    BuyerPhase.CLOSE: CLOSE_TEMPLATE,
}


def get_template(phase: BuyerPhase) -> ProjectTemplate:
    """Get the project template for a buyer phase."""
    return PHASE_TEMPLATES[phase]


def get_template_by_name(name: str) -> Optional[ProjectTemplate]:
    """Get template by name (case-insensitive)."""
    name_upper = name.upper()
    for phase, template in PHASE_TEMPLATES.items():
        if template.name_suffix.upper() == name_upper:
            return template
    return None


def list_templates() -> list[str]:
    """List available template names."""
    return [t.name_suffix for t in PHASE_TEMPLATES.values()]
