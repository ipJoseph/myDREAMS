# Code Review Skill

Perform security and quality analysis on myDREAMS code.

## Activation

Use this skill when asked to:
- Review code for security issues
- Check code quality
- Audit a module or file
- Find vulnerabilities

## Security Checklist

### 1. SQL Injection
- [ ] All queries use parameterized statements (`?` placeholders)
- [ ] No f-strings or string concatenation in SQL
- [ ] Dynamic column names validated against whitelist

### 2. XSS (Cross-Site Scripting)
- [ ] User input escaped in HTML templates
- [ ] JavaScript uses `textContent` not `innerHTML` for user data
- [ ] Content-Security-Policy headers set

### 3. Authentication/Authorization
- [ ] `@requires_auth` decorator on protected routes
- [ ] API keys not exposed in responses
- [ ] Debug mode disabled in production
- [ ] Passwords not logged or in URLs

### 4. CSRF Protection
- [ ] CSRF tokens on all POST forms
- [ ] State-changing actions require POST
- [ ] SameSite cookie attribute set

### 5. Error Handling
- [ ] Exception details not returned to clients
- [ ] Specific exceptions caught (not bare `except:`)
- [ ] Errors logged with context

### 6. Input Validation
- [ ] Request parameters validated
- [ ] File paths sanitized
- [ ] Numeric ranges checked

### 7. Secrets Management
- [ ] No hardcoded credentials
- [ ] Secrets from environment variables
- [ ] `.env` files git-ignored

## Quality Checklist

### 1. Code Structure
- [ ] Functions < 50 lines
- [ ] Files < 500 lines (flag if > 1000)
- [ ] Clear separation of concerns

### 2. Error Handling
- [ ] Graceful error handling
- [ ] Meaningful error messages (internal)
- [ ] Generic error messages (external)

### 3. Logging
- [ ] Appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- [ ] Structured logging for key operations
- [ ] No sensitive data in logs

### 4. Database
- [ ] Connection pooling or proper cleanup
- [ ] Transactions for multi-step operations
- [ ] Indexes on frequently queried columns

### 5. Performance
- [ ] No N+1 query patterns
- [ ] Pagination for large result sets
- [ ] Async where appropriate

### 6. Documentation
- [ ] Module docstrings
- [ ] Function docstrings for public API
- [ ] Type hints on function signatures

## Review Workflow

1. **Read** the target file(s)
2. **Check** against security checklist
3. **Check** against quality checklist
4. **Identify** specific line numbers for issues
5. **Categorize** findings:
   - CRITICAL: Must fix immediately (security)
   - HIGH: Should fix soon (security, major bugs)
   - MEDIUM: Should fix (quality, minor bugs)
   - LOW: Nice to fix (style, minor improvements)
6. **Provide** fix recommendations

## Output Format

```
## Code Review: [filename]

### Summary
[1-2 sentence overview]

### Security Issues
| Severity | Line | Issue | Recommendation |
|----------|------|-------|----------------|
| CRITICAL | 45 | SQL injection | Use parameterized query |

### Quality Issues
| Severity | Line | Issue | Recommendation |
|----------|------|-------|----------------|
| MEDIUM | 120 | Bare except | Catch specific exception |

### Positive Notes
- Good use of type hints
- Clear function naming

### Recommendations
1. [Priority fix 1]
2. [Priority fix 2]
```

## Tools to Use

### Static Analysis (if available)
```bash
# Python security scanner
bandit -r /home/bigeug/myDREAMS/apps/ -f json

# Python linter
ruff check /home/bigeug/myDREAMS/apps/

# Type checking
mypy /home/bigeug/myDREAMS/src/
```

### Manual Analysis
- Read files with Read tool
- Search patterns with Grep tool
- Check for known vulnerability patterns

## Known myDREAMS Patterns to Check

1. **CORS Configuration**: Should NOT be `"*"` in production
2. **Debug Mode**: Should be controlled by environment variable
3. **Database Connections**: Use `get_db()` helper
4. **API Authentication**: Use `@requires_auth` decorator
5. **Error Responses**: Use `{'success': False, 'error': 'message'}` format
