---
description: Security and quality code review
---

# Code Review

Perform security and quality analysis on myDREAMS code.

## Instructions

Follow the code-review skill guidelines in `.claude/skills/code-review.md`.

When the user provides a file or module path:

1. Read the target file(s)
2. Check against security checklist (SQL injection, XSS, auth, CSRF, etc.)
3. Check against quality checklist (structure, error handling, logging, etc.)
4. Identify specific line numbers for each issue
5. Categorize findings by severity (CRITICAL, HIGH, MEDIUM, LOW)
6. Provide fix recommendations

## Output Format

Provide a structured review with:
- Summary (1-2 sentences)
- Security Issues table
- Quality Issues table
- Positive notes
- Priority recommendations

## Argument

$ARGUMENTS - Path to file or directory to review, or "all" for full project scan
