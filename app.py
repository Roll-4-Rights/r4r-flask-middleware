# imports
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# create the Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SESSION_TYPE'] = 'filesystem'

# configure CORS to allow requests from the frontend
CORS(app, supports_credentials=True, origins=[
    'http://localhost:5173', # Vite dev server
    'http://localhost:5174', # Another Vite dev server
    'http://localhost:3000', # React dev server
    'http://localhost:3001'  # Another React dev server
])
Session(app)

# NocoDB credentials (HIDDEN from frontend!)
NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080') # this is the nocodb server URL, defaulting to localhost for local dev
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN') # this is the nocodb API token, which should be kept secret and not exposed to the frontend
NOCODB_BASE_ID = os.environ.get('NOCODB_BASE_ID') # this is the main base ID for the R4R project in NocoDB
# NOCODB_CHAT_BASE_ID = os.environ.get('NOCODB_CHAT_BASE_ID', NOCODB_BASE_ID) # this is the base ID for the chat tables, defaulting to the main base if not set
# NOCODB_AUCTION_BASE_ID = os.environ.get('NOCODB_AUCTION_BASE_ID') # this is the base ID for the auction tables, defaulting to the main base if not set
# NOCODB_ITEMS_TABLE_ID = os.environ.get('NOCODB_ITEMS_TABLE_ID') # this is the table ID for the auction items table
# NOCODB_ANNOUNCEMENTS_TABLE_ID = os.environ.get('NOCODB_ANNOUNCEMENTS_TABLE_ID') # this is the table ID for the announcements table
# NOCODB_CAMPAIGN_TABLE_ID = os.getenv('NOCODB_CAMPAIGN_TABLE_ID') # this is the table ID for the campaign settings table

print("Flask Configuration:") # this is printed to the console for debugging purposes, but not exposed to the frontend
print(f"   NocoDB URL: {NOCODB_URL}")
print(f"   Main Base ID: {NOCODB_BASE_ID}")
print(f"   Token: {'Set' if NOCODB_TOKEN else 'Missing'}")


# ============= HEALTH CHECK =============
# this endpoint checks if the Flask server is running and if it can connect to NocoDB. It returns a JSON response with the status of both services.

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        response = requests.get(
            f'{NOCODB_URL}/api/v1/db/meta/projects',
            headers=headers,
            timeout=5
        )
        
        nocodb_status = 'connected' if response.status_code == 200 else 'error'
        
        return jsonify({
            'status': 'healthy',
            'flask': 'running',
            'nocodb': nocodb_status,
            'bases': {
                'main': NOCODB_BASE_ID,
                'chat': NOCODB_CHAT_BASE_ID
            }
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

# ============= DONATIONS ROUTES =============
# this endpoint proxies requests to the NocoDB Donations and Tracking table. It supports GET, POST, PATCH, and DELETE methods.

@app.route('/api/donations', methods=['GET']) # this endpoint gets all donations from the NocoDB Donations and Tracking table. It supports query parameters for filtering, sorting, and pagination.
def get_donations(): # this function handles the GET request to retrieve all donations from the NocoDB Donations and Tracking table. It forwards any query parameters from the request to NocoDB for filtering, sorting, and pagination.
    """Get all donations"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/Donations and Tracking'
        
        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Get donations error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donations', methods=['POST'])
def create_donation():
    """Create a new donation"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/Donations and Tracking'
        
        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Create donation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/donations/<record_id>', methods=['GET', 'PATCH', 'DELETE'])
def donation_operations(record_id):
    """Get, update, or delete a specific donation"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/Donations and Tracking/{record_id}'
        
        if request.method == 'GET':
            response = requests.get(url, headers=headers)
        elif request.method == 'PATCH':
            response = requests.patch(url, headers=headers, json=request.json)
        elif request.method == 'DELETE':
            response = requests.delete(url, headers=headers)
        
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
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/Public Calendar'
        
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
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/Team Calendar'
        
        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Get team calendar error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= GENERIC TABLE ROUTES (for flexibility) =============

@app.route('/api/tables/<table_name>', methods=['GET'])
def get_table_data(table_name):
    """Get data from any table in main R4R base"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/{table_name}'
        
        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Get table error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<table_name>', methods=['POST'])
def create_record(table_name):
    """Create record in any table"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/{table_name}'
        
        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Create record error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tables/<table_name>/<record_id>', methods=['GET', 'PATCH', 'DELETE'])
def table_record_operations(table_name, record_id):
    """Get, update, or delete a specific record"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_BASE_ID}/{table_name}/{record_id}'
        
        if request.method == 'GET':
            response = requests.get(url, headers=headers)
        elif request.method == 'PATCH':
            response = requests.patch(url, headers=headers, json=request.json)
        elif request.method == 'DELETE':
            response = requests.delete(url, headers=headers)
        
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Record operation error: {e}")
        return jsonify({'error': str(e)}), 500

    

# ============= AUCTION ROUTES =============
# Temporarily commented out - will enable when tables are created

# @app.route('/api/auction/items', methods=['GET'])
# def get_auction_items():
#     """Get all auction items"""
#     try:
#         headers = {'xc-token': NOCODB_TOKEN}
#         url = f'{NOCODB_URL}/api/v2/tables/{NOCODB_ITEMS_TABLE_ID}/records'
#         
#         response = requests.get(url, headers=headers, params=request.args)
#         return jsonify(response.json()), response.status_code
#         
#     except Exception as e:
#         app.logger.error(f"Get auction items error: {e}")
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/auction/items/<item_id>', methods=['GET'])
# def get_auction_item(item_id):
#     """Get a single auction item by ID"""
#     try:
#         headers = {'xc-token': NOCODB_TOKEN}
#         url = f'{NOCODB_URL}/api/v2/tables/{NOCODB_ITEMS_TABLE_ID}/records/{item_id}'
#         
#         response = requests.get(url, headers=headers)
#         return jsonify(response.json()), response.status_code
#         
#     except Exception as e:
#         app.logger.error(f"Get auction item error: {e}")
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/announcements', methods=['GET'])
# def get_announcements():
#     """Get all active announcements"""
#     try:
#         headers = {'xc-token': NOCODB_TOKEN}
#         url = f'{NOCODB_URL}/api/v2/tables/{NOCODB_ANNOUNCEMENTS_TABLE_ID}/records'
#         
#         response = requests.get(url, headers=headers, params=request.args)
#         return jsonify(response.json()), response.status_code
#         
#     except Exception as e:
#         app.logger.error(f"Get announcements error: {e}")
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/campaign', methods=['GET'])
# def get_campaign():
#     """Get current campaign settings (countdown, donate link, etc.)"""
#     try:
#         headers = {'xc-token': NOCODB_TOKEN}
#         url = f'{NOCODB_URL}/api/v2/tables/{NOCODB_CAMPAIGN_TABLE_ID}/records'
#         
#         response = requests.get(url, headers=headers, params=request.args)
#         return jsonify(response.json()), response.status_code
#         
#     except Exception as e:
#         app.logger.error(f"Get campaign error: {e}")
#         return jsonify({'error': str(e)}), 500

# ============= CHAT ROUTES =============

@app.route('/api/chat/user-messages', methods=['GET', 'POST'])
def user_chat_messages():
    """Get or create user chat messages"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_CHAT_BASE_ID}/UserChatMessages'
        
        if request.method == 'GET':
            response = requests.get(url, headers=headers, params=request.args)
        else:  # POST
            response = requests.post(url, headers=headers, json=request.json)
        
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"User chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/admin-team', methods=['GET', 'POST'])
def admin_team_messages():
    """Get or create admin team messages"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_CHAT_BASE_ID}/AdminTeamMessages'
        
        if request.method == 'GET':
            response = requests.get(url, headers=headers, params=request.args)
        else:  # POST
            response = requests.post(url, headers=headers, json=request.json)
        
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Admin team chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/admin-dm', methods=['GET', 'POST'])
def admin_dm_messages():
    """Get or create admin DM messages"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_CHAT_BASE_ID}/AdminDMMessages'
        
        if request.method == 'GET':
            response = requests.get(url, headers=headers, params=request.args)
        else:  # POST
            response = requests.post(url, headers=headers, json=request.json)
        
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Admin DM error: {e}")
        return jsonify({'error': str(e)}), 500

# ============= FILE UPLOAD =============

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Upload files to NocoDB storage"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        files = request.files.getlist('file')
        
        # Forward to NocoDB upload endpoint
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
            'user_chat': '/api/chat/user-messages',
            'admin_team': '/api/chat/admin-team',
            'admin_dm': '/api/chat/admin-dm',
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
    print("Starting Flask Middleware...")
    print(f"Proxying to NocoDB at {NOCODB_URL}")
    print("Token hidden from frontend")
    app.run(debug=True, port=5000, host='0.0.0.0')


