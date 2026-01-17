# Shared Resources

Cross-application resources for the DREAMS platform.

## CSS Design System

**Location:** `css/dreams.css`

### Usage

Each Flask app should symlink to the shared directory from its static folder:

```bash
# From apps/<app-name>/static/
ln -s ../../../shared shared
```

Then in templates:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='shared/css/dreams.css') }}">
```

### What's Included

- **CSS Variables** - Design tokens for colors, spacing, typography
- **Base Reset** - Consistent box-sizing and margins
- **Component Classes** - Headers, buttons, badges, tables, cards
- **Status Badges** - Property status, IDX validation status
- **Responsive Breakpoints** - Mobile-friendly defaults

### Migration Path

1. Add the stylesheet link to your template
2. Existing inline styles with matching variable names will work
3. Gradually replace inline styles with shared classes
4. Remove redundant inline CSS over time

### Documentation

Full design system documentation: `docs/ARCHITECTURE.md` (Shared UI Design System section)
