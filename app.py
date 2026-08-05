from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SESSION_TYPE'] = 'filesystem'

CORS(app, supports_credentials=True, origins=[
    'http://localhost:5173',  # Donator app
    'http://localhost:5174',  # Admin app
    'http://localhost:3001'   # Chat app
])
Session(app)

# NocoDB credentials (HIDDEN from frontend!)
NOCODB_URL = os.environ.get('NOCODB_URL', 'http://localhost:8080')
NOCODB_TOKEN = os.environ.get('NOCODB_TOKEN')
NOCODB_BASE_ID = os.environ.get('NOCODB_BASE_ID')
NOCODB_CHAT_BASE_ID = os.environ.get('NOCODB_CHAT_BASE_ID', NOCODB_BASE_ID)

print("✅ Flask Configuration:")
print(f"   NocoDB URL: {NOCODB_URL}")
print(f"   Main Base ID: {NOCODB_BASE_ID}")
print(f"   Chat Base ID: {NOCODB_CHAT_BASE_ID}")
print(f"   Token: {'✅ Set' if NOCODB_TOKEN else '❌ Missing'}")

# ============= HEALTH CHECK =============

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

# ============= MAIN BASE ROUTES (R4R) =============

@app.route('/api/tables/<table_name>', methods=['GET'])
def get_table_data(table_name):
    """Get data from main R4R base"""
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
    """Create record in main R4R base"""
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

# ============= CHAT BASE ROUTES =============

@app.route('/api/chat/messages', methods=['GET'])
def get_chat_messages():
    """Get chat messages from Chat base"""
    try:
        headers = {'xc-token': NOCODB_TOKEN}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_CHAT_BASE_ID}/Messages'
        
        response = requests.get(url, headers=headers, params=request.args)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Get messages error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/messages', methods=['POST'])
def create_chat_message():
    """Create chat message in Chat base"""
    try:
        headers = {'xc-token': NOCODB_TOKEN, 'Content-Type': 'application/json'}
        url = f'{NOCODB_URL}/api/v1/db/data/v1/{NOCODB_CHAT_BASE_ID}/Messages'
        
        response = requests.post(url, headers=headers, json=request.json)
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        app.logger.error(f"Create message error: {e}")
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
            'tables': '/api/tables/<table_name>',
            'chat': '/api/chat/messages',
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
    print("🚀 Starting Flask Middleware...")
    print(f"📡 Proxying to NocoDB at {NOCODB_URL}")
    print(f"🔒 Token hidden from frontend")
    app.run(debug=True, port=5000, host='0.0.0.0')