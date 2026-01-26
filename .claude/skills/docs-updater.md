# Documentation Updater Skill

Keep myDREAMS documentation in sync with code changes.

## Activation

Use this skill when:
- Code changes are made that affect documentation
- After completing a feature
- When asked to update docs
- Before committing significant changes

## Documentation Files

| File | Purpose | When to Update |
|------|---------|----------------|
| `CHANGELOG.md` | Version history | After completing features/fixes |
| `docs/ROADMAP.md` | Progress tracking | After completing roadmap items |
| `docs/TODO.md` | Task list | When tasks are completed |
| `docs/ARCHITECTURE.md` | System design | When architecture changes |
| `docs/DATA_DICTIONARY.md` | Database fields | When schema changes |
| `README.md` | Quick start | When setup process changes |

## CHANGELOG.md Format

Location: `/home/bigeug/myDREAMS/CHANGELOG.md`

```markdown
## [Unreleased]

### Added
- New feature description

### Changed
- Modified behavior description

### Fixed
- Bug fix description

### Removed
- Removed feature description

---

## [1.x.x] - YYYY-MM-DD

### Added
...
```

### Categories
- **Added**: New features
- **Changed**: Changes to existing features
- **Deprecated**: Features marked for removal
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security improvements

## ROADMAP.md Updates

Location: `/home/bigeug/myDREAMS/docs/ROADMAP.md`

When a feature is completed:
1. Find the feature in the roadmap
2. Change status from `Pending` to `DONE`
3. Add completion date if applicable
4. Move to completed section if exists

## TODO.md Updates

Location: `/home/bigeug/myDREAMS/docs/TODO.md`

When a task is completed:
1. Find the task in the appropriate priority section
2. Change Status from `Pending` to `DONE`
3. Add notes about implementation
4. Add to "Completed Items" section with date

## Workflow

### After Feature Completion

1. **Read** the relevant documentation files
2. **Update** CHANGELOG.md with new entry under [Unreleased]
3. **Update** ROADMAP.md if feature was on roadmap
4. **Update** TODO.md if task was listed
5. **Update** README.md if user-facing changes

### Example: After Adding Dark Mode

```markdown
# CHANGELOG.md addition:

## [Unreleased]

### Added
- Dark mode support with system preference detection
  - Toggle in `/admin/settings`
  - Respects `prefers-color-scheme` media query
  - Persists preference in localStorage
```

```markdown
# TODO.md update:

| 18 | **Dark mode support** | DONE | Phase 4 | CSS variables, localStorage persistence |
```

### Before Version Release

1. Move all [Unreleased] entries to new version section
2. Add version number and date
3. Update version numbers in code if needed
4. Create git tag

## Templates

### New Feature Entry
```markdown
- **Feature Name** - Brief description
  - Detail 1
  - Detail 2
  - Related file: `path/to/file.py`
```

### Bug Fix Entry
```markdown
- Fix issue where [description of bug] (#issue-number if applicable)
```

### Breaking Change Entry
```markdown
- **BREAKING**: Description of breaking change
  - Migration: How to update
```

## Style Guidelines

- Use present tense ("Add feature" not "Added feature")
- Be specific but concise
- Reference files/functions when relevant
- Group related changes together
- Include migration notes for breaking changes

## Commands

Check if documentation needs updates:
```bash
# See recent commits not yet in changelog
git log --oneline HEAD~10..HEAD
```

Update last-updated date in doc:
```bash
# Add date to file header
date +"%B %d, %Y"  # e.g., "January 25, 2026"
```
