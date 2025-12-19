# ADR 0001: Integrity Dev OS Baseline

Date: 2025-12-18
Status: Accepted

## Context
Integrity Pursuits requires a repeatable, low-friction development environment that supports:
- Ubuntu + VS Code
- Python-first workflows
- GitHub-hosted projects
- Multiple AI assistants working from shared context

## Decision
We adopt the following baseline:
- VS Code as the primary IDE
- GitHub for source control and project spine
- Project-local Python virtual environments (.venv)
- Explicit interpreter pinning via .vscode/settings.json
- Minimal, opinionated defaults over heavy frameworks

## Consequences
- Faster project spin-up with fewer environment bugs
- Clear shared context for human and AI contributors
- Slight upfront discipline in maintaining docs and decisions
