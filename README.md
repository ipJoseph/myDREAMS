# Integrity Dev OS

This repo is the baseline operating system for building and managing Integrity Pursuits projects.

## What this repo is
- A reusable template for new apps and automation projects
- A consistent VS Code + Python + venv setup
- A place for project standards: decisions, runbooks, and patterns

## Quick start
1) Create and activate the virtual environment
   - python3 -m venv .venv
   - source .venv/bin/activate
2) Run the smoke test
   - python hello.py

## Repo structure (to be built next)
- docs/decisions/        Architecture decisions (ADRs)
- docs/runbooks/         Setup, deploy, rollback, common fixes
- docs/patterns/         Reusable prompts, templates, code patterns
- apps/                  Production apps
- tools/                 Scripts and automation

## Standards
- Use a project-local .venv
- Keep secrets in .env (never commit)
- Default branch: main

