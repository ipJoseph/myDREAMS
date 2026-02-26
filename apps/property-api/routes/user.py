"""
User API endpoints for authentication, favorites, and saved searches.

These endpoints handle buyer account management for the public website.
Authentication is handled by Auth.js (NextAuth v5) on the Next.js side;
these endpoints are called from the Auth.js callbacks and from the
client-side UI.

Endpoints:
    POST /user/register       - Create account with email/password
    POST /user/login          - Validate credentials, return user data
    POST /user/oauth-sync     - Sync OAuth user (called from Auth.js callback)
    GET  /user/me             - Get current user profile (requires JWT)
    GET  /user/favorites      - List user's favorited listings
    POST /user/favorites      - Add a listing to favorites
    DELETE /user/favorites/:id - Remove a favorite
    GET  /user/searches       - List saved searches
    POST /user/searches       - Save a search
    DELETE /user/searches/:id - Delete a saved search
"""

import json
import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

user_bp = Blueprint('user', __name__)

DB_PATH = os.getenv('DREAMS_DB_PATH', str(PROJECT_ROOT / 'data' / 'dreams.db'))


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _check_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    import bcrypt
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def _get_user_from_jwt():
    """Extract user ID from the Authorization header (Bearer JWT).

    In our architecture, Auth.js manages sessions via JWTs. The Next.js
    client sends the JWT in the Authorization header for API calls that
    need authentication. We decode it using the shared AUTH_SECRET.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header[7:]
    auth_secret = os.getenv('AUTH_SECRET')
    if not auth_secret:
        return None

    try:
        import jwt
        payload = jwt.decode(token, auth_secret, algorithms=['HS256'])
        return payload.get('id') or payload.get('sub')
    except Exception:
        return None


def _user_dict(row) -> dict:
    """Convert a user row to a safe dict (no password hash)."""
    if not row:
        return None
    d = dict(row)
    d.pop('password_hash', None)
    return d


def _resolve_lead_id(db, user_id: str) -> str | None:
    """Resolve a user to a lead ID via cached value or email match."""
    user = db.execute(
        'SELECT lead_id, fub_lead_id, email FROM users WHERE id = ?',
        [user_id]
    ).fetchone()
    if not user:
        return None

    cached = user['lead_id'] or user['fub_lead_id']
    if cached:
        return cached

    if not user['email']:
        return None

    lead = db.execute(
        'SELECT id FROM leads WHERE LOWER(email) = LOWER(?) LIMIT 1',
        [user['email']]
    ).fetchone()

    if lead:
        db.execute('UPDATE users SET lead_id = ? WHERE id = ?',
                   [lead['id'], user_id])
        db.commit()
        return lead['id']

    return None


def _log_buyer_activity(
    user_id: str,
    activity_type: str,
    entity_type: str = None,
    entity_id: str = None,
    entity_name: str = None,
    metadata: dict = None,
):
    """Log a buyer action to buyer_activity. Never raises."""
    try:
        db = get_db()
        lead_id = _resolve_lead_id(db, user_id)
        db.execute(
            '''INSERT INTO buyer_activity
               (user_id, lead_id, activity_type, entity_type, entity_id,
                entity_name, metadata, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            [user_id, lead_id, activity_type, entity_type, entity_id,
             entity_name, json.dumps(metadata) if metadata else None,
             datetime.now().isoformat()]
        )
        db.commit()
        db.close()
    except Exception as e:
        logger.warning(f"Failed to log buyer activity: {e}")


# -----------------------------------------------------------------------
# Registration & Login
# -----------------------------------------------------------------------

@user_bp.route('/register', methods=['POST'])
def register():
    """Create a new user account with email and password."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')
    name = (data.get('name') or '').strip()

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400

    if len(password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

    try:
        db = get_db()

        # Check for existing user
        existing = db.execute('SELECT id FROM users WHERE email = ?', [email]).fetchone()
        if existing:
            db.close()
            return jsonify({'success': False, 'error': 'An account with this email already exists'}), 409

        user_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        db.execute(
            'INSERT INTO users (id, email, name, password_hash, created_at, last_login) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [user_id, email, name, _hash_password(password), now, now]
        )
        db.commit()

        user = db.execute('SELECT * FROM users WHERE id = ?', [user_id]).fetchone()
        db.close()

        return jsonify({
            'success': True,
            'data': _user_dict(user),
        }), 201

    except Exception:
        return jsonify({'success': False, 'error': 'Registration failed'}), 500


@user_bp.route('/login', methods=['POST'])
def login():
    """Validate email/password and return user data.

    Called by Auth.js Credentials provider's authorize() function.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    email = (data.get('email') or '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password are required'}), 400

    try:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', [email]).fetchone()

        if not user or not user['password_hash']:
            db.close()
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401

        if not _check_password(password, user['password_hash']):
            db.close()
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401

        # Update last login
        db.execute('UPDATE users SET last_login = ? WHERE id = ?',
                   [datetime.now().isoformat(), user['id']])
        db.commit()
        db.close()

        return jsonify({
            'success': True,
            'data': _user_dict(user),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Login failed'}), 500


@user_bp.route('/oauth-sync', methods=['POST'])
def oauth_sync():
    """Sync an OAuth user (Google) to our database.

    Called from Auth.js jwt callback when a user signs in with Google.
    Creates the user if they don't exist, or returns existing user.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    provider = data.get('provider')
    provider_account_id = data.get('provider_account_id')
    email = (data.get('email') or '').strip().lower()
    name = data.get('name', '')
    avatar_url = data.get('avatar_url', '')

    if not provider or not provider_account_id or not email:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    try:
        db = get_db()
        now = datetime.now().isoformat()

        # Check if user exists by email
        user = db.execute('SELECT * FROM users WHERE email = ?', [email]).fetchone()

        if user:
            # Update last login and avatar if needed
            updates = {'last_login': now}
            if avatar_url and not user['avatar_url']:
                updates['avatar_url'] = avatar_url
            if provider == 'google' and not user['google_id']:
                updates['google_id'] = provider_account_id

            set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
            db.execute(
                f'UPDATE users SET {set_clause} WHERE id = ?',
                list(updates.values()) + [user['id']]
            )
            db.commit()
            user_id = user['id']
        else:
            # Create new user
            user_id = str(uuid.uuid4())
            google_id = provider_account_id if provider == 'google' else None

            db.execute(
                'INSERT INTO users (id, email, name, google_id, avatar_url, email_verified, created_at, last_login) '
                'VALUES (?, ?, ?, ?, ?, 1, ?, ?)',
                [user_id, email, name, google_id, avatar_url, now, now]
            )
            db.commit()

        # Ensure auth_accounts entry exists
        existing_account = db.execute(
            'SELECT id FROM auth_accounts WHERE provider = ? AND provider_account_id = ?',
            [provider, provider_account_id]
        ).fetchone()

        if not existing_account:
            db.execute(
                'INSERT INTO auth_accounts (id, user_id, type, provider, provider_account_id) '
                'VALUES (?, ?, ?, ?, ?)',
                [str(uuid.uuid4()), user_id, 'oauth', provider, provider_account_id]
            )
            db.commit()

        user = db.execute('SELECT * FROM users WHERE id = ?', [user_id]).fetchone()
        db.close()

        return jsonify({
            'success': True,
            'data': _user_dict(user),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'OAuth sync failed'}), 500


@user_bp.route('/me', methods=['GET'])
def get_me():
    """Get the current user's profile."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE id = ?', [user_id]).fetchone()
        db.close()

        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        return jsonify({
            'success': True,
            'data': _user_dict(user),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to get profile'}), 500


# -----------------------------------------------------------------------
# Favorites
# -----------------------------------------------------------------------

@user_bp.route('/favorites', methods=['GET'])
def list_favorites():
    """List the current user's favorited listings."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()

        rows = db.execute(
            '''SELECT uf.id as favorite_id, uf.created_at as favorited_at,
                      l.id, l.mls_number, l.status, l.list_price, l.sold_price,
                      l.address, l.city, l.state, l.zip, l.county,
                      l.property_type, l.beds, l.baths, l.sqft, l.acreage,
                      l.primary_photo, l.days_on_market, l.list_date
               FROM user_favorites uf
               JOIN listings l ON l.id = uf.listing_id
               WHERE uf.user_id = ?
               ORDER BY uf.created_at DESC''',
            [user_id]
        ).fetchall()

        db.close()

        return jsonify({
            'success': True,
            'data': [dict(r) for r in rows],
            'count': len(rows),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to list favorites'}), 500


@user_bp.route('/favorites', methods=['POST'])
def add_favorite():
    """Add a listing to the user's favorites."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    listing_id = data.get('listing_id') if data else None
    if not listing_id:
        return jsonify({'success': False, 'error': 'listing_id is required'}), 400

    try:
        db = get_db()

        # Verify listing exists
        listing = db.execute('SELECT id FROM listings WHERE id = ?', [listing_id]).fetchone()
        if not listing:
            db.close()
            return jsonify({'success': False, 'error': 'Listing not found'}), 404

        # Get listing details for activity metadata
        listing_info = db.execute(
            'SELECT address, city, list_price FROM listings WHERE id = ?',
            [listing_id]
        ).fetchone()

        fav_id = str(uuid.uuid4())
        db.execute(
            'INSERT OR IGNORE INTO user_favorites (id, user_id, listing_id, created_at) '
            'VALUES (?, ?, ?, ?)',
            [fav_id, user_id, listing_id, datetime.now().isoformat()]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'favorite', 'listing', listing_id,
            entity_name=f"{listing_info['address']}, {listing_info['city']}" if listing_info else None,
            metadata={'list_price': listing_info['list_price']} if listing_info else None,
        )

        return jsonify({'success': True, 'data': {'id': fav_id}}), 201

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to add favorite'}), 500


@user_bp.route('/favorites/<listing_id>', methods=['DELETE'])
def remove_favorite(listing_id):
    """Remove a listing from the user's favorites."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        db.execute(
            'DELETE FROM user_favorites WHERE user_id = ? AND listing_id = ?',
            [user_id, listing_id]
        )
        db.commit()
        db.close()

        _log_buyer_activity(user_id, 'unfavorite', 'listing', listing_id)

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to remove favorite'}), 500


@user_bp.route('/favorites/check', methods=['GET'])
def check_favorites():
    """Check which listing IDs from a list are favorited by the current user.

    Query params:
        ids - Comma-separated listing IDs
    """
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': True, 'data': []})

    ids_param = request.args.get('ids', '')
    if not ids_param:
        return jsonify({'success': True, 'data': []})

    listing_ids = [lid.strip() for lid in ids_param.split(',') if lid.strip()]
    if not listing_ids:
        return jsonify({'success': True, 'data': []})

    try:
        db = get_db()
        placeholders = ','.join(['?'] * len(listing_ids))
        rows = db.execute(
            f'SELECT listing_id FROM user_favorites WHERE user_id = ? AND listing_id IN ({placeholders})',
            [user_id] + listing_ids
        ).fetchall()
        db.close()

        return jsonify({
            'success': True,
            'data': [r['listing_id'] for r in rows],
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to check favorites'}), 500


# -----------------------------------------------------------------------
# Saved Searches
# -----------------------------------------------------------------------

@user_bp.route('/searches', methods=['GET'])
def list_searches():
    """List the current user's saved searches."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        rows = db.execute(
            'SELECT * FROM saved_searches WHERE user_id = ? ORDER BY created_at DESC',
            [user_id]
        ).fetchall()
        db.close()

        searches = []
        for row in rows:
            d = dict(row)
            # Parse filters_json back to object
            try:
                d['filters'] = json.loads(d.pop('filters_json'))
            except (json.JSONDecodeError, KeyError):
                d['filters'] = {}
            searches.append(d)

        return jsonify({
            'success': True,
            'data': searches,
            'count': len(searches),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to list searches'}), 500


@user_bp.route('/searches', methods=['POST'])
def save_search():
    """Save a search with filters."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    name = (data.get('name') or '').strip()
    filters = data.get('filters', {})
    alert_frequency = data.get('alert_frequency', 'daily')

    if not name:
        return jsonify({'success': False, 'error': 'Search name is required'}), 400

    if alert_frequency not in ('daily', 'weekly', 'never'):
        alert_frequency = 'daily'

    try:
        db = get_db()
        search_id = str(uuid.uuid4())
        db.execute(
            'INSERT INTO saved_searches (id, user_id, name, filters_json, alert_frequency, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [search_id, user_id, name, json.dumps(filters), alert_frequency, datetime.now().isoformat()]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'save_search', 'search', search_id,
            entity_name=name, metadata={'filters': filters},
        )

        return jsonify({
            'success': True,
            'data': {'id': search_id, 'name': name, 'filters': filters},
        }), 201

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to save search'}), 500


@user_bp.route('/searches/<search_id>', methods=['PUT'])
def update_search(search_id):
    """Update a saved search's name or alert frequency."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    try:
        db = get_db()
        updates = []
        params = []

        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                db.close()
                return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
            updates.append('name = ?')
            params.append(name)

        if 'alert_frequency' in data:
            freq = data['alert_frequency']
            if freq not in ('daily', 'weekly', 'never'):
                freq = 'daily'
            updates.append('alert_frequency = ?')
            params.append(freq)

        if not updates:
            db.close()
            return jsonify({'success': False, 'error': 'Nothing to update'}), 400

        params.extend([search_id, user_id])
        db.execute(
            f'UPDATE saved_searches SET {", ".join(updates)} WHERE id = ? AND user_id = ?',
            params
        )
        db.commit()
        db.close()

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to update search'}), 500


@user_bp.route('/searches/<search_id>', methods=['DELETE'])
def delete_search(search_id):
    """Delete a saved search."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        db.execute(
            'DELETE FROM saved_searches WHERE id = ? AND user_id = ?',
            [search_id, user_id]
        )
        db.commit()
        db.close()

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to delete search'}), 500


# -----------------------------------------------------------------------
# Collections (Buyer property groupings)
# -----------------------------------------------------------------------

@user_bp.route('/collections', methods=['GET'])
def list_collections():
    """List the current user's property collections."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        rows = db.execute(
            '''SELECT pp.*, COUNT(pkp.listing_id) as property_count
               FROM property_packages pp
               LEFT JOIN package_properties pkp ON pkp.package_id = pp.id
               WHERE pp.user_id = ? AND pp.collection_type = 'buyer_collection'
               GROUP BY pp.id
               ORDER BY pp.created_at DESC''',
            [user_id]
        ).fetchall()
        db.close()

        return jsonify({
            'success': True,
            'data': [dict(r) for r in rows],
            'count': len(rows),
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to list collections'}), 500


@user_bp.route('/collections', methods=['POST'])
def create_collection():
    """Create a new property collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Collection name is required'}), 400

    try:
        db = get_db()
        import secrets
        collection_id = str(uuid.uuid4())
        share_token = secrets.token_urlsafe(16)
        now = datetime.now().isoformat()

        db.execute(
            '''INSERT INTO property_packages
               (id, name, description, status, user_id, collection_type,
                share_token, created_at, updated_at)
               VALUES (?, ?, ?, 'draft', ?, 'buyer_collection', ?, ?, ?)''',
            [collection_id, name, data.get('description', ''),
             user_id, share_token, now, now]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'create_collection', 'collection', collection_id,
            entity_name=name,
        )

        return jsonify({
            'success': True,
            'data': {'id': collection_id, 'name': name, 'share_token': share_token},
        }), 201

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to create collection'}), 500


@user_bp.route('/collections/<collection_id>', methods=['GET'])
def get_collection(collection_id):
    """Get a collection with its listings."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()

        collection = db.execute(
            '''SELECT id, name, description, status, user_id, collection_type,
                      share_token, created_at, updated_at,
                      showing_requested, showing_requested_at
               FROM property_packages WHERE id = ? AND user_id = ?''',
            [collection_id, user_id]
        ).fetchone()

        if not collection:
            db.close()
            return jsonify({'success': False, 'error': 'Collection not found'}), 404

        # Get listings in collection
        listings = db.execute(
            '''SELECT l.id, l.mls_number, l.status, l.list_price, l.sold_price,
                      l.address, l.city, l.state, l.zip,
                      l.property_type, l.beds, l.baths, l.sqft, l.acreage,
                      l.primary_photo, l.days_on_market,
                      pp.display_order, pp.agent_notes, pp.added_at
               FROM package_properties pp
               JOIN listings l ON l.id = pp.listing_id
               WHERE pp.package_id = ?
               ORDER BY pp.display_order, pp.added_at''',
            [collection_id]
        ).fetchall()

        db.close()

        result = dict(collection)
        result['listings'] = [dict(r) for r in listings]

        return jsonify({'success': True, 'data': result})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to get collection'}), 500


@user_bp.route('/collections/<collection_id>', methods=['PUT'])
def update_collection(collection_id):
    """Update a collection's name or description."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    try:
        db = get_db()
        updates = []
        params = []

        if 'name' in data:
            updates.append('name = ?')
            params.append(data['name'])
        if 'description' in data:
            updates.append('description = ?')
            params.append(data['description'])

        if not updates:
            db.close()
            return jsonify({'success': False, 'error': 'Nothing to update'}), 400

        updates.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.extend([collection_id, user_id])

        db.execute(
            f'UPDATE property_packages SET {", ".join(updates)} WHERE id = ? AND user_id = ?',
            params
        )
        db.commit()
        db.close()

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to update collection'}), 500


@user_bp.route('/collections/<collection_id>', methods=['DELETE'])
def delete_collection(collection_id):
    """Delete a collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()
        # Delete items first (FK cascade may not be enabled)
        db.execute('DELETE FROM package_properties WHERE package_id = ?', [collection_id])
        db.execute(
            'DELETE FROM property_packages WHERE id = ? AND user_id = ?',
            [collection_id, user_id]
        )
        db.commit()
        db.close()

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to delete collection'}), 500


@user_bp.route('/collections/<collection_id>/items', methods=['POST'])
def add_to_collection(collection_id):
    """Add a listing to a collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    data = request.get_json()
    listing_id = data.get('listing_id') if data else None
    if not listing_id:
        return jsonify({'success': False, 'error': 'listing_id is required'}), 400

    try:
        db = get_db()

        # Verify collection belongs to user
        collection = db.execute(
            'SELECT id FROM property_packages WHERE id = ? AND user_id = ?',
            [collection_id, user_id]
        ).fetchone()
        if not collection:
            db.close()
            return jsonify({'success': False, 'error': 'Collection not found'}), 404

        # Get next display_order
        max_order = db.execute(
            'SELECT COALESCE(MAX(display_order), 0) FROM package_properties WHERE package_id = ?',
            [collection_id]
        ).fetchone()[0]

        # Get listing details for activity metadata
        listing_info = db.execute(
            'SELECT address, city, list_price FROM listings WHERE id = ?',
            [listing_id]
        ).fetchone()

        item_id = str(uuid.uuid4())
        db.execute(
            'INSERT OR IGNORE INTO package_properties (id, package_id, listing_id, display_order, added_at) '
            'VALUES (?, ?, ?, ?, ?)',
            [item_id, collection_id, listing_id, max_order + 1, datetime.now().isoformat()]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'add_to_collection', 'listing', listing_id,
            entity_name=f"{listing_info['address']}, {listing_info['city']}" if listing_info else None,
            metadata={'collection_id': collection_id, 'list_price': listing_info['list_price']} if listing_info else None,
        )

        return jsonify({'success': True, 'data': {'id': item_id}}), 201

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to add to collection'}), 500


@user_bp.route('/collections/<collection_id>/items/<listing_id>', methods=['DELETE'])
def remove_from_collection(collection_id, listing_id):
    """Remove a listing from a collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()

        # Verify collection belongs to user
        collection = db.execute(
            'SELECT id FROM property_packages WHERE id = ? AND user_id = ?',
            [collection_id, user_id]
        ).fetchone()
        if not collection:
            db.close()
            return jsonify({'success': False, 'error': 'Collection not found'}), 404

        db.execute(
            'DELETE FROM package_properties WHERE package_id = ? AND listing_id = ?',
            [collection_id, listing_id]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'remove_from_collection', 'listing', listing_id,
            metadata={'collection_id': collection_id},
        )

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to remove from collection'}), 500


# -----------------------------------------------------------------------
# Showing Requests
# -----------------------------------------------------------------------

@user_bp.route('/collections/<collection_id>/request-showings', methods=['POST'])
def request_showings(collection_id):
    """Request showings for all properties in a collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()

        # Verify collection belongs to user and get details
        collection = db.execute(
            'SELECT id, name, showing_requested FROM property_packages WHERE id = ? AND user_id = ?',
            [collection_id, user_id]
        ).fetchone()
        if not collection:
            db.close()
            return jsonify({'success': False, 'error': 'Collection not found'}), 404

        # Count properties
        prop_count = db.execute(
            'SELECT COUNT(*) FROM package_properties WHERE package_id = ?',
            [collection_id]
        ).fetchone()[0]

        if prop_count == 0:
            db.close()
            return jsonify({'success': False, 'error': 'Collection has no properties'}), 400

        now = datetime.now().isoformat()
        db.execute(
            'UPDATE property_packages SET showing_requested = 1, showing_requested_at = ?, updated_at = ? WHERE id = ?',
            [now, now, collection_id]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'request_showings', 'collection', collection_id,
            entity_name=collection['name'],
            metadata={'property_count': prop_count},
        )

        # Fire immediate agent notification (best effort)
        try:
            from apps.automation.buyer_notifications import send_showing_request_alert
            send_showing_request_alert(user_id, collection_id)
        except Exception as e:
            logger.warning(f"Failed to send showing request alert: {e}")

        return jsonify({
            'success': True,
            'data': {
                'showing_requested': 1,
                'showing_requested_at': now,
                'property_count': prop_count,
            },
        })

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to request showings'}), 500


@user_bp.route('/collections/<collection_id>/cancel-showings', methods=['POST'])
def cancel_showings(collection_id):
    """Cancel a showing request for a collection."""
    user_id = _get_user_from_jwt()
    if not user_id:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    try:
        db = get_db()

        collection = db.execute(
            'SELECT id, name FROM property_packages WHERE id = ? AND user_id = ?',
            [collection_id, user_id]
        ).fetchone()
        if not collection:
            db.close()
            return jsonify({'success': False, 'error': 'Collection not found'}), 404

        now = datetime.now().isoformat()
        db.execute(
            'UPDATE property_packages SET showing_requested = 0, updated_at = ? WHERE id = ?',
            [now, collection_id]
        )
        db.commit()
        db.close()

        _log_buyer_activity(
            user_id, 'cancel_showings', 'collection', collection_id,
            entity_name=collection['name'],
        )

        return jsonify({'success': True})

    except Exception:
        return jsonify({'success': False, 'error': 'Failed to cancel showings'}), 500
