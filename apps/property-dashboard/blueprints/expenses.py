"""Expense tracking routes, extracted from apps/property-dashboard/app.py.

Covers:
  /expenses, /expenses/new, /expenses/<id>, /expenses/tax-summary
  /api/expenses/<id> (PUT/DELETE), /api/expenses/<id>/items (POST/PUT/DELETE),
  /api/expenses/<id>/items/<item>/receipt (POST/GET/DELETE)

The blueprint reaches the DREAMSDatabase singleton and the auth
decorator via `blueprints.deps`, which app.py populates before this
module is imported.
"""

from __future__ import annotations

import base64
import os
import sqlite3
import uuid
from datetime import datetime

from flask import Blueprint, Response, jsonify, redirect, render_template, request, send_from_directory

from . import deps

expenses_bp = Blueprint("expenses", __name__)


# IRS Schedule C category mapping for a real-estate-agent expense report.
SCHEDULE_C_MAP = {
    'Marketing':      {'line': '8',   'label': 'Advertising'},
    'Signs':          {'line': '8',   'label': 'Advertising'},
    'Photography':    {'line': '8',   'label': 'Advertising'},
    'Mileage':        {'line': '9',   'label': 'Car and truck expenses'},
    'Commissions':    {'line': '10',  'label': 'Commissions and fees'},
    'Contract Labor': {'line': '11',  'label': 'Contract labor'},
    'Insurance':      {'line': '15',  'label': 'Insurance (E&O, liability)'},
    'Professional':   {'line': '17',  'label': 'Legal and professional services'},
    'Office':         {'line': '18',  'label': 'Office expense'},
    'Technology':     {'line': '18',  'label': 'Office expense'},
    'Desk Fees':      {'line': '20b', 'label': 'Rent or lease (desk fees, storage)'},
    'Licensing':      {'line': '23',  'label': 'Taxes and licenses (MLS, NAR, state)'},
    'Dues':           {'line': '23',  'label': 'Taxes and licenses (MLS, NAR, state)'},
    'Travel':         {'line': '24a', 'label': 'Travel'},
    'Meals':          {'line': '24b', 'label': 'Meals (50% deductible)'},
    'Education':      {'line': '27a', 'label': 'Other expenses'},
    'Gifts':          {'line': '27a', 'label': 'Other expenses (gifts max $25/person)'},
    'Staging':        {'line': '27a', 'label': 'Other expenses'},
    'Other':          {'line': '27a', 'label': 'Other expenses'},
    'Home Office':    {'line': '30',  'label': 'Business use of home'},
}

EXPENSE_CATEGORIES = [
    'Marketing', 'Signs', 'Photography',
    'Mileage',
    'Commissions', 'Contract Labor',
    'Insurance',
    'Professional',
    'Office', 'Technology',
    'Desk Fees',
    'Licensing', 'Dues',
    'Travel', 'Meals',
    'Education', 'Gifts', 'Staging', 'Home Office',
    'Other',
]


def _ensure_expense_tables():
    """Create expense tables if they don't exist.

    PostgreSQL DEV and PRD already have these tables from the PG
    migration, so this is a SQLite-only bootstrap helper. The AUTOINCREMENT
    keyword is SQLite-specific, which is why we gate on the backend rather
    than relying on `CREATE TABLE IF NOT EXISTS` to be a no-op.
    """
    from src.core.pg_adapter import is_postgres
    if is_postgres():
        return

    with deps.db._get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_reports (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'Expense Report',
                link_type TEXT,
                link_id TEXT,
                link_label TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES expense_reports(id),
                name TEXT NOT NULL,
                description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                category TEXT,
                receipt_data BLOB,
                receipt_mime TEXT,
                receipt_name TEXT,
                created_at TEXT NOT NULL
            )
        """)
        try:
            conn.execute("ALTER TABLE expense_items ADD COLUMN receipt_data BLOB")
            conn.execute("ALTER TABLE expense_items ADD COLUMN receipt_mime TEXT")
            conn.execute("ALTER TABLE expense_items ADD COLUMN receipt_name TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def _agent_info_and_logo():
    logo_path = deps.project_root / 'assets' / 'branding' / 'jth-icon.jpg'
    logo_b64 = ''
    if logo_path.exists():
        logo_b64 = f"data:image/jpeg;base64,{base64.b64encode(logo_path.read_bytes()).decode()}"
    agent_info = {
        'name': os.environ.get('AGENT_NAME', 'Joseph Williams'),
        'phone': os.environ.get('AGENT_PHONE', '(828) 347-9363'),
        'email': os.environ.get('AGENT_EMAIL', 'Joseph@JonTharpHomes.com'),
        'website': os.environ.get('AGENT_WEBSITE', 'www.JonTharpHomes.com'),
    }
    return agent_info, logo_b64


@expenses_bp.route('/expenses')
@deps.requires_auth
def expense_list():
    _ensure_expense_tables()
    with deps.db._get_connection() as conn:
        reports = conn.execute("""
            SELECT r.id, r.title, r.link_type, r.link_label, r.created_at, r.updated_at,
                   COUNT(i.id) as item_count, COALESCE(SUM(i.amount), 0) as total
            FROM expense_reports r
            LEFT JOIN expense_items i ON i.report_id = r.id
            GROUP BY r.id
            ORDER BY r.updated_at DESC
        """).fetchall()
    return render_template('expense_list.html', reports=reports)


@expenses_bp.route('/expenses/new')
@deps.requires_auth
def expense_new():
    _ensure_expense_tables()
    report_id = str(uuid.uuid4())[:8]
    now = datetime.now(tz=deps.et).isoformat()

    link_type = request.args.get('link_type', '')
    link_id = request.args.get('link_id', '')
    link_label = request.args.get('link_label', '')

    with deps.db._get_connection() as conn:
        conn.execute(
            "INSERT INTO expense_reports (id, title, link_type, link_id, link_label, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [report_id, 'Expense Report', link_type or None, link_id or None, link_label or None, now, now],
        )
        conn.commit()
    return redirect(f'/expenses/{report_id}')


@expenses_bp.route('/expenses/<report_id>')
@deps.requires_auth
def expense_form(report_id):
    _ensure_expense_tables()
    with deps.db._get_connection() as conn:
        report = conn.execute(
            "SELECT * FROM expense_reports WHERE id = ?", [report_id]
        ).fetchone()
        if not report:
            return "Expense report not found", 404

        items_raw = conn.execute(
            "SELECT id, report_id, name, description, amount, category, receipt_mime, receipt_name, created_at "
            "FROM expense_items WHERE report_id = ? ORDER BY id", [report_id]
        ).fetchall()
        items = []
        for row in items_raw:
            d = dict(row)
            d['has_receipt'] = bool(d.get('receipt_mime'))
            items.append(d)

        contacts = conn.execute(
            "SELECT id, first_name, last_name FROM leads "
            "WHERE first_name IS NOT NULL ORDER BY first_name LIMIT 200"
        ).fetchall()

    agent_info, logo_b64 = _agent_info_and_logo()
    return render_template(
        'expense_form.html',
        report=dict(report),
        items=[dict(i) for i in items],
        contacts=contacts,
        categories=EXPENSE_CATEGORIES,
        logo_b64=logo_b64,
        agent=agent_info,
    )


@expenses_bp.route('/api/expenses/<report_id>', methods=['PUT'])
@deps.requires_auth
def api_update_expense_report(report_id):
    _ensure_expense_tables()
    data = request.get_json()
    now = datetime.now(tz=deps.et).isoformat()
    with deps.db._get_connection() as conn:
        conn.execute(
            "UPDATE expense_reports SET title=?, link_type=?, link_id=?, link_label=?, updated_at=? WHERE id=?",
            [data.get('title', 'Expense Report'), data.get('link_type'), data.get('link_id'),
             data.get('link_label'), now, report_id],
        )
        conn.commit()
    return jsonify({'success': True})


@expenses_bp.route('/api/expenses/<report_id>/items', methods=['POST'])
@deps.requires_auth
def api_add_expense_item(report_id):
    _ensure_expense_tables()
    data = request.get_json()
    now = datetime.now(tz=deps.et).isoformat()
    with deps.db._get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO expense_items (report_id, name, description, amount, category, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [report_id, data.get('name', ''), data.get('description', ''),
             float(data.get('amount', 0)), data.get('category', ''), now],
        )
        conn.execute("UPDATE expense_reports SET updated_at=? WHERE id=?", [now, report_id])
        conn.commit()
        item_id = cursor.lastrowid
    return jsonify({'success': True, 'id': item_id})


@expenses_bp.route('/api/expenses/<report_id>/items/<int:item_id>', methods=['PUT'])
@deps.requires_auth
def api_update_expense_item(report_id, item_id):
    data = request.get_json()
    now = datetime.now(tz=deps.et).isoformat()
    with deps.db._get_connection() as conn:
        conn.execute(
            "UPDATE expense_items SET name=?, description=?, amount=?, category=? WHERE id=? AND report_id=?",
            [data.get('name', ''), data.get('description', ''),
             float(data.get('amount', 0)), data.get('category', ''), item_id, report_id],
        )
        conn.execute("UPDATE expense_reports SET updated_at=? WHERE id=?", [now, report_id])
        conn.commit()
    return jsonify({'success': True})


@expenses_bp.route('/api/expenses/<report_id>/items/<int:item_id>', methods=['DELETE'])
@deps.requires_auth
def api_delete_expense_item(report_id, item_id):
    now = datetime.now(tz=deps.et).isoformat()
    with deps.db._get_connection() as conn:
        conn.execute("DELETE FROM expense_items WHERE id=? AND report_id=?", [item_id, report_id])
        conn.execute("UPDATE expense_reports SET updated_at=? WHERE id=?", [now, report_id])
        conn.commit()
    return jsonify({'success': True})


@expenses_bp.route('/api/expenses/<report_id>', methods=['DELETE'])
@deps.requires_auth
def api_delete_expense_report(report_id):
    with deps.db._get_connection() as conn:
        conn.execute("DELETE FROM expense_items WHERE report_id=?", [report_id])
        conn.execute("DELETE FROM expense_reports WHERE id=?", [report_id])
        conn.commit()
    return jsonify({'success': True})


@expenses_bp.route('/api/expenses/<report_id>/items/<int:item_id>/receipt', methods=['POST'])
@deps.requires_auth
def api_upload_receipt(report_id, item_id):
    if 'receipt' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    f = request.files['receipt']
    if not f.filename:
        return jsonify({'success': False, 'error': 'Empty filename'}), 400

    data = f.read()
    if len(data) > 10 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'File too large (10 MB max)'}), 400

    mime = f.content_type or 'application/octet-stream'
    now = datetime.now(tz=deps.et).isoformat()

    with deps.db._get_connection() as conn:
        conn.execute(
            "UPDATE expense_items SET receipt_data=?, receipt_mime=?, receipt_name=? "
            "WHERE id=? AND report_id=?",
            [sqlite3.Binary(data), mime, f.filename, item_id, report_id],
        )
        conn.execute("UPDATE expense_reports SET updated_at=? WHERE id=?", [now, report_id])
        conn.commit()

    return jsonify({'success': True, 'filename': f.filename, 'size': len(data)})


@expenses_bp.route('/api/expenses/<report_id>/items/<int:item_id>/receipt', methods=['GET'])
@deps.requires_auth
def api_get_receipt(report_id, item_id):
    with deps.db._get_connection() as conn:
        row = conn.execute(
            "SELECT receipt_data, receipt_mime, receipt_name FROM expense_items "
            "WHERE id=? AND report_id=?",
            [item_id, report_id],
        ).fetchone()

    if not row or not row['receipt_data']:
        return "No receipt", 404

    return Response(
        row['receipt_data'],
        mimetype=row['receipt_mime'] or 'image/jpeg',
        headers={'Content-Disposition': f'inline; filename="{row["receipt_name"] or "receipt"}"'},
    )


@expenses_bp.route('/api/expenses/<report_id>/items/<int:item_id>/receipt', methods=['DELETE'])
@deps.requires_auth
def api_delete_receipt(report_id, item_id):
    now = datetime.now(tz=deps.et).isoformat()
    with deps.db._get_connection() as conn:
        conn.execute(
            "UPDATE expense_items SET receipt_data=NULL, receipt_mime=NULL, receipt_name=NULL "
            "WHERE id=? AND report_id=?",
            [item_id, report_id],
        )
        conn.execute("UPDATE expense_reports SET updated_at=? WHERE id=?", [now, report_id])
        conn.commit()
    return jsonify({'success': True})


@expenses_bp.route('/expenses/tax-summary')
@deps.requires_auth
def expense_tax_summary():
    _ensure_expense_tables()
    year = request.args.get('year', str(datetime.now().year))
    agent_info, logo_b64 = _agent_info_and_logo()

    with deps.db._get_connection() as conn:
        items = conn.execute("""
            SELECT i.id, i.name, i.description, i.amount, i.category,
                   i.receipt_mime, i.created_at,
                   r.id as report_id, r.title as report_title,
                   r.link_type, r.link_label
            FROM expense_items i
            JOIN expense_reports r ON r.id = i.report_id
            WHERE i.created_at LIKE ?
            ORDER BY i.category, i.created_at
        """, [f'{year}%']).fetchall()

        years = conn.execute("""
            SELECT DISTINCT SUBSTR(created_at, 1, 4) as yr
            FROM expense_items ORDER BY yr DESC
        """).fetchall()

    schedule_c = {}
    for item in items:
        d = dict(item)
        cat = d['category'] or 'Other'
        mapping = SCHEDULE_C_MAP.get(cat, {'line': '27a', 'label': 'Other expenses'})
        line_key = mapping['line']

        if line_key not in schedule_c:
            schedule_c[line_key] = {
                'line': line_key,
                'label': mapping['label'],
                'expenses': [],
                'total': 0,
                'categories': set(),
            }
        schedule_c[line_key]['expenses'].append(d)
        schedule_c[line_key]['total'] += d['amount']
        schedule_c[line_key]['categories'].add(cat)

    sorted_lines = sorted(schedule_c.values(), key=lambda x: x['line'])
    grand_total = sum(line['total'] for line in sorted_lines)
    total_items = sum(len(line['expenses']) for line in sorted_lines)
    total_with_receipts = sum(
        1 for line in sorted_lines for item in line['expenses'] if item.get('receipt_mime')
    )
    available_years = [r['yr'] for r in years] if years else [str(datetime.now().year)]

    return render_template(
        'expense_tax_summary.html',
        schedule_c=sorted_lines,
        grand_total=grand_total,
        total_items=total_items,
        total_with_receipts=total_with_receipts,
        year=year,
        available_years=available_years,
        logo_b64=logo_b64,
        agent=agent_info,
    )


@expenses_bp.route('/reports/<path:filename>')
@deps.requires_auth
def serve_report(filename):
    from pathlib import Path
    safe_name = Path(filename).name
    return send_from_directory(str(deps.reports_dir), safe_name)
