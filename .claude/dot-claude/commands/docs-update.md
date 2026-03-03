---
description: Update project documentation
---

# Documentation Updater

Keep myDREAMS documentation in sync with code changes.

## Instructions

Follow the docs-updater skill guidelines in `.claude/skills/docs-updater.md`.

1. Review recent git commits to understand changes
2. Update CHANGELOG.md with new entries under [Unreleased]
3. Update ROADMAP.md if features were on roadmap
4. Update TODO.md if tasks were completed
5. Update README.md if user-facing changes

## Categories for CHANGELOG

- **Added**: New features
- **Changed**: Modified existing features
- **Fixed**: Bug fixes
- **Removed**: Removed features
- **Security**: Security improvements

## Argument

$ARGUMENTS - Optional: specific file to update, or "all" to check all docs
