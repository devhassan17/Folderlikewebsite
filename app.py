from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
from config import Config
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

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        file = request.files['file']
        media_type = request.form.get('media_type')
        
        if file and media_type in ['images', 'audio', 'videos']:
            filename = secure_filename(file.filename)
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
            
            # Add to database
            add_media(filename, static_path, media_type)
            flash('File uploaded successfully!', 'success')
    
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True)