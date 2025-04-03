from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, abort, make_response
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime, timedelta
import subprocess
from functools import wraps
from flask_cors import CORS
import secrets

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key in production
CORS(app)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_FOLDER'] = 'static'
app.config['ALLOWED_IMAGE_EXTENSIONS'] = ['.jpg', '.jpeg', '.png', '.gif']
app.config['ALLOWED_AUDIO_EXTENSIONS'] = ['.mp3', '.wav', '.ogg']
app.config['ALLOWED_VIDEO_EXTENSIONS'] = ['.mp4', '.mov', '.avi']
app.config['ALLOWED_DOCUMENT_EXTENSIONS'] = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit

# NFC Access Control Configuration
app.config['NFC_TOKEN_VALIDITY'] = timedelta(minutes=5)  # Tokens expire after 5 minutes
app.config['SESSION_LIFETIME'] = timedelta(minutes=30)  # Session expires after 30 minutes of inactivity
valid_nfc_tokens = {}  # In-memory token storage (use Redis in production)

# Database setup
DATABASE = 'media.db'

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                media_type TEXT NOT NULL,
                upload_date TEXT NOT NULL
            )
        ''')
        db.commit()

def add_media(filename, filepath, media_type):
    db = get_db()
    db.execute(
        'INSERT INTO media (filename, filepath, media_type, upload_date) VALUES (?, ?, ?, ?)',
        (filename, filepath, media_type, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()

def get_media_by_type(media_type):
    db = get_db()
    cursor = db.execute('SELECT * FROM media WHERE media_type = ? ORDER BY upload_date DESC', (media_type,))
    return cursor.fetchall()

def get_all_media():
    db = get_db()
    cursor = db.execute('SELECT * FROM media ORDER BY upload_date DESC')
    return cursor.fetchall()

# Initialize database
init_db()

# Ensure upload folders exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'images'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'audio'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'videos'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'documents'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'videos', 'thumbs'), exist_ok=True)

# NFC Protection Functions
def nfc_protected(f):
    """Decorator to enforce NFC-only access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip NFC check for API endpoints and static files
        if request.path.startswith('/api/') or request.path.startswith('/static/'):
            return f(*args, **kwargs)
            
        # Skip NFC check for login/logout and nfc-auth endpoints
        if request.path in ['/login', '/logout', '/nfc-auth']:
            return f(*args, **kwargs)
            
        # Check if user has a valid NFC session
        if not session.get('nfc_authenticated'):
            # Special case: if accessing root URL, redirect to nfc-auth
            if request.path == '/':
                return redirect(url_for('nfc_auth'))
            abort(403, description="Access denied. Please scan the NFC tag to access this content.")
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/nfc-auth')
def nfc_auth():
    """Endpoint that the NFC tag should point to - generates a one-time token"""
    # Generate a unique token
    token = secrets.token_urlsafe(32)
    valid_nfc_tokens[token] = {
        'valid_until': datetime.now() + app.config['NFC_TOKEN_VALIDITY'],
        'used': False,
        'ip_address': request.remote_addr
    }
    
    # Redirect to main page with token
    response = make_response(redirect(url_for('index', nfc_token=token)))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.before_request
def check_nfc_access():
    """Check NFC authentication before processing requests"""
    # Skip checks for static files and API endpoints
    if request.path.startswith('/static/') or request.path.startswith('/api/'):
        return
        
    # Skip checks for login/logout and nfc-auth endpoints
    if request.path in ['/login', '/logout', '/nfc-auth']:
        return
    
    # Check for NFC token in the initial access
    token = request.args.get('nfc_token')
    if token and token in valid_nfc_tokens:
        token_data = valid_nfc_tokens[token]
        
        # Check if token is valid and not expired
        if (datetime.now() <= token_data['valid_until'] and 
            not token_data['used']):
            
            # Mark token as used
            valid_nfc_tokens[token]['used'] = True
            
            # Create authenticated session
            session['nfc_authenticated'] = True
            session.permanent = True
            app.permanent_session_lifetime = app.config['SESSION_LIFETIME']
            
            # Remove the token from URL after validation
            if request.args.get('nfc_token'):
                response = make_response(redirect(url_for('index')))
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                return response
    
    # For all other requests, verify the session
    if not session.get('nfc_authenticated') and request.path != '/':
        abort(403, description="Access denied. Please scan the NFC tag to access this content.")

@app.template_filter('format_date')
def format_date_filter(value):
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime('%b %d, %Y')

def generate_video_thumbnail(video_path, thumb_path):
    """Generate thumbnail using FFmpeg"""
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

@app.route('/')
@nfc_protected
def index():
    return render_template('index.html')

@app.route('/api/media', methods=['GET'])
def get_all_media_api():
    media_type = request.args.get('type')
    
    try:
        if media_type:
            media = get_media_by_type(media_type)
        else:
            media = get_all_media()
        
        media_list = []
        for item in media:
            # Construct correct file paths
            filepath = item['filepath'].replace('static/', '')
            static_path = f"/static/{filepath}"
            
            media_item = {
                'id': item['id'],
                'filename': item['filename'],
                'filepath': static_path,
                'media_type': item['media_type'],
                'upload_date': item['upload_date']
            }
            
            # Add thumbnail path for videos
            if item['media_type'] == 'videos':
                thumb_filename = os.path.splitext(item['filename'])[0] + '.jpg'
                thumb_path = f"videos/thumbs/{thumb_filename}"
                thumb_full_path = os.path.join(app.config['STATIC_FOLDER'], thumb_path)
                
                # Check if thumbnail exists
                if os.path.exists(thumb_full_path):
                    media_item['thumbnail'] = f"/static/{thumb_path}"
                else:
                    # Try to generate thumbnail if it doesn't exist
                    video_full_path = os.path.join(app.config['STATIC_FOLDER'], filepath)
                    if generate_video_thumbnail(video_full_path, thumb_full_path):
                        media_item['thumbnail'] = f"/static/{thumb_path}"
            
            media_list.append(media_item)
        
        return jsonify({
            'success': True,
            'data': media_list
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
@nfc_protected
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        file = request.files['file']
        media_type = request.form.get('media_type')
        
        if file and media_type in ['images', 'audio', 'videos', 'documents']:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Validate file extension
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
                # Save to static folder
                static_subfolder = os.path.join(app.config['STATIC_FOLDER'], media_type)
                static_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                static_path = os.path.join(static_subfolder, static_filename)
                file.save(static_path)
                
                # Generate thumbnail if video
                if media_type == 'videos':
                    thumb_filename = os.path.splitext(static_filename)[0] + '.jpg'
                    thumb_path = os.path.join(app.config['STATIC_FOLDER'], 'videos', 'thumbs', thumb_filename)
                    if not generate_video_thumbnail(static_path, thumb_path):
                        flash('Video uploaded but thumbnail generation failed', 'warning')
                
                # Add to database
                db_path = os.path.join(media_type, static_filename).replace('\\', '/')
                add_media(filename, db_path, media_type)
                flash(f'{media_type.capitalize()} uploaded successfully!', 'success')
                
            except Exception as e:
                print(f"Error uploading file: {str(e)}")
                flash('Error uploading file', 'error')
    
    return render_template('upload.html')

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

# Add no-cache headers to all responses
@app.after_request
def add_no_cache(response):
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Clean up expired tokens periodically
def cleanup_tokens():
    now = datetime.now()
    expired_tokens = [token for token, data in valid_nfc_tokens.items() 
                     if now > data['valid_until']]
    for token in expired_tokens:
        valid_nfc_tokens.pop(token, None)

# Schedule token cleanup (simple in-memory version)
@app.before_request
def before_req():
    cleanup_tokens()

if __name__ == '__main__':
    app.run(debug=True)