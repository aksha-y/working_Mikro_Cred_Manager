import sqlite3
import os
from dotenv import load_dotenv
import logging
from typing import List, Dict, Any, Optional

load_dotenv()

# Database configuration
DB_PATH = os.getenv('DB_PATH', 'mikrotik_cred_manager.db')

class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row  # This makes rows behave like dictionaries
            self.cursor = self.connection.cursor()
            logging.info("Database connection established successfully")
            return True
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            return False
    
    def disconnect(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            logging.info("Database connection closed")
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a query and return results"""
        try:
            if not self.connection:
                self.connect()
            
            if params:
                self.cursor.execute(query, params)
            else:
                self.cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                rows = self.cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                self.connection.commit()
                return self.cursor.rowcount
        except Exception as e:
            logging.error(f"Database query error: {e}")
            if self.connection:
                self.connection.rollback()
            raise e
    
    def create_tables(self):
        """Create all necessary tables"""
        tables = {
            'users': """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT DEFAULT 'read_only' CHECK(role IN ('admin', 'full_access', 'read_only', 'write_access')),
                    allowed_duration_minutes INTEGER DEFAULT 30,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'mikrotik_devices': """
                CREATE TABLE IF NOT EXISTS mikrotik_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wan_ip TEXT UNIQUE NOT NULL,
                    device_name TEXT,
                    location TEXT,
                    notes TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'credential_requests': """
                CREATE TABLE IF NOT EXISTS credential_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    wan_ip TEXT NOT NULL,
                    device_identity TEXT,
                    purpose TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    temp_username TEXT NOT NULL,
                    temp_password TEXT NOT NULL,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'revoked')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    revoked_at TIMESTAMP NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """,
            'activity_logs': """
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    target_ip TEXT,
                    target_identity TEXT,
                    details TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    status TEXT DEFAULT 'success' CHECK(status IN ('success', 'failed', 'error')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """,
            'sessions': """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """
        }
        
        try:
            for table_name, query in tables.items():
                self.execute_query(query)
                logging.info(f"Table '{table_name}' created/verified successfully")
            
            # Create default admin user if not exists
            self.create_default_admin()
            
        except Exception as e:
            logging.error(f"Error creating tables: {e}")
            raise e
    
    def create_default_admin(self):
        """Create default admin user with a random password printed to logs once."""
        from auth import hash_password
        import secrets
        
        check_admin = "SELECT id FROM users WHERE username = 'admin'"
        result = self.execute_query(check_admin)
        
        if not result:
            # Use fixed password from env for local setups if provided; otherwise generate random
            local_pw = os.getenv("ADMIN_DEFAULT_PASSWORD")
            raw_password = local_pw if local_pw else secrets.token_urlsafe(12)
            password_hash = hash_password(raw_password)
            insert_admin = """
                INSERT INTO users (username, email, password_hash, full_name, role, allowed_duration_minutes, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            self.execute_query(insert_admin, (
                'admin', 
                'admin@example.com', 
                password_hash, 
                'System Administrator', 
                'admin', 
                180,
                True
            ))
            logging.warning("Default admin user created.")
            logging.warning("Admin username: admin")
            logging.warning(f"Admin password: {raw_password}")

# Global database instance
db = DatabaseManager()

def init_database():
    """Initialize database connection and create tables"""
    if db.connect():
        db.create_tables()
        return True
    return False