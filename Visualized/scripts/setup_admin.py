import sqlite3
import hashlib
import secrets
import os
import sys
from pathlib import Path

# Calculate DB path relative to this script
# Visualized/scripts/setup_admin.py -> Visualized/cache/hotsearch.db
SCRIPT_DIR = Path(__file__).parent
VISUALIZED_DIR = SCRIPT_DIR.parent
CACHE_DIR = VISUALIZED_DIR / "cache"
HOTSEARCH_DB_PATH = CACHE_DIR / "hotsearch.db"

def get_password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def setup_admin():
    print(f"Target DB: {HOTSEARCH_DB_PATH}")
    
    if not HOTSEARCH_DB_PATH.exists():
        print("Database not found! Please run the application first to initialize the database.")
        return

    conn = sqlite3.connect(HOTSEARCH_DB_PATH)
    cur = conn.cursor()
    
    # Check if users table exists
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cur.fetchone():
            print("Users table not found! Please run the application first to initialize the database.")
            conn.close()
            return
            
        # Check if salt column exists
        cur.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cur.fetchall()]
        if 'salt' not in columns:
            print("Adding missing 'salt' column to users table...")
            cur.execute("ALTER TABLE users ADD COLUMN salt TEXT DEFAULT ''")
            
    except Exception as e:
        print(f"Error checking table: {e}")
        conn.close()
        return

    # 1. Create/Update root user
    username = 'root'
    password = '123456'
    
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    existing = cur.fetchone()
    
    if existing:
        user_id = existing[0]
        print(f"User '{username}' exists. Updating password...")
        # Use new salt for security
        new_salt = secrets.token_hex(16)
        pwd_hash = get_password_hash(password, new_salt)
        
        cur.execute("UPDATE users SET password_hash = ?, salt = ?, role = 'admin' WHERE id = ?", (pwd_hash, new_salt, user_id))
        print(f"Updated user '{username}' (ID: {user_id})")
    else:
        print(f"User '{username}' not found. Creating...")
        salt = secrets.token_hex(16)
        pwd_hash = get_password_hash(password, salt)
        cur.execute("INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)", (username, pwd_hash, salt, 'admin'))
        print(f"Created user '{username}'")
        
    conn.commit()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    setup_admin()
