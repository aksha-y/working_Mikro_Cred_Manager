#!/usr/bin/env python3
"""
Database initialization script for MikroTik Credential Manager (SQLite version)
"""

import sqlite3
import hashlib
import secrets
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_PATH = os.getenv('DB_PATH', 'mikrotik_cred_manager.db')

def create_database():
    """Create the database file if it doesn't exist"""
    try:
        # SQLite creates the database file automatically when we connect
        connection = sqlite3.connect(DB_PATH)
        connection.close()
        print(f"✓ Database '{DB_PATH}' created or already exists")
        return True
    except Exception as e:
        print(f"✗ Error creating database: {e}")
        return False

def create_tables():
    """Create all required tables"""
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'read_only' CHECK(role IN ('admin', 'full_access', 'write_access', 'read_only')),
                allowed_duration_minutes INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP NULL
            )
        """)
        print("✓ Users table created")
        
        # Create indexes for users table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_role ON users(role)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_active ON users(is_active)")
        
        # Credential requests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credential_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wan_ip TEXT NOT NULL,
                device_identity TEXT,
                temp_username TEXT NOT NULL,
                temp_password TEXT NOT NULL,
                purpose TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'revoked')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                revoked_at TIMESTAMP NULL,
                revoked_by INTEGER NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (revoked_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("✓ Credential requests table created")
        
        # Create indexes for credential_requests table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON credential_requests(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_wan_ip ON credential_requests(wan_ip)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON credential_requests(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON credential_requests(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON credential_requests(expires_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_temp_username ON credential_requests(temp_username)")
        
        # Activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NULL,
                action TEXT NOT NULL,
                target_ip TEXT NULL,
                target_identity TEXT NULL,
                details TEXT NULL,
                ip_address TEXT NULL,
                user_agent TEXT NULL,
                status TEXT DEFAULT 'success' CHECK(status IN ('success', 'failed', 'error')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("✓ Activity logs table created")
        
        # Create indexes for activity_logs table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user_id ON activity_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_action ON activity_logs(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_target_ip ON activity_logs(target_ip)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_status ON activity_logs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_logs(created_at)")
        
        # System settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT NULL,
                description TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✓ System settings table created")
        
        # Create index for system_settings table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_setting_key ON system_settings(setting_key)")
        
        # MikroTik devices table
        cursor.execute("""
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
        """)
        print("✓ MikroTik devices table created")
        
        # Sessions table
        cursor.execute("""
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
        """)
        print("✓ Sessions table created")
        
        connection.commit()
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"✗ Error creating tables: {e}")
        return False
    
    return True

def create_admin_user():
    """Create default admin user"""
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        # Check if admin user already exists
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if cursor.fetchone():
            print("✓ Admin user already exists")
            cursor.close()
            connection.close()
            return True
        
        # Get admin password from environment or generate one
        admin_password = os.getenv('ADMIN_DEFAULT_PASSWORD', secrets.token_urlsafe(12))
        password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
        
        # Insert admin user
        cursor.execute("""
            INSERT INTO users (username, email, full_name, password_hash, role, allowed_duration_minutes, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            'admin',
            'admin@company.com',
            'System Administrator',
            password_hash,
            'admin',
            180,
            True
        ))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✓ Admin user created successfully")
        print(f"  Username: admin")
        print(f"  Password: {admin_password}")
        print("  ⚠️  Please save this password and change it after first login!")
        
        return True
        
    except Exception as e:
        print(f"✗ Error creating admin user: {e}")
        return False

def insert_default_settings():
    """Insert default system settings"""
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        
        default_settings = [
            ('mikrotik_service_username', 'service_user', 'Default service account username for MikroTik devices'),
            ('mikrotik_service_password', 'service_password123', 'Default service account password for MikroTik devices'),
            ('default_temp_user_prefix', 'temp_', 'Prefix for temporary usernames'),
            ('max_concurrent_sessions', '10', 'Maximum concurrent sessions per user'),
            ('session_cleanup_interval', '300', 'Session cleanup interval in seconds'),
            ('log_retention_days', '90', 'Number of days to retain activity logs'),
            ('enable_email_notifications', 'false', 'Enable email notifications for credential requests'),
            ('system_timezone', 'UTC', 'System timezone'),
        ]
        
        for key, value, description in default_settings:
            cursor.execute("""
                INSERT OR IGNORE INTO system_settings (setting_key, setting_value, description)
                VALUES (?, ?, ?)
            """, (key, value, description))
        
        connection.commit()
        cursor.close()
        connection.close()
        
        print("✓ Default system settings inserted")
        
    except Exception as e:
        print(f"✗ Error inserting default settings: {e}")
        return False
    
    return True

def test_connection():
    """Test database connection"""
    try:
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        connection.close()
        print("✓ Database connection test successful")
        return True
    except Exception as e:
        print(f"✗ Database connection test failed: {e}")
        return False

def main():
    """Main initialization function"""
    print("🚀 Initializing MikroTik Credential Manager Database (SQLite)...")
    print("=" * 60)
    
    # Step 1: Create database
    if not create_database():
        print("❌ Database initialization failed!")
        return False
    
    # Step 2: Test connection
    if not test_connection():
        print("❌ Database connection failed!")
        return False
    
    # Step 3: Create tables
    if not create_tables():
        print("❌ Table creation failed!")
        return False
    
    # Step 4: Create admin user
    if not create_admin_user():
        print("❌ Admin user creation failed!")
        return False
    
    # Step 5: Insert default settings
    if not insert_default_settings():
        print("❌ Default settings insertion failed!")
        return False
    
    print("=" * 60)
    print("✅ Database initialization completed successfully!")
    print(f"\n📋 Database file: {DB_PATH}")
    print("\n📋 Next Steps:")
    print("1. Update the .env file with your configuration")
    print("2. Update MikroTik service account credentials in system settings")
    print("3. Run the application: python run.py")
    print("4. Login with admin credentials and change the password")
    
    return True

if __name__ == "__main__":
    main()