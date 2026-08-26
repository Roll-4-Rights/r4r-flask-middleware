# imports
from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import os
import jwt
import datetime
from dotenv import load_dotenv
from db import get_db_connection, init_donators_table

load_dotenv()

# create the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

# Ensure the donators table exists (separate from NocoDB, not visible in its UI)
init_donators_table()

JWT_SECRET = os.environ.get('JWT_SECRET', app.config['SECRET_KEY'])

def generate_token(donator_id, email):
    payload = {
        'donator_id': donator_id,
        'email': email,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

# ============= ENVIRONMENT CONFIG =============

FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

# configure CORS to allow requests from the frontend (env-driven, no hardcoded localhost in prod)
ALLOWED_ORIGINS = os.environ.get(
    'ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:5174,http://localhost:3000,http://localhost:3001'
).split(',')

CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)

# NocoDB credentials (HIDDEN from frontend!)
NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')

# Kept for reference/health check only — actual record operations use table IDs below
NOCODB_DONATOR_BASE_ID = os.environ.get('NOCODB_DONATOR_BASE_ID')
NOCODB_AUCTION_BASE_ID = os.environ.get('NOCODB_AUCTION_BASE_ID')

# NocoDB v2 records API requires table IDs, not table names.
# These are stable once created — get them via scripts/get_table_ids.py if they ever change.
TABLE_IDS = {
    'Donations and Tracking': 'mvfbfkw4tndofk7',
    'Public Calendar': 'm2pcy5vvdir11qr',
    'Team Calendar': 'm7d9kcnaqabtihu',
    'Announcements': 'muop1f8mhgos6uy',
    'Campaign Settings': 'mf0h6hpznxy4v1g',
    'Auction Items': 'm02kvrs08uiij89',
    'Bids': 'mw3pqffp5qhrrjj',
}
ALLOWED_TABLES = list(TABLE_IDS.keys())

# API key required for write operations (POST/PATCH/DELETE)
MIDDLEWARE_API_KEY = os.environ.get('MIDDLEWARE_API_KEY')

print("Flask Configuration:")
print(f"   Environment: {FLASK_ENV}")
print(f"   NocoDB URL: {NOCODB_URL}")
print(f"   Donator Base ID: {NOCODB_DONATOR_BASE_ID}")
print(f"   Auction Base ID: {NOCODB_AUCTION_BASE_ID}")
print(f"   Token: {'Set' if NOCODB_TOKEN else 'Missing'}")
print(f"   Allowed Origins: {ALLOWED_ORIGINS}")
print(f"   API Key protection: {'Enabled' if MIDDLEWARE_API_KEY else 'DISABLED (no key set!)'}")


def nocodb_records_url(table_name, record_id=None):
    """Build a v2 records API URL for a given logical table name."""
    table_id = TABLE_IDS[table_name]
    base = f'{NOCODB_URL}/api/v2/tables/{table_id}/records'
    return f'{base}/{record_id}' if record_id else base


# ============= AUTH DECORATOR =============

def require_api_key(f):
    """Require a valid X-API-Key header for write operations."""
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


def require_donator_auth(f):
    """Require a valid donator JWT (Authorization: Bearer <token>)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        token = auth_header.split(' ', 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired, please log in again'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        request.donator_id = payload['donator_id']
        request.donator_email = payload['email']
        return f(*args, **kwargs)
    return decorated


def validate_table(table_name):
    """Only allow access to known/expected tables via generic routes."""
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
def register_donator():
    """Register a new donator account"""
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

        token = generate_token(new_id, email)
        return jsonify({'token': token, 'name': name, 'email': email}), 201

    except Exception as e:
        app.logger.error(f"Register error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login_donator():
    """Log in an existing donator"""
    try:
        data = request.json or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, password_hash FROM donators WHERE email = %s", (email,))
        donator = cur.fetchone()
        cur.close()
        conn.close()

        if not donator or not check_password_hash(donator['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        token = generate_token(donator['id'], email)
        return jsonify({'token': token, 'name': donator['name'], 'email': email}), 200

    except Exception as e:
        app.logger.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
@require_donator_auth
def get_current_donator():
    """Get the currently logged-in donator's info (used by frontend to check login state)"""
    return jsonify({
        'donator_id': request.donator_id,
        'email': request.donator_email
    }), 200

# ============= DONATIONS ROUTES =============

@app.route('/api/donations', methods=['GET'])
def get_donations():
    """Get all donations"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donations and Tracking')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get donations error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donations', methods=['POST'])
@require_api_key
def create_donation():
    """Create a new donation"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Donations and Tracking')

        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Create donation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donations/<record_id>', methods=['GET'])
def get_donation(record_id):
    """Get a specific donation"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Donations and Tracking', record_id)
        response = requests.get(url, headers=headers)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        app.logger.error(f"Get donation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donations/<record_id>', methods=['PATCH', 'DELETE'])
@require_api_key
def donation_write_operations(record_id):
    """Update or delete a specific donation"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Donations and Tracking')

        if request.method == 'PATCH':
            body = {**(request.json or {}), 'Id': int(record_id)}
            response = requests.patch(url, headers=headers, json=body)
        else:  # DELETE
            body = {'Id': int(record_id)}
            response = requests.delete(url, headers=headers, json=body)

        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Donation operation error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= CALENDAR ROUTES =============

@app.route('/api/calendar', methods=['GET'])
def get_calendar():
    """Get public calendar events"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Public Calendar')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Get calendar error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/calendar/team', methods=['GET'])
def get_team_calendar():
    """Get team calendar events"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Team Calendar')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

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
    """Place a new bid (public - no API key required, but validated)"""
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

        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = nocodb_records_url('Bids')

        response = requests.post(url, headers=headers, json=data)
        return jsonify(response.json()), response.status_code

    except Exception as e:
        app.logger.error(f"Place bid error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= ANNOUNCEMENTS / CAMPAIGN =============

@app.route('/api/announcements', methods=['GET'])
def get_announcements():
    """Get all active announcements"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = nocodb_records_url('Announcements')

        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code

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
@require_api_key
def upload_files():
    """Upload files to NocoDB storage (admin only)"""
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

if __name__ == '__main__':
    debug_mode = FLASK_ENV == 'development'

    print("Starting Flask Middleware...")
    print(f"Proxying to NocoDB at {NOCODB_URL}")
    print(f"Debug mode: {debug_mode}")
    print("Token hidden from frontend")
    app.run(debug=debug_mode, port=5000, host='0.0.0.0')


