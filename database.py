import sqlite3
from datetime import datetime, timedelta
from config import Config

def get_db_connection():
    conn = sqlite3.connect('media.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            media_type TEXT NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS unlock_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE, -- The unique session unlock token
            created_at TIMESTAMP NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized (media and unlock_sessions tables).")

def add_media(filename, filepath, media_type):
    conn = get_db_connection()
    conn.execute('INSERT INTO media (filename, filepath, media_type) VALUES (?, ?, ?)',
                 (filename, filepath, media_type))
    conn.commit()
    conn.close()

def get_media_by_type(media_type):
    conn = get_db_connection()
    media = conn.execute('SELECT * FROM media WHERE media_type = ? ORDER BY upload_date DESC', (media_type,)).fetchall()
    conn.close()
    return media

def get_all_media():
    conn = get_db_connection()
    media = conn.execute('SELECT * FROM media ORDER BY upload_date DESC').fetchall()
    conn.close()
    return media

def delete_media(media_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM media WHERE id = ?', (media_id,))
    conn.commit()
    conn.close()

def add_unlock_session(token):
    """Adds a new unlock session token to the database."""
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO unlock_sessions (token, created_at) VALUES (?, ?)',
                     (token, datetime.now()))
        conn.commit()
    except sqlite3.IntegrityError:
        # Handle cases where the token might already exist (very unlikely with secrets.token_hex)
        print(f"Warning: Attempted to insert duplicate unlock token: {token}")
        pass # Or raise an error if this shouldn't happen
    finally:
        conn.close()

def validate_unlock_token(token):
    """Checks if a token exists and is within the valid time window."""
    conn = get_db_connection()
    try:
        result = conn.execute('SELECT created_at FROM unlock_sessions WHERE token = ?', (token,)).fetchone()
        if result:
            created_at = result['created_at']
            
            # Handle SQLite timestamp to datetime conversion
            try:
                # If it's already a datetime object
                if isinstance(created_at, datetime):
                    pass
                # If it's a ISO format string
                elif isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        # Try parsing with explicit format if fromisoformat fails
                        created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    print(f"Warning: Unexpected created_at type: {type(created_at)}")
                    return False
                    
                # Calculate timeout using seconds first (if defined), falling back to minutes
                if hasattr(Config, 'UNLOCK_SESSION_TIMEOUT_SECONDS') and Config.UNLOCK_SESSION_TIMEOUT_SECONDS is not None:
                    valid_until = created_at + timedelta(seconds=Config.UNLOCK_SESSION_TIMEOUT_SECONDS)
                    print(f"Using seconds timeout: {Config.UNLOCK_SESSION_TIMEOUT_SECONDS}s")
                else:
                    valid_until = created_at + timedelta(minutes=Config.UNLOCK_SESSION_TIMEOUT_MINUTES)
                    print(f"Using minutes timeout: {Config.UNLOCK_SESSION_TIMEOUT_MINUTES}m")
                
                now = datetime.now()
                is_valid = now < valid_until
                
                # Print debug info
                time_diff = (now - created_at).total_seconds()
                print(f"Token check: created={created_at}, now={now}, diff={time_diff:.1f}s, valid_until={valid_until}, is_valid={is_valid}")
                
                return is_valid
            except Exception as e:
                print(f"Error validating token timestamp: {e}")
                return False
    finally:
        conn.close()
    return False  # Token not found or expired

def cleanup_expired_tokens():
    """Removes tokens older than the configured timeout."""
    conn = get_db_connection()
    try:
        # Use seconds if defined, otherwise convert minutes to seconds
        if hasattr(Config, 'UNLOCK_SESSION_TIMEOUT_SECONDS') and Config.UNLOCK_SESSION_TIMEOUT_SECONDS is not None:
            timeout_seconds = Config.UNLOCK_SESSION_TIMEOUT_SECONDS
        else:
            timeout_seconds = Config.UNLOCK_SESSION_TIMEOUT_MINUTES * 60
            
        cutoff_time = datetime.now() - timedelta(seconds=timeout_seconds)
        result = conn.execute('DELETE FROM unlock_sessions WHERE created_at < ?', (cutoff_time,))
        deleted_count = result.rowcount
        conn.commit()
        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} expired unlock session(s).")
    finally:
        conn.close()