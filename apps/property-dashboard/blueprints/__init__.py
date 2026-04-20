"""Dashboard blueprints.

Each blueprint owns a slice of dashboard routes. Shared dependencies
(the DREAMSDatabase singleton, the requires_auth decorator, a few
path constants) are injected via this module's `deps` namespace to
avoid circular imports between `app.py` and the blueprint modules.

Usage in app.py:

    from blueprints import deps as _bp_deps
    _bp_deps.db = db
    _bp_deps.requires_auth = requires_auth
    _bp_deps.project_root = PROJECT_ROOT
    _bp_deps.et = ET
    _bp_deps.reports_dir = REPORTS_DIR

    from blueprints.expenses import expenses_bp
    app.register_blueprint(expenses_bp)
"""

from types import SimpleNamespace

# Populated by app.py at startup before any blueprint module is imported.
deps = SimpleNamespace()
