# myDREAMS Claude Code Commands

Custom slash commands for common myDREAMS development tasks.

## Available Commands

| Command | Description |
|---------|-------------|
| `/pdf` | Generate lead profile PDF |
| `/test-writer` | Generate pytest tests for code |
| `/code-review` | Security and quality analysis |
| `/docs-update` | Update CHANGELOG, ROADMAP, TODO |
| `/deploy` | Deploy to production VPS |

## Usage

Type the command in Claude Code:

```
/pdf Steve Legg
/test-writer src/core/database.py
/code-review apps/property-api/
/docs-update
/deploy
```

## Command Details

### /pdf
Generates professional PDF lead profiles.
- Searches lead by name, email, or ID
- Creates visually formatted PDF with scores, insights, recommendations
- Outputs to `output/<lead_name>_profile.pdf`
- Example: `/pdf Katie Boggs`

### /test-writer
Generates pytest tests following project conventions.
- Creates tests in `/tests/` mirroring source structure
- Uses fixtures for common setup
- Covers happy path, edge cases, and error cases
- Runs tests and reports coverage

### /code-review
Security and quality code review.
- Checks against security checklist (SQL injection, XSS, auth, etc.)
- Checks against quality checklist (structure, logging, etc.)
- Reports findings by severity (CRITICAL, HIGH, MEDIUM, LOW)
- Provides fix recommendations

### /docs-update
Keeps documentation in sync with code.
- Updates CHANGELOG.md with new entries
- Updates ROADMAP.md progress
- Updates TODO.md task status
- Updates README.md if needed

### /deploy
Deploys code from DEV to PRD.
- Pre-deployment checks
- Git push and SSH pull
- Service restart
- Verification and monitoring

## Skill Files

Detailed instructions are in `.claude/skills/`:
- `pdf.md`
- `test-writer.md`
- `code-review.md`
- `docs-updater.md`
- `deploy.md`
