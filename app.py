from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, make_response
from werkzeug.utils import secure_filename
import os
from config import Config
import subprocess
from datetime import datetime
from database import init_db, add_media, get_media_by_type

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
init_db()

# Ensure upload folders exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'images'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'audio'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
os.makedirs(os.path.join('static', 'videos', 'thumbs'), exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.template_filter('format_date')
def format_date_filter(value):
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    return value.strftime('%b %d, %Y')

@app.route('/gallery')
def gallery():
    images = get_media_by_type('images')
    audio = get_media_by_type('audio')
    videos = get_media_by_type('videos')
    return render_template('gallery.html', 
                         images=images, 
                         audio=audio, 
                         videos=videos)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['logged_in'] = True
            return redirect(url_for('upload'))
        else:
            flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

def generate_video_thumbnail(video_path, thumb_path):
    """Generate thumbnail using FFmpeg"""
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:01',  # Capture at 1 second
            '-vframes', '1',
            '-q:v', '2',         # Quality level
            '-y',                # Overwrite without asking
            thumb_path
        ]
        subprocess.run(cmd, check=True, 
                      stdout=subprocess.PIPE, 
                      stderr=subprocess.PIPE,
                      timeout=30)  # 30 second timeout
        return True
    except subprocess.CalledProcessError as e:
        app.logger.error(f"Thumbnail generation failed: {e.stderr.decode()}")
        return False
    except Exception as e:
        app.logger.error(f"Error generating thumbnail: {str(e)}")
        return False

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        file = request.files['file']
        media_type = request.form.get('media_type')
        
        if file and media_type in ['images', 'audio', 'videos']:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            
            # Validate file extension
            allowed_extensions = {
                'images': ['.jpg', '.jpeg', '.png', '.gif'],
                'audio': ['.mp3', '.wav', '.ogg'],
                'videos': ['.mp4', '.mov', '.avi']
            }
            
            if file_ext not in allowed_extensions[media_type]:
                flash(f'Invalid file extension for {media_type}', 'error')
                return redirect(url_for('upload'))
            
            try:
                # Save to uploads folder
                upload_subfolder = os.path.join(app.config['UPLOAD_FOLDER'], media_type)
                os.makedirs(upload_subfolder, exist_ok=True)
                filepath = os.path.join(upload_subfolder, filename)
                file.save(filepath)
                
                # Save to static folder for serving
                static_subfolder = os.path.join('static', media_type)
                os.makedirs(static_subfolder, exist_ok=True)
                static_path = os.path.join(static_subfolder, filename)
                file.seek(0)  # Reset file pointer
                file.save(static_path)
                
                # Generate thumbnail if video
                if media_type == 'videos':
                    thumb_folder = os.path.join('static', 'videos', 'thumbs')
                    os.makedirs(thumb_folder, exist_ok=True)
                    thumb_path = os.path.join(thumb_folder, filename + '.jpg')
                    if not generate_video_thumbnail(filepath, thumb_path):
                        flash('Video uploaded but thumbnail generation failed', 'warning')
                
                # Add to database
                add_media(filename, static_path, media_type)
                flash(f'{media_type.capitalize()} uploaded successfully!', 'success')
                
            except Exception as e:
                app.logger.error(f"Error uploading file: {str(e)}")
                flash('Error uploading file', 'error')
    
    return render_template('upload.html')

@app.route('/download')
def download():
    return render_template('download.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/service-worker.js')
def service_worker():
    response = make_response(send_from_directory('.', 'service-worker.js'))
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)