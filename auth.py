from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import secrets
import hashlib
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings (do not ship real secrets; require env overrides)
SECRET_KEY = os.getenv("SECRET_KEY", "changeme-in-env")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)

def generate_temp_password(length: int = 12) -> str:
    """Generate a temporary password"""
    import string
    import random
    
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(characters) for _ in range(length))

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

class SessionManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def create_session(self, user_id: int, ip_address: str, user_agent: str) -> str:
        """Create a new session"""
        session_token = generate_session_token()
        # Use UTC for storage; display converts to server local time
        expires_at = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        query = """
            INSERT INTO sessions (user_id, session_token, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """
        
        try:
            self.db.execute_query(query, (user_id, session_token, ip_address, user_agent, expires_at))
            return session_token
        except Exception as e:
            logging.error(f"Error creating session: {e}")
            return None
    
    def validate_session(self, session_token: str) -> dict:
        """Validate session token"""
        query = """
            SELECT 
                s.id AS session_id,
                s.user_id AS user_id,
                u.id AS id,            -- ensure 'id' refers to user id for app logic
                u.username,
                u.email,
                u.role,
                u.full_name,
                u.is_active,
                u.allowed_duration_minutes
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? AND s.is_active = 1 AND s.expires_at > datetime('now')
        """
        
        try:
            result = self.db.execute_query(query, (session_token,))
            if result:
                return result[0]
            return None
        except Exception as e:
            logging.error(f"Error validating session: {e}")
            return None
    
    def invalidate_session(self, session_token: str) -> bool:
        """Invalidate a session"""
        query = "UPDATE sessions SET is_active = 0 WHERE session_token = ?"
        
        try:
            self.db.execute_query(query, (session_token,))
            return True
        except Exception as e:
            logging.error(f"Error invalidating session: {e}")
            return False
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        query = "DELETE FROM sessions WHERE expires_at < datetime('now')"
        
        try:
            self.db.execute_query(query)
            logging.info("Expired sessions cleaned up")
        except Exception as e:
            logging.error(f"Error cleaning up sessions: {e}")

class UserManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def authenticate_user(self, username: str, password: str) -> dict:
        """Authenticate user credentials"""
        query = "SELECT * FROM users WHERE username = ? AND is_active = 1"
        
        try:
            result = self.db.execute_query(query, (username,))
            if result and verify_password(password, result[0]['password_hash']):
                user = result[0]
                # Remove password hash from returned data
                del user['password_hash']
                return user
            return None
        except Exception as e:
            logging.error(f"Error authenticating user: {e}")
            return None
    
    def create_user(self, username: str, email: str, password: str, full_name: str, role: str = 'read_only', allowed_duration_minutes: int = 30) -> bool:
        """Create a new user"""
        password_hash = hash_password(password)
        query = """
            INSERT INTO users (username, email, password_hash, full_name, role, allowed_duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        try:
            self.db.execute_query(query, (username, email, password_hash, full_name, role, allowed_duration_minutes))
            return True
        except Exception as e:
            logging.error(f"Error creating user: {e}")
            return False
    
    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user information"""
        allowed_fields = ['email', 'full_name', 'role', 'is_active', 'allowed_duration_minutes']
        updates = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                values.append(value)
        
        if not updates:
            return False
        
        values.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        
        try:
            self.db.execute_query(query, values)
            return True
        except Exception as e:
            logging.error(f"Error updating user: {e}")
            return False
    
    def change_password(self, user_id: int, new_password: str) -> bool:
        """Change user password"""
        password_hash = hash_password(new_password)
        query = "UPDATE users SET password_hash = ? WHERE id = ?"
        
        try:
            self.db.execute_query(query, (password_hash, user_id))
            return True
        except Exception as e:
            logging.error(f"Error changing password: {e}")
            return False
    
    def get_all_users(self) -> list:
        """Get all users (excluding password hashes)"""
        query = "SELECT id, username, email, full_name, role, is_active, allowed_duration_minutes, created_at FROM users ORDER BY created_at DESC"
        
        try:
            return self.db.execute_query(query)
        except Exception as e:
            logging.error(f"Error getting users: {e}")
            return []
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user"""
        query = "DELETE FROM users WHERE id = ?"
        
        try:
            self.db.execute_query(query, (user_id,))
            return True
        except Exception as e:
            logging.error(f"Error deleting user: {e}")
            return False