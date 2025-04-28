from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime, timedelta
import subprocess
from functools import wraps
from flask_cors import CORS
import secrets

# Import Config and database functions
from config import Config, get_allowed_extensions
import database as db

app = Flask(__name__)

# --- Load Configuration from config.py ---
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']  # Set secret key from loaded config
# ----------------------------------------

CORS(app)

# Load UIDs from file
def load_uids_from_file(file_path='uid.txt'):
    valid_uids = set()
    try:
        with open(file_path, 'r') as f:
            for line in f:
                uid = line.strip()
                if uid:  # Skip empty lines
                    valid_uids.add(uid)
        return valid_uids
    except Exception as e:
        print(f"Error loading UIDs from file: {e}")
        return set()

def reload_uids():
    """Reload UIDs from file without server restart"""
    global VALID_UIDS
    VALID_UIDS = load_uids_from_file()
    print(f"Reloaded {len(VALID_UIDS)} UIDs from whitelist file")
    return VALID_UIDS

VALID_UIDS = load_uids_from_file()
print(f"Loaded {len(VALID_UIDS)} UIDs from whitelist file")

# In-memory request logs
request_logs = []

# Initialize database using the function from database.py
db.init_db()

# Ensure upload folders exist using paths from loaded config
for sub in ['images', 'audio', 'videos', 'documents', 'videos/thumbs']:
    os.makedirs(os.path.join(app.config['STATIC_FOLDER'], sub), exist_ok=True)

@app.before_request
def log_request_info():
    if request.path.startswith('/static') or request.path == '/unlock':
        return
    try:
        log_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'method': request.method,
            'path': request.path,
            'headers': dict(request.headers),
            'args': request.args.to_dict(),
            'form': request.form.to_dict(),
            'json': request.get_json(silent=True),
            'remote_addr': request.remote_addr
        }
        request_logs.append(log_entry)
        if len(request_logs) > 1000:
            request_logs.pop(0)
    except Exception as e:
        print(f"Error logging request: {e}")

def nfc_protected_route(f):
    """Decorator to protect routes, requiring a valid NFC unlock session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        unlock_token = session.get('nfc_unlock_token')
        # Validate the token using the database function
        if not unlock_token or not db.validate_unlock_token(unlock_token):
            # Clear the invalid token from session
            if unlock_token:
                print(f"Clearing invalid/expired unlock token from session")
                session.pop('nfc_unlock_token', None)
                
            # Check if login is also required for this route (added via login_required decorator)
            is_login_required = getattr(f, 'login_required', False)
            if is_login_required and not session.get('logged_in'):
                # If login is required but user isn't logged in, prioritize login redirect
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            else:
                # If login isn't required or user is logged in, but NFC is missing/invalid
                flash('Access denied. Please scan a valid NFC tag.', 'error')
                # Redirect to login page (or a dedicated access denied page)
                return redirect(url_for('login'))
        # If token is valid, proceed with the original route function
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Displays the main page, likely showing media."""
    # This route now requires NFC unlock first
    return render_template('index.html')

@app.template_filter('format_date')
def format_date_filter(value):
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime('%b %d, %Y')

def generate_video_thumbnail(video_path, thumb_path):
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:01',
            '-vframes', '1',
            '-q:v', '2',
            '-vf', 'scale=300:-1',
            '-y',
            thumb_path
        ]
        subprocess.run(cmd, check=True,
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,
                      timeout=30)
        return True
    except Exception as e:
        print(f"Error generating thumbnail: {str(e)}")
        return False

@app.route('/api/media', methods=['GET'])
def get_all_media_api():
    media_type = request.args.get('type')
    try:
        if media_type:
            media = db.get_media_by_type(media_type)
        else:
            media = db.get_all_media()

        media_list = []
        for item in media:
            filepath = item['filepath'].replace('static/', '')
            static_path = f"/static/{filepath}"
            media_item = {
                'id': item['id'],
                'filename': item['filename'],
                'filepath': static_path,
                'media_type': item['media_type'],
                'upload_date': item['upload_date']
            }
            if item['media_type'] == 'videos':
                thumb_filename = os.path.splitext(item['filename'])[0] + '.jpg'
                thumb_path = f"videos/thumbs/{thumb_filename}"
                thumb_full_path = os.path.join(app.config['STATIC_FOLDER'], thumb_path)
                if os.path.exists(thumb_full_path):
                    media_item['thumbnail'] = f"/static/{thumb_path}"
                else:
                    video_full_path = os.path.join(app.config['STATIC_FOLDER'], filepath)
                    if generate_video_thumbnail(video_full_path, thumb_full_path):
                        media_item['thumbnail'] = f"/static/{thumb_path}"
            media_list.append(media_item)

        return jsonify({'success': True, 'data': media_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'password':
            session['logged_in'] = True
            return redirect(url_for('upload'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs the user out and clears all session data."""
    # Clear specific keys
    session.pop('logged_in', None)
    session.pop('nfc_unlock_token', None)
    
    # For complete security, clear the entire session
    session.clear()
    
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))  # Redirect to login after logout

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files['file']
        media_type = request.form.get('media_type')

        if file and media_type in ['images', 'audio', 'videos', 'documents']:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()

            allowed_extensions = {
                'images': app.config['ALLOWED_IMAGE_EXTENSIONS'],
                'audio': app.config['ALLOWED_AUDIO_EXTENSIONS'],
                'videos': app.config['ALLOWED_VIDEO_EXTENSIONS'],
                'documents': app.config['ALLOWED_DOCUMENT_EXTENSIONS']
            }

            if file_ext not in allowed_extensions[media_type]:
                flash(f'Invalid file extension for {media_type}', 'error')
                return redirect(url_for('upload'))

            try:
                static_subfolder = os.path.join(app.config['STATIC_FOLDER'], media_type)
                static_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                static_path = os.path.join(static_subfolder, static_filename)
                file.save(static_path)

                if media_type == 'videos':
                    thumb_filename = os.path.splitext(static_filename)[0] + '.jpg'
                    thumb_path = os.path.join(app.config['STATIC_FOLDER'], 'videos', 'thumbs', thumb_filename)
                    if not generate_video_thumbnail(static_path, thumb_path):
                        flash('Video uploaded but thumbnail generation failed', 'warning')

                db_path = os.path.join(media_type, static_filename).replace('\\', '/')
                db.add_media(filename, db_path, media_type)
                flash(f'{media_type.capitalize()} uploaded successfully!', 'success')

            except Exception as e:
                print(f"Error uploading file: {str(e)}")
                flash('Error uploading file', 'error')

    return render_template('upload.html')

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.route('/request-logs')
def show_request_logs():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('request_logs.html', logs=reversed(request_logs))

@app.route('/unlock', methods=['GET'])
def unlock_via_nfc():
    """Endpoint triggered by NFC scan. Validates tag and creates unlock session."""
    scanned_token = request.args.get('nfc_token')
    if not scanned_token:
        flash('NFC token missing in unlock attempt.', 'error')
        return redirect(url_for('login'))
        
    # Check if already unlocked with a valid token - prevents token refresh attacks
    # First check if there's an existing token in the session
    existing_token = session.get('nfc_unlock_token')
    if existing_token and db.validate_unlock_token(existing_token):
        print(f"Already has valid unlock token - preventing new token generation")
        flash('Already unlocked! Access maintained.', 'info')
        return redirect(url_for('index'))
    
    # Clear any existing invalid session token
    if existing_token:
        session.pop('nfc_unlock_token', None)
    
    # Check if scanned NFC token is in valid list
    if scanned_token in VALID_UIDS:
        unlock_token = secrets.token_urlsafe()
        session['nfc_unlock_token'] = unlock_token
        db.add_unlock_token(unlock_token)
        flash('NFC tag validated. You are now unlocked!', 'success')
        return redirect(url_for('index'))
    else:
        flash('Invalid NFC tag detected!', 'error')
        return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
