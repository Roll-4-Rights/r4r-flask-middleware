# imports
from gevent import monkey
monkey.patch_all()

from psycogreen.gevent import patch_psycopg
patch_psycopg()

import math

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
from dotenv import load_dotenv
from db import (
    get_db_connection, get_intro_threads, init_donators_table, get_donator_by_id, get_donator_by_email,
    init_forum_messages_table, get_channel_history, init_intro_threads_tables, save_channel_message,
    get_forum_messages_for_moderation, delete_forum_message_by_id, get_intro_thread_by_donator,
    upsert_intro_thread, get_intro_thread_owner, delete_intro_thread_by_id,
    get_intro_replies, add_intro_reply, get_intro_reply_owner, delete_intro_reply_by_id
)
from datetime import datetime
import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
from flask import send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room


load_dotenv()

# create the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

# Session cookie config — required for cross-subdomain cookies over HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Ensure the donators table exists (separate from NocoDB, not visible in its UI)
init_donators_table()
init_forum_messages_table()
init_intro_threads_tables()

# ============= ENVIRONMENT CONFIG =============

FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

ALLOWED_ORIGINS = os.environ.get(
    'ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:5174,http://localhost:3000,http://localhost:3001'
).split(',')

CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)
socketio = SocketIO(app, cors_allowed_origins=ALLOWED_ORIGINS, async_mode='gevent')

# ============= FLASK-LOGIN SETUP =============

login_manager = LoginManager()
login_manager.init_app(app)


class Donator(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(donator_id):
    row = get_donator_by_id(donator_id)
    if not row:
        return None
    return Donator(row['id'], row['name'], row['email'])


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({'error': 'Login required'}), 401


def csrf_protect(f):
    """
    Verify the request's Origin header is one of our known frontends before
    allowing a state-changing (cookie-authenticated) request through.
    Session cookies are auto-attached cross-site (SameSite=None), so this
    replaces the CSRF protection that bearer tokens got "for free".
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        origin = request.headers.get('Origin', '')
        if origin not in ALLOWED_ORIGINS:
            app.logger.warning(f"Blocked request with untrusted Origin: {origin!r}")
            return jsonify({'error': 'Untrusted origin'}), 403
        return f(*args, **kwargs)
    return decorated


# NocoDB credentials (HIDDEN from frontend!)
NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')

NOCODB_DONATOR_BASE_ID = os.environ.get('NOCODB_DONATOR_BASE_ID')
NOCODB_AUCTION_BASE_ID = os.environ.get('NOCODB_AUCTION_BASE_ID')

TABLE_IDS = {
    'Donations and Tracking': 'mxe1093xcatdwzr',
    'Donator Profiles': 'mvga4wzvkiq52xx',
    'Public Calendar': 'm2pcy5vvdir11qr',
    'Team Calendar': 'm7d9kcnaqabtihu',
    'Announcements': 'muop1f8mhgos6uy',
    'Campaign Settings': 'm5k63e9xcuixxio',
    'Auction Items': 'm02kvrs08uiij89',
    'Bids': 'mw3pqffp5qhrrjj',
    'Donator FAQs': 'mrsh3g2gm19ytlf',
    'Donator Messages': 'm1udj4sgwj3fsm2',
}
ALLOWED_TABLES = list(TABLE_IDS.keys())

MIDDLEWARE_API_KEY = os.environ.get('MIDDLEWARE_API_KEY')

MILESTONE_STEP = 10000

print("Flask Configuration:")
print(f"   Environment: {FLASK_ENV}")
print(f"   NocoDB URL: {NOCODB_URL}")
print(f"   Donator Base ID: {NOCODB_DONATOR_BASE_ID}")
print(f"   Auction Base ID: {NOCODB_AUCTION_BASE_ID}")
print(f"   Token: {'Set' if NOCODB_TOKEN else 'Missing'}")
print(f"   Allowed Origins: {ALLOWED_ORIGINS}")
print(f"   API Key protection: {'Enabled' if MIDDLEWARE_API_KEY else 'DISABLED (no key set!)'}")


def nocodb_records_url(table_name, record_id=None):
    table_id = TABLE_IDS[table_name]
    base = f'{NOCODB_URL}/api/v2/tables/{table_id}/records'
    return f'{base}/{record_id}' if record_id else base


# ============= API KEY DECORATOR (unchanged — admin routes still use this) =============

def require_api_key(f):
    """Require a valid X-API-Key header for admin write operations."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not MIDDLEWARE_API_KEY:
            app.logger.warning("MIDDLEWARE_API_KEY not set - blocking write operation for safety")
            return jsonify({'error': 'Server misconfigured: write operations disabled'}), 503

        provided_key = request.headers.get('X-API-Key')
        if provided_key != MIDDLEWARE_API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401

        return f(*args, **kwargs)
    return decorated


def validate_table(table_name):
    return table_name in ALLOWED_TABLES


# ============= HEALTH CHECK =============

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        response = requests.get(
            f'{NOCODB_URL}/api/v2/meta/bases/{NOCODB_DONATOR_BASE_ID}/tables',
            headers=headers,
            timeout=5
        )

        nocodb_status = 'connected' if response.status_code == 200 else f'error ({response.status_code})'

        return jsonify({
            'status': 'healthy',
            'flask': 'running',
            'nocodb': nocodb_status,
            'donator_base_id': NOCODB_DONATOR_BASE_ID,
            'auction_base_id': NOCODB_AUCTION_BASE_ID
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# ============= DONATOR AUTH ROUTES =============

@app.route('/api/auth/register', methods=['POST'])
@csrf_protect
def register_donator():
    """Register a new donator account and start a session"""
    try:
        data = request.json or {}
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not name or not email or not password:
            return jsonify({'error': 'Name, email, and password are required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT id FROM donators WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'An account with this email already exists'}), 409

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO donators (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (name, email, password_hash)
        )
        new_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()

        login_user(Donator(new_id, name, email), remember=True)
        return jsonify({'name': name, 'email': email}), 201

    except Exception as e:
        app.logger.error(f"Register error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
@csrf_protect
def login_donator():
    """Log in an existing donator and start a session"""
    try:
        data = request.json or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        donator = get_donator_by_email(email)

        if not donator or not check_password_hash(donator['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        login_user(Donator(donator['id'], donator['name'], email), remember=True)
        return jsonify({'name': donator['name'], 'email': email}), 200

    except Exception as e:
        app.logger.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
@login_required
@csrf_protect
def logout_donator():
    logout_user()
    return jsonify({'message': 'Logged out'}), 200



# ============= DONATOR AUTH ROUTES - ACCOUNT MANAGEMENT =============


@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_donator():
    """Get the currently logged-in donator's info (used by frontend to check login state)"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT profile_picture FROM donators WHERE id = %s", (current_user.id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        picture_path = f"/profile-pictures/{row['profile_picture']}" if row and row['profile_picture'] else None

        return jsonify({
            'donator_id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'profile_picture': picture_path
        }), 200
    except Exception as e:
        app.logger.error(f"Get current donator error: {e}")
        return jsonify({'error': 'Failed to load account'}), 500


@app.route('/api/auth/me', methods=['PATCH'])
@login_required
@csrf_protect
def update_donator_name():
    """Update the current donator's display name"""
    try:
        data = request.json or {}
        name = data.get('name', '').strip()

        if not name:
            return jsonify({'error': 'Name is required'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE donators SET name = %s WHERE id = %s", (name, current_user.id))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'name': name}), 200

    except Exception as e:
        app.logger.error(f"Update name error: {e}")
        return jsonify({'error': 'Update failed'}), 500


# ============= DONATIONS ROUTES =============

@app.route('/api/donations', methods=['GET'])
@login_required
def get_donations():
    """Get donations belonging to the logged-in donator"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donations and Tracking')

        params = dict(request.args)
        params['where'] = f"(Donator Email,eq,{current_user.email})"

        response = requests.get(url, headers=headers, params=params)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get donations error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/donations', methods=['POST'])
@login_required
@csrf_protect
def create_donation():
    """Create a new donation (must be logged in — donator identity comes from session, not the request body)"""
    try:
        data = request.json or {}
        data['Donator Email'] = current_user.email
        data['Item Status'] = 'Submitted'  # always starts here regardless of what the client sends

        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Donations and Tracking')

        response = requests.post(url, headers=headers, json=data)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Create donation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/donations/<record_id>', methods=['GET'])
@login_required
def get_donation(record_id):
    """Get a specific donation — only if it belongs to the logged-in donator"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donations and Tracking', record_id)
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            record = response.json()
            if record.get('Donator Email') != current_user.email:
                return jsonify({'error': 'Not found'}), 404

        return jsonify(response.json()), response.status_code
    except Exception as e:
        app.logger.error(f"Get donation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/donations/<record_id>', methods=['PATCH', 'DELETE'])
@login_required
@csrf_protect
def donation_write_operations(record_id):
    """Update or delete a specific donation — only if it belongs to the logged-in donator"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}

        get_url = nocodb_records_url('Donations and Tracking', record_id)
        existing = requests.get(get_url, headers={'xc-token': NOCODB_TOKEN})
        if existing.status_code != 200 or existing.json().get('Donator Email') != current_user.email:
            return jsonify({'error': 'Not found'}), 404

        list_url = nocodb_records_url('Donations and Tracking')

        if request.method == 'PATCH':
            body = {**(request.json or {}), 'Id': int(record_id)}
            body.pop('Donator Email', None)
            body.pop('Item Status', None)
            response = requests.patch(list_url, headers=headers, json=body)
        else:
            body = {'Id': int(record_id)}
            response = requests.delete(list_url, headers=headers, json=body)

        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Donation operation error: {e}")
        return jsonify({'error': str(e)}), 500




# ============= MESSAGES ROUTES =============

@app.route('/api/messages', methods=['GET'])
@login_required
def get_messages():
    """Get the logged-in donator's own messages, most recent first."""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donator Messages')

        response = requests.get(url, headers=headers, params={
            'limit': 1000,
            'where': f"(Donator Email,eq,{current_user.email})",
            'sort': '-Created At'
        })
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records), response.status_code

    except Exception as e:
        app.logger.error(f"Get messages error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/messages', methods=['POST'])
@login_required
@csrf_protect
def send_message():
    """Submit a new message. Identity comes from the session, never the request body."""
    try:
        data = request.json or {}
        question = data.get('Question', '').strip()

        if not question:
            return jsonify({'error': 'Question is required'}), 400

        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Donator Messages')

        payload = {
            'Question': question,
            'Donator Email': current_user.email,
            'Donator Name': current_user.name,
            'Status': 'New'
        }

        response = requests.post(url, headers=headers, json=payload)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Send message error: {e}")
        return jsonify({'error': str(e)}), 500

    
# ============= PASSWORD ROUTES =============

@app.route('/api/auth/password', methods=['POST'])
@login_required
@csrf_protect
def change_password():
    """Change the current donator's password. Requires the correct current password."""
    try:
        data = request.json or {}
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')

        if not current_password or not new_password:
            return jsonify({'error': 'Current and new password are required'}), 400
        if len(new_password) < 8:
            return jsonify({'error': 'New password must be at least 8 characters'}), 400

        donator = get_donator_by_id(current_user.id)
        if not donator or not check_password_hash(donator['password_hash'], current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401

        new_hash = generate_password_hash(new_password)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE donators SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'message': 'Password updated'}), 200

    except Exception as e:
        app.logger.error(f"Change password error: {e}")
        return jsonify({'error': 'Password update failed'}), 500


    
# ============= CALENDAR ROUTES =============

@app.route('/api/calendar', methods=['GET'])
def get_calendar():
    """Get public calendar events"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Public Calendar')

        response = requests.get(url, headers=headers, params={'limit': 1000, **request.args})
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records), response.status_code

    except Exception as e:
        app.logger.error(f"Get calendar error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/calendar/team', methods=['GET'])
def get_team_calendar():
    """Get team calendar events"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Team Calendar')

        response = requests.get(url, headers=headers, params={'limit': 1000, **request.args})
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records), response.status_code

    except Exception as e:
        app.logger.error(f"Get team calendar error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= AUCTION ROUTES =============

@app.route('/api/auction/items', methods=['GET'])
def get_auction_items():
    """Get all auction items"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Auction Items')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get auction items error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auction/items/<item_id>', methods=['GET'])
def get_auction_item(item_id):
    """Get a single auction item by ID"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Auction Items', item_id)

        response = requests.get(url, headers=headers)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get auction item error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auction/items', methods=['POST'])
@require_api_key
def create_auction_item():
    """Create a new auction item (admin only)"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Auction Items')

        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Create auction item error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auction/items/<item_id>', methods=['PATCH', 'DELETE'])
@require_api_key
def auction_item_write_operations(item_id):
    """Update or delete an auction item (admin only)"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Auction Items')

        if request.method == 'PATCH':
            body = {**(request.json or {}), 'Id': int(item_id)}
            response = requests.patch(url, headers=headers, json=body)
        else:
            body = {'Id': int(item_id)}
            response = requests.delete(url, headers=headers, json=body)

        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Auction item operation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auction/bids', methods=['GET'])
def get_auction_bids():
    """Get all bids"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Bids')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get bids error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auction/bids', methods=['POST'])
def place_bid():
    """Place a new bid (public - no API key required, but validated)."""
    try:
        data = request.json or {}

        required_fields = ['item_id', 'bidder_name', 'bidder_email', 'amount']
        missing = [f for f in required_fields if f not in data or data[f] in (None, '')]
        if missing:
            return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

        try:
            amount = float(data['amount'])
            if amount <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({'error': 'Amount must be a positive number'}), 400

        try:
            item_id_int = int(data['item_id'])
        except (ValueError, TypeError):
            return jsonify({'error': 'item_id must be a valid integer'}), 400

        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}

        item_resp = requests.get(
            nocodb_records_url('Auction Items', item_id_int),
            headers={'xc-token': NOCODB_TOKEN}
        )
        if item_resp.status_code != 200:
            return jsonify({'error': 'Auction item not found'}), 404
        item = item_resp.json()

        current_bid = float(item.get('Current Bid') or item.get('Starting Bid') or 0)
        if amount <= current_bid:
            return jsonify({'error': f'Bid must be higher than the current bid (${current_bid:.2f})'}), 400

        bid_response = requests.post(nocodb_records_url('Bids'), headers=headers, json=data)
        if bid_response.status_code not in (200, 201):
            return jsonify(bid_response.json()), bid_response.status_code

        requests.patch(nocodb_records_url('Auction Items'), headers=headers, json={
            'Id': item_id_int,
            'Current Bid': amount,
            'Current Bidder Name': data['bidder_name']
        })

        recompute_running_total()

        return jsonify(bid_response.json()), bid_response.status_code

    except Exception as e:
        app.logger.error(f"Place bid error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= ANNOUNCEMENTS / CAMPAIGN =============

@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    """
    Public, read-only announcements for the home page feed.
    Only rows with 'Is Active' checked are returned; sorted by Priority (desc),
    then Created At (desc) as a tiebreaker.
    """
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Announcements')

        response = requests.get(url, headers=headers, params={
            'limit': 1000,
            'where': "(Is Active,eq,true)",
            'sort': '-Priority,-Created At'
        })
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records), response.status_code

    except Exception as e:
        app.logger.error(f"Get announcements error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/announcements', methods=['POST'])
@require_api_key
def create_announcement():
    """Create an announcement (admin only)"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Announcements')

        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Create announcement error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaign', methods=['GET'])
def get_campaign():
    """Get current campaign settings (countdown, donate link, etc.)"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Campaign Settings')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get campaign error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaign', methods=['PATCH'])
@require_api_key
def update_campaign():
    """Update campaign settings (admin only)"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Campaign Settings')

        response = requests.patch(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Update campaign error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaign-progress', methods=['GET'])
def get_campaign_progress():
    """
    Live fundraising total, read directly from Campaign Settings.Running Est Total --
    which is kept current automatically every time a bid is placed (see
    recompute_running_total()). No summing needed here; just a fast single read.
    """
    try:
        headers = {'xc-token': NOCODB_TOKEN}

        settings_resp = requests.get(nocodb_records_url('Campaign Settings'), headers=headers)
        settings_data = settings_resp.json()
        settings_records = settings_data.get('list', []) if isinstance(settings_data, dict) else settings_data
        settings = settings_records[0] if settings_records else {}

        total = float(settings.get('Running Est Total') or 0)

        current_milestone = int(total // MILESTONE_STEP) * MILESTONE_STEP
        next_milestone = current_milestone + MILESTONE_STEP
        progress_within_milestone = (total - current_milestone) / MILESTONE_STEP

        return jsonify({
            'total': total,
            'currentMilestone': current_milestone,
            'nextMilestone': next_milestone,
            'progressWithinMilestone': progress_within_milestone
        }), 200

    except Exception as e:
        app.logger.error(f"Get campaign progress error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaign-info', methods=['GET'])
def get_campaign_info():
    """
    Public, read-only campaign metadata (name, tagline, charity info, dates).
    Admins update this directly in NocoDB whenever a new auction/campaign starts --
    no app deploy required to change campaigns, including swapping the charity link.
    """
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        settings_resp = requests.get(nocodb_records_url('Campaign Settings'), headers=headers)
        settings_data = settings_resp.json()
        records = settings_data.get('list', []) if isinstance(settings_data, dict) else settings_data
        settings = records[0] if records else {}

        return jsonify({
            'name': settings.get('Campaign Name', ''),
            'tagline': settings.get('Tagline', ''),
            'charityName': settings.get('Charity Name', ''),
            'charityLogoUrl': settings.get('Charity Logo URL', ''),
            'charityWebsite': settings.get('Charity Website', ''),
            'charityDescription': settings.get('Charity Description', ''),
            'startDate': settings.get('Start Date', ''),
            'endDate': settings.get('End Date', '')
        }), 200

    except Exception as e:
        app.logger.error(f"Get campaign info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donator-faqs', methods=['GET'])
def get_donator_faqs():
    """
    Public, read-only FAQ content for the guides-faq page.
    Adding a new 'Topic' option in NocoDB automatically becomes a new tab
    client-side -- no code changes or deploys needed for new topics.
    """
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donator FAQs')

        response = requests.get(url, headers=headers, params={'limit': 1000, **request.args})
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records), response.status_code

    except Exception as e:
        app.logger.error(f"Get donator FAQs error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= GENERIC TABLE ROUTES (allowlisted) =============

@app.route('/api/tables/<table_name>', methods=['GET'])
def get_table_data(table_name):
    """Get data from an allowlisted table"""
    if table_name not in TABLE_IDS:
        return jsonify({'error': f'Table "{table_name}" is not accessible via this API'}), 403

    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url(table_name)

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get table error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<table_name>', methods=['POST'])
@require_api_key
def create_record(table_name):
    """Create record in an allowlisted table"""
    if table_name not in TABLE_IDS:
        return jsonify({'error': f'Table "{table_name}" is not accessible via this API'}), 403

    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url(table_name)

        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Create record error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<table_name>/<record_id>', methods=['GET'])
def get_table_record(table_name, record_id):
    """Get a specific record from an allowlisted table"""
    if table_name not in TABLE_IDS:
        return jsonify({'error': f'Table "{table_name}" is not accessible via this API'}), 403

    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url(table_name, record_id)
        response = requests.get(url, headers=headers)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get record error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<table_name>/<record_id>', methods=['PATCH', 'DELETE'])
@require_api_key
def table_record_write_operations(table_name, record_id):
    """Update or delete a specific record in an allowlisted table"""
    if table_name not in TABLE_IDS:
        return jsonify({'error': f'Table "{table_name}" is not accessible via this API'}), 403

    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url(table_name)

        if request.method == 'PATCH':
            body = {**(request.json or {}), 'Id': int(record_id)}
            body.pop('Donator Email', None)
            body.pop('Item Status', None)
            response = requests.patch(url, headers=headers, json=body)
        else:  # DELETE
            body = {'Id': int(record_id)}
            response = requests.delete(url, headers=headers, json=body)

        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Record operation error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= FILE UPLOAD =============

@app.route('/api/upload', methods=['POST'])
@login_required
@csrf_protect
def upload_files():
    """Upload files to NocoDB storage (any logged-in donator)"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        files = request.files.getlist('file')

        files_data = []
        for file in files:
            files_data.append(('file', (file.filename, file.stream, file.content_type)))

        headers = {'xc-token': NOCODB_TOKEN}
        url = f'{NOCODB_URL}/api/v1/db/storage/upload'

        response = requests.post(url, headers=headers, files=files_data)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= ROOT & ERROR HANDLERS =============

@app.route('/')
def index():
    """Root endpoint - API info"""
    return jsonify({
        'service': 'Roll4Rights Flask Middleware',
        'status': 'running',
        'endpoints': {
            'health': '/api/health',
            'donations': '/api/donations',
            'calendar': '/api/calendar',
            'team_calendar': '/api/calendar/team',
            'auction_items': '/api/auction/items',
            'auction_bids': '/api/auction/bids',
            'announcements': '/api/announcements',
            'campaign': '/api/campaign',
            'donator_faqs': '/api/donator-faqs',
            'upload': '/api/upload',
            'generic': '/api/tables/<table_name>'
        }
    }), 200

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/donator-profile', methods=['GET'])
@login_required
def get_donator_profile():
    """Fetch the logged-in donator's profile from NocoDB, if they've submitted one before."""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donator Profiles')
        params = {'where': f"(Donator Email,eq,{current_user.email})"}

        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        records = data.get('list', []) if isinstance(data, dict) else data

        return jsonify(records[0] if records else None), 200

    except Exception as e:
        app.logger.error(f"Get donator profile error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= DONATOR INFO ROUTES =============
@app.route('/api/donator-profile', methods=['POST'])
@login_required
@csrf_protect
def upsert_donator_profile():
    """
    Create or update the logged-in donator's profile in NocoDB.
    Donators are allowed to resubmit as many times as needed (e.g. fixing a typo) —
    this overwrites their existing profile rather than blocking a second submission.
    """
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Donator Profiles')

        existing = requests.get(
            url, headers={'xc-token': NOCODB_TOKEN},
            params={'where': f"(Donator Email,eq,{current_user.email})"}
        )
        existing_data = existing.json()
        existing_records = existing_data.get('list', []) if isinstance(existing_data, dict) else existing_data

        data = request.json or {}
        data['Donator Email'] = current_user.email

        if existing_records:
            data['Id'] = existing_records[0]['Id']
            response = requests.patch(url, headers=headers, json=data)
        else:
            response = requests.post(url, headers=headers, json=data)

        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Upsert donator profile error: {e}")
        return jsonify({'error': str(e)}), 500

def recompute_running_total():
    """
    Sums Current Bid across all Auction Items and writes the result to
    Campaign Settings.Running Est Total. Called right after a bid is placed
    so the field always reflects the live total -- both for the app's
    progress endpoint AND for anyone looking directly in NocoDB.
    """
    headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}

    items_resp = requests.get(nocodb_records_url('Auction Items'), headers={'xc-token': NOCODB_TOKEN}, params={'limit': 1000})
    items_data = items_resp.json()
    items = items_data.get('list', []) if isinstance(items_data, dict) else items_data
    total = sum(float(item.get('Current Bid') or 0) for item in items)

    settings_resp = requests.get(nocodb_records_url('Campaign Settings'), headers={'xc-token': NOCODB_TOKEN})
    settings_data = settings_resp.json()
    settings_records = settings_data.get('list', []) if isinstance(settings_data, dict) else settings_data

    if settings_records:
        requests.patch(nocodb_records_url('Campaign Settings'), headers=headers, json={
            'Id': settings_records[0]['Id'],
            'Running Est Total': total
        })

    return total

# ============= ACCOUNT ROUTES =============
"""Flask routes for managing account information in the donator app, such as uploading a profile picture, changing password, and updating username, NOT stored in the Donator Profiles table, stored in the Account Management table"""

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_IMAGE_DIMENSION = 1024
UPLOAD_FOLDER = os.path.join(
    os.environ.get('UPLOAD_STORAGE_PATH', os.path.join(app.root_path, 'uploads')),
    'profile_pictures'
)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB cap, applies globally

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/auth/profile-picture', methods=['POST'])
@login_required
@csrf_protect
def upload_profile_picture():
    """Upload/replace the current donator's profile picture"""
    try:
        if 'picture' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['picture']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PNG, JPG, and WEBP images are allowed'}), 400

        # Don't trust the extension - verify it's actually a decodable image
        try:
            image = Image.open(file.stream)
            image.verify()
            file.stream.seek(0)
            image = Image.open(file.stream)  # must reopen after verify()
        except Exception:
            return jsonify({'error': 'Invalid image file'}), 400

        # Re-encode & resize: strips EXIF/metadata, normalizes format,
        # and neutralizes any payload hidden in the original file bytes
        image = image.convert('RGB')
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))

        filename = f"{uuid.uuid4().hex}.jpg"  # never use the user-supplied filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        image.save(filepath, format='JPEG', quality=85)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT profile_picture FROM donators WHERE id = %s", (current_user.id,))
        old = cur.fetchone()

        cur.execute(
            "UPDATE donators SET profile_picture = %s WHERE id = %s",
            (filename, current_user.id)
        )
        conn.commit()
        cur.close()
        conn.close()

        # clean up the old file so uploads don't orphan on disk
        if old and old['profile_picture']:
            old_path = os.path.join(UPLOAD_FOLDER, old['profile_picture'])
            if os.path.exists(old_path):
                os.remove(old_path)

        return jsonify({'profile_picture': f'/profile-pictures/{filename}'}), 200

    except Exception as e:
        app.logger.error(f"Profile picture upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500


@app.route('/api/profile-pictures/<filename>', methods=['GET'])
def serve_profile_picture(filename):
    """Serve a profile picture by filename"""
    safe_name = os.path.basename(filename)  # blocks ../ path traversal
    return send_from_directory(UPLOAD_FOLDER, safe_name)




# ============= FORUM / CHAT (SOCKET.IO) =============

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        app.logger.warning("Rejected unauthenticated Socket.IO connection")
        return False


@socketio.on('join_channel')
def handle_join_channel(data):
    channel = data.get('channel')
    if not channel:
        return
    join_room(channel)
    history = get_channel_history(channel)
    emit('channel_history', {
        'channel': channel,
        'messages': [
            {
                'id': row['id'],
                'channel': row['channel'],
                'senderID': row['sender_id'],
                'senderName': row['sender_name'],
                'message': row['message'],
                'timestamp': row['created_at'].isoformat()
            }
            for row in history
        ]
    })


@socketio.on('leave_channel')
def handle_leave_channel(data):
    channel = data.get('channel')
    if channel:
        leave_room(channel)


@socketio.on('send_channel_message')
def handle_send_channel_message(data):
    channel = data.get('channel')
    message = (data.get('message') or '').strip()

    if not channel or not message:
        return

    saved = save_channel_message(channel, str(current_user.id), current_user.name, message)

    emit('channel_message', {
        'id': saved['id'],
        'channel': saved['channel'],
        'senderID': saved['sender_id'],
        'senderName': saved['sender_name'],
        'message': saved['message'],
        'timestamp': saved['created_at'].isoformat()
    }, room=channel)



# ============= INTRO THREADS ("Introduce Yourself") =============

@app.route('/api/forum/intro-threads', methods=['GET'])
@login_required
def list_intro_threads():
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 10
        rows, total = get_intro_threads(page=page, per_page=per_page)
        return jsonify({
            'threads': [
                {
                    'id': row['id'], 'donatorId': row['donator_id'], 'author': row['author_name'],
                    'title': row['title'], 'body': row['body'],
                    'createdAt': row['created_at'].isoformat(), 'replyCount': row['reply_count']
                }
                for row in rows
            ],
            'page': page,
            'totalPages': max(1, math.ceil(total / per_page))
        }), 200
    except Exception as e:
        app.logger.error(f"List intro threads error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-threads/mine', methods=['GET'])
@login_required
def get_my_intro_thread():
    try:
        row = get_intro_thread_by_donator(current_user.id)
        if not row:
            return jsonify(None), 200
        return jsonify({
            'id': row['id'], 'donatorId': row['donator_id'], 'author': row['author_name'],
            'title': row['title'], 'body': row['body'], 'createdAt': row['created_at'].isoformat()
        }), 200
    except Exception as e:
        app.logger.error(f"Get my intro thread error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-threads', methods=['POST'])
@login_required
@csrf_protect
def save_intro_thread():
    """Create or update the current donator's own intro thread."""
    try:
        data = request.json or {}
        title = data.get('title', '').strip()
        body = data.get('body', '').strip()
        if not title or not body:
            return jsonify({'error': 'Title and body are required'}), 400

        saved = upsert_intro_thread(current_user.id, current_user.name, title, body)
        return jsonify({
            'id': saved['id'], 'donatorId': saved['donator_id'], 'author': saved['author_name'],
            'title': saved['title'], 'body': saved['body'], 'createdAt': saved['created_at'].isoformat()
        }), 200
    except Exception as e:
        app.logger.error(f"Save intro thread error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-threads/<int:thread_id>', methods=['DELETE'])
@login_required
@csrf_protect
def remove_intro_thread(thread_id):
    try:
        owner_id = get_intro_thread_owner(thread_id)
        if owner_id is None or owner_id != current_user.id:
            return jsonify({'error': 'Not found'}), 404
        delete_intro_thread_by_id(thread_id)
        return jsonify({'message': 'Deleted'}), 200
    except Exception as e:
        app.logger.error(f"Delete intro thread error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-threads/<int:thread_id>/replies', methods=['GET'])
@login_required
def list_intro_replies(thread_id):
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = 10
        rows, total = get_intro_replies(thread_id, page=page, per_page=per_page)
        return jsonify({
            'replies': [
                {
                    'id': row['id'], 'threadId': row['thread_id'], 'donatorId': row['donator_id'],
                    'author': row['author_name'], 'message': row['message'],
                    'createdAt': row['created_at'].isoformat()
                }
                for row in rows
            ],
            'page': page,
            'totalPages': max(1, math.ceil(total / per_page))
        }), 200
    except Exception as e:
        app.logger.error(f"List intro replies error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-threads/<int:thread_id>/replies', methods=['POST'])
@login_required
@csrf_protect
def create_intro_reply(thread_id):
    try:
        data = request.json or {}
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        if get_intro_thread_owner(thread_id) is None:
            return jsonify({'error': 'Thread not found'}), 404

        saved = add_intro_reply(thread_id, current_user.id, current_user.name, message)
        return jsonify({
            'id': saved['id'], 'threadId': saved['thread_id'], 'donatorId': saved['donator_id'],
            'author': saved['author_name'], 'message': saved['message'],
            'createdAt': saved['created_at'].isoformat()
        }), 201
    except Exception as e:
        app.logger.error(f"Create intro reply error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum/intro-replies/<int:reply_id>', methods=['DELETE'])
@login_required
@csrf_protect
def remove_intro_reply(reply_id):
    try:
        owner_id = get_intro_reply_owner(reply_id)
        if owner_id is None or owner_id != current_user.id:
            return jsonify({'error': 'Not found'}), 404
        delete_intro_reply_by_id(reply_id)
        return jsonify({'message': 'Deleted'}), 200
    except Exception as e:
        app.logger.error(f"Delete intro reply error: {e}")
        return jsonify({'error': str(e)}), 500



# ============= FORUM MODERATION (admin key required) =============

@app.route('/api/forum-messages', methods=['GET'])
@require_api_key
def list_forum_messages():
    """List recent forum messages, optionally filtered with ?channel=, for moderation."""
    try:
        channel = request.args.get('channel')
        limit = int(request.args.get('limit', 200))
        rows = get_forum_messages_for_moderation(channel=channel, limit=limit)
        return jsonify([
            {
                'id': row['id'], 'channel': row['channel'],
                'senderID': row['sender_id'], 'senderName': row['sender_name'],
                'message': row['message'], 'timestamp': row['created_at'].isoformat()
            }
            for row in rows
        ]), 200
    except Exception as e:
        app.logger.error(f"List forum messages error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/forum-messages/<int:message_id>', methods=['DELETE'])
@require_api_key
def delete_forum_message(message_id):
    """Delete a single forum message (moderation)."""
    try:
        if not delete_forum_message_by_id(message_id):
            return jsonify({'error': 'Message not found'}), 404
        return jsonify({'message': 'Deleted'}), 200
    except Exception as e:
        app.logger.error(f"Delete forum message error: {e}")
        return jsonify({'error': str(e)}), 500



# ============= BACKGROUND TASKS =============

if __name__ == '__main__':
    debug_mode = FLASK_ENV == 'development'
    print("Starting Flask Middleware...")
    print(f"Proxying to NocoDB at {NOCODB_URL}")
    print(f"Debug mode: {debug_mode}")
    print("Token hidden from frontend")
    socketio.run(app, debug=debug_mode, port=5000, host='0.0.0.0')


