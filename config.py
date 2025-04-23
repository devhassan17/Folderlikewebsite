import os

# STATIC_FOLDER = 'static' # Remove or comment out from here

class Config:
    # --- Core Settings ---
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-should-be-changed') # Use environment variable or change this
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password') # Change this!

    # --- File Paths ---
    STATIC_FOLDER = 'static' # Define INSIDE the class
    UPLOAD_FOLDER = 'uploads' # Keep this for consistency, even if less used?

    # --- Upload Restrictions ---
    # General allowed set (maybe remove if using specific types below?)
    # ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp3', 'wav', 'mp4', 'mov'}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB limit

    # Media type configurations
    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
    ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg'}
    ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'}

    # --- NFC Access Control ---
    VALID_NFC_TAGS = {'YOUR_NFC_TAG_ID_1', 'YOUR_NFC_TAG_ID_2'}
    UNLOCK_SESSION_TIMEOUT_MINUTES = 10 # How long access remains valid after scan (in minutes)
    # --- End NFC Access Control ---

# Helper function to get allowed extensions for a type
def get_allowed_extensions(media_type):
    if media_type == 'images':
        return Config.ALLOWED_IMAGE_EXTENSIONS
    elif media_type == 'audio':
        return Config.ALLOWED_AUDIO_EXTENSIONS
    elif media_type == 'videos':
        return Config.ALLOWED_VIDEO_EXTENSIONS
    elif media_type == 'documents':
        return Config.ALLOWED_DOCUMENT_EXTENSIONS
    else:
        return set()