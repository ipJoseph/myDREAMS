# Assistant Roles and Lanes

This document defines how different AI assistants are used inside Integrity Dev OS.
Each assistant has a clear lane. Overlap is intentional but constrained.

---

## Copilot (IDE Assistant)
Primary role:
- Inline code completion
- Small refactors
- Boilerplate generation
- Tests and docstrings

Rules:
- Operates only within files opened in the IDE
- Must follow existing code style and ADRs
- Should not introduce new tools or frameworks without instruction

When to use:
- Writing or modifying code
- Cleaning up repetitive patterns
- Implementing clearly-defined tasks

---

## Research Assistant (Perplexity or equivalent)
Primary role:
- Current best practices
- Library comparisons
- Linux, cloud, and tooling research
- Verifying up-to-date facts

Rules:
- Does not write production code
- Outputs summaries, links, and tradeoffs
- Must frame findings in terms of existing ADR constraints

When to use:
- “What is the current state of…”
- “Compare these options…”
- “What changed recently in…”
- Risk and feasibility research

---

## Architecture Assistant (Claude-style reasoning)
Primary role:
- System design
- Tradeoff analysis
- Long-form reasoning
- Drafting ADRs and design docs

Rules:
- Proposes options, not defaults
- Must reference or suggest updates to ADRs
- Avoids premature optimization

When to use:
- Designing new systems or subsystems
- Evaluating architectural changes
- Writing decision documents

---

## Orchestrator (Auggie)
Primary role:
- System coherence
- Workflow design
- Translating goals into structured steps
- Enforcing standards and constraints

Rules:
- Treats ADRs as authoritative
- Keeps work incremental and verifiable
- Stops scope creep early

When to use:
- Planning work
- Resolving conflicts between assistants
- Designing processes and operating models
