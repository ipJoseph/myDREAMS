---
description: Generate session handoff summary
---

# Session Handoff

Generate a summary of the current session for continuity into the next conversation.

## Instructions

Create a handoff document covering everything the next session needs to know. Gather information from:

1. **Git changes this session**: Run `git log --oneline -20` and `git diff --stat HEAD~5..HEAD` to see what was built/changed
2. **Current state**: Run `git status` to check for uncommitted work
3. **PRD vs DEV**: Run `ssh root@178.156.221.10 'git -C /opt/mydreams log --oneline -1'` to compare what's deployed vs what's in DEV
4. **Open items**: Check `docs/TODO.md` for relevant in-progress tasks

## Output Format

```markdown
# Session Handoff - [Date]

## What Was Done
- [Bullet list of completed work with commit references]

## Current State
- **Uncommitted changes**: [yes/no, what]
- **DEV ahead of PRD by**: [N commits]
- **Needs PRD deploy**: [yes/no, what specifically]

## In Progress / Blockers
- [Any work started but not finished]
- [Blockers or decisions needed]

## Next Session Priorities
- [Suggested next steps based on TODO.md and current momentum]
```

## Notes

- Be specific about what changed, not vague
- Include file paths for in-progress work
- If database schema changed, note whether PRD DB needs migration
- Check if any new .env variables were added that PRD needs

## Argument

$ARGUMENTS - Optional: additional context to include in the handoff
