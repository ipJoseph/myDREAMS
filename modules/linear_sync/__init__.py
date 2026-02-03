"""Linear Sync Module - Linear ↔ Follow Up Boss Task Sync

This module provides bidirectional synchronization between Linear (project management)
and Follow Up Boss (CRM), routing tasks to appropriate Linear teams based on
the real estate buyer journey:

Teams (Process Groups):
- DEVELOP: Lead development (Qualify + Curate phases)
- TRANSACT: Active deals (Acquire + Close phases)
- GENERAL: Admin, marketing, operations

Architecture:
- FUB tasks sync to Linear issues in the appropriate team
- Linear issues sync back to FUB tasks
- Person labels track clients across teams
- Projects in TRANSACT team track specific deals
"""

__version__ = "0.1.0"

# Dashboard integration exports (to be implemented)
# from .dashboard import (
#     get_linear_issues_for_dashboard,
#     get_issue_stats,
#     get_issues_by_team,
# )
