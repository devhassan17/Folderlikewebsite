from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory, jsonify, abort, make_response
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime, timedelta
import subprocess
from functools import wraps
import secrets

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secure random key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_FOLDER'] = 'static'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['ALLOWED_EXTENSIONS'] = {
    'images': ['.jpg', '.jpeg', '.png', '.gif'],
    'audio': ['.mp3', '.wav', '.ogg'],
    'videos': ['.mp4', '.mov', '.avi'],
    'documents': ['.pdf', '.doc', '.docx', '.txt']
}

# NFC access tracking (use Redis in production)
nfc_access_tracker = {}

# Database setup
def get_db():
    db = sqlite3.connect('media.db')
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

init_db()

# Create required directories
for folder in ['images', 'audio', 'videos', 'documents']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], folder), exist_ok=True)
    os.makedirs(os.path.join(app.config['STATIC_FOLDER'], folder), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'videos', 'thumbs'), exist_ok=True)

@app.before_request
def handle_nfc_authentication():
    """Handle NFC-based authentication without requiring tag modifications"""
    # Skip authentication for static files and API endpoints
    if request.path.startswith(('/static/', '/api/', '/login', '/logout')):
        return
    
    client_ip = request.remote_addr
    now = datetime.now()
    
    # Detect NFC scan (rapid subsequent access from same IP)
    if client_ip in nfc_access_tracker:
        elapsed = (now - nfc_access_tracker[client_ip]).total_seconds()
        if elapsed < 2:  # NFC scan detected (within 2 seconds)
            session['nfc_authenticated'] = True
            session.permanent = True
    
    # Update last access time
    nfc_access_tracker[client_ip] = now
    
    # Clean up old entries (older than 1 minute)
    for ip in list(nfc_access_tracker.keys()):
        if (now - nfc_access_tracker[ip]).total_seconds() > 60:
            nfc_access_tracker.pop(ip, None)

def nfc_protected(f):
    """Decorator to enforce NFC-only access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('nfc_authenticated'):
            abort(403, "Access denied. Please scan the NFC tag.")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if not session.get('nfc_authenticated'):
        # Create a page that prompts user to scan NFC
        resp = make_response(render_template('nfc_prompt.html'))
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp
    return render_template('index.html')

@app.route('/api/media')
@nfc_protected
def get_media():
    media_type = request.args.get('type', '')
    
    try:
        db = get_db()
        if media_type and media_type in app.config['ALLOWED_EXTENSIONS']:
            media = db.execute('SELECT * FROM media WHERE media_type = ? ORDER BY upload_date DESC', 
                             (media_type,)).fetchall()
        else:
            media = db.execute('SELECT * FROM media ORDER BY upload_date DESC').fetchall()
        
        media_list = []
        for item in media:
            media_item = {
                'id': item['id'],
                'filename': item['filename'],
                'filepath': f"/static/{item['filepath']}",
                'media_type': item['media_type'],
                'upload_date': item['upload_date']
            }
            
            if item['media_type'] == 'videos':
                thumb_path = f"videos/thumbs/{os.path.splitext(item['filename'])[0]}.jpg"
                if os.path.exists(os.path.join(app.config['STATIC_FOLDER'], thumb_path)):
                    media_item['thumbnail'] = f"/static/{thumb_path}"
            
            media_list.append(media_item)
        
        return jsonify({'success': True, 'data': media_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
@nfc_protected
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'password':  # Change in production!
            session['logged_in'] = True
            return redirect(url_for('upload'))
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
        file = request.files.get('file')
        media_type = request.form.get('media_type')
        
        if file and media_type in app.config['ALLOWED_EXTENSIONS']:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in app.config['ALLOWED_EXTENSIONS'][media_type]:
                flash('Invalid file type', 'error')
                return redirect(url_for('upload'))
            
            try:
                filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
                save_path = os.path.join(app.config['STATIC_FOLDER'], media_type, filename)
                file.save(save_path)
                
                if media_type == 'videos':
                    thumb_name = f"{os.path.splitext(filename)[0]}.jpg"
                    thumb_path = os.path.join(app.config['STATIC_FOLDER'], 'videos', 'thumbs', thumb_name)
                    if not generate_thumbnail(save_path, thumb_path):
                        flash('Video uploaded but thumbnail failed', 'warning')
                
                db = get_db()
                db.execute(
                    'INSERT INTO media (filename, filepath, media_type, upload_date) VALUES (?, ?, ?, ?)',
                    (file.filename, f"{media_type}/{filename}", media_type, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
                db.commit()
                flash('Upload successful!', 'success')
            except Exception as e:
                flash(f'Upload failed: {str(e)}', 'error')
    
    return render_template('upload.html')

def generate_thumbnail(video_path, thumb_path):
    """Generate video thumbnail using ffmpeg"""
    try:
        subprocess.run([
            'ffmpeg', '-i', video_path,
            '-ss', '00:00:01', '-vframes', '1',
            '-q:v', '2', '-vf', 'scale=300:-1',
            '-y', thumb_path
        ], check=True, timeout=30)
        return True
    except Exception:
        return False

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)