import os

class Config:
    SECRET_KEY = 'your-secret-key-here'
    ADMIN_USERNAME = 'admin'
    ADMIN_PASSWORD = 'singer123'
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp3', 'wav', 'mp4', 'mov'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size