import sqlite3
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
    conn.commit()
    conn.close()

def add_media(filename, filepath, media_type):
    conn = get_db_connection()
    conn.execute('INSERT INTO media (filename, filepath, media_type) VALUES (?, ?, ?)',
                 (filename, filepath, media_type))
    conn.commit()
    conn.close()

def get_media_by_type(media_type):
    conn = get_db_connection()
    media = conn.execute('SELECT * FROM media WHERE media_type = ?', (media_type,)).fetchall()
    conn.close()
    return media

def get_all_media():
    conn = get_db_connection()
    media = conn.execute('SELECT * FROM media').fetchall()
    conn.close()
    return media

def delete_media(media_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM media WHERE id = ?', (media_id,))
    conn.commit()
    conn.close()