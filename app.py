from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, abort
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
app.secret_key = 'your_secret_key_here'
CORS(app)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['STATIC_FOLDER'] = 'static'
app.config['ALLOWED_IMAGE_EXTENSIONS'] = ['.jpg', '.jpeg', '.png', '.gif']
app.config['ALLOWED_AUDIO_EXTENSIONS'] = ['.mp3', '.wav', '.ogg']
app.config['ALLOWED_VIDEO_EXTENSIONS'] = ['.mp4', '.mov', '.avi']
app.config['ALLOWED_DOCUMENT_EXTENSIONS'] = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB limit

# In-memory request logs
request_logs = []

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
for sub in ['images', 'audio', 'videos', 'documents', 'videos/thumbs']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], sub), exist_ok=True)
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

@app.route('/')
def index():
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
            media = get_media_by_type(media_type)
        else:
            media = get_all_media()

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
    session.pop('logged_in', None)
    return redirect(url_for('index'))

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
                add_media(filename, db_path, media_type)
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

if __name__ == '__main__':
    app.run(debug=True)
