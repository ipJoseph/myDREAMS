---
description: Generate pytest tests for code
---

# Test Writer

Generate pytest tests following myDREAMS conventions.

## Instructions

Follow the test-writer skill guidelines in `.claude/skills/test-writer.md`.

When the user provides a file or module path:

1. Read the source file to understand what needs testing
2. Create test file in `/home/bigeug/myDREAMS/tests/` mirroring source structure
3. Write tests covering:
   - Happy path (normal usage)
   - Edge cases (empty inputs, boundaries)
   - Error cases (invalid inputs, exceptions)
4. Use pytest fixtures for common setup
5. Run the tests with `pytest -v`
6. Report results

## Argument

$ARGUMENTS - Path to file or module to test, or "all" for suggested files
