# ADR 0002: Vendor Directory Application

Date: 2025-12-18  
Status: Accepted

## Context
Integrity Pursuits needs a lightweight way to track professional vendors
(attorneys, lenders, inspectors, contractors, agents) with notes and contact history.

This tool must be:
- Simple to use
- Local-first
- Easy to evolve without rework

## Decision
We will build the Vendor Directory as:
- A Python CLI application
- Using SQLite as the initial data store
- With a simple schema owned by the application
- No web UI in v1

Data will live locally in the repo (or a configurable path).
Future versions may migrate to Postgres or expose an API.

## Consequences
- Zero infrastructure required to get value
- Easy testing and iteration
- Clear upgrade path without premature complexity
