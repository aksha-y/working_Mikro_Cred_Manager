"""
MikroTik RouterOS API integration module
"""

import socket
import hashlib
import binascii
import time
import secrets
import string
from typing import Dict, List, Optional, Tuple
import logging
import ssl

logger = logging.getLogger(__name__)

class MikroTikAPIError(Exception):
    """Custom exception for MikroTik API errors"""
    pass

class MikroTikAPI:
    """MikroTik RouterOS API client"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 8728, timeout: int = 10, use_tls: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.use_tls = use_tls
        self.socket = None
        self.connected = False
        
    def connect(self) -> bool:
        """Connect to MikroTik device (supports TLS when enabled)"""
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.settimeout(self.timeout)

            # Only enable TLS if explicitly set; default is plain API
            if self.use_tls:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.socket = context.wrap_socket(raw_sock, server_hostname=self.host)
            else:
                self.socket = raw_sock

            self.socket.connect((self.host, self.port))
            
            # Login
            if self._login():
                self.connected = True
                logger.info(f"Successfully connected to MikroTik {self.host}:{self.port} (tls={self.use_tls})")
                return True
            else:
                self.disconnect()
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to MikroTik {self.host}:{self.port} (tls={self.use_tls}): {e}")
            self.disconnect()
            return False
    
    def disconnect(self):
        """Disconnect from MikroTik device"""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        self.connected = False
    
    def _send_length(self, length: int):
        """Send length of the message"""
        if length < 0x80:
            self.socket.send(bytes([length]))
        elif length < 0x4000:
            length |= 0x8000
            self.socket.send(bytes([(length >> 8) & 0xFF, length & 0xFF]))
        elif length < 0x200000:
            length |= 0xC00000
            self.socket.send(bytes([(length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))
        elif length < 0x10000000:
            length |= 0xE0000000
            self.socket.send(bytes([(length >> 24) & 0xFF, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))
        else:
            self.socket.send(bytes([0xF0, (length >> 24) & 0xFF, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF]))
    
    def _send_word(self, word: str):
        """Send a word (command or parameter)"""
        word_bytes = word.encode('utf-8')
        self._send_length(len(word_bytes))
        self.socket.send(word_bytes)
    
    def _read_length(self) -> int:
        """Read length of incoming message"""
        first_byte = self.socket.recv(1)[0]
        
        if first_byte < 0x80:
            return first_byte
        elif first_byte < 0xC0:
            return ((first_byte & 0x7F) << 8) + self.socket.recv(1)[0]
        elif first_byte < 0xE0:
            return ((first_byte & 0x1F) << 16) + (self.socket.recv(1)[0] << 8) + self.socket.recv(1)[0]
        elif first_byte < 0xF0:
            return ((first_byte & 0x0F) << 24) + (self.socket.recv(1)[0] << 16) + (self.socket.recv(1)[0] << 8) + self.socket.recv(1)[0]
        else:
            return (self.socket.recv(1)[0] << 24) + (self.socket.recv(1)[0] << 16) + (self.socket.recv(1)[0] << 8) + self.socket.recv(1)[0]
    
    def _read_word(self) -> str:
        """Read a word from the socket"""
        length = self._read_length()
        if length == 0:
            return ""
        return self.socket.recv(length).decode('utf-8')
    
    def _send_command(self, command: str, arguments: Dict[str, str] = None) -> List[Dict[str, str]]:
        """Send command to MikroTik and return response"""
        if not self.connected:
            raise MikroTikAPIError("Not connected to MikroTik device")
        
        try:
            # Send command
            self._send_word(command)
            
            # Send arguments
            if arguments:
                for key, value in arguments.items():
                    self._send_word(f"={key}={value}")
            
            # Send empty word to end command
            self._send_word("")
            
            # Read response with proper sentence handling
            response: List[Dict[str, str]] = []
            next_control: Optional[str] = None
            while True:
                # Support a pushed-back control token from inner loop
                if next_control is not None:
                    word = next_control
                    next_control = None
                else:
                    word = self._read_word()
                
                if not word:
                    break
                
                if word == "!re" or word.startswith("!re"):
                    # Data sentence
                    data: Dict[str, str] = {}
                    while True:
                        attr = self._read_word()
                        if not attr:
                            # End of sentence
                            break
                        if attr.startswith("="):
                            key, _, value = attr[1:].partition("=")
                            data[key] = value
                        elif attr.startswith("!"):
                            # Next control token belongs to outer loop
                            next_control = attr
                            break
                    response.append(data)
                elif word.startswith("!done"):
                    break
                elif word.startswith("!trap") or word.startswith("!fatal"):
                    # Error occurred
                    error_msg = "Unknown error"
                    while True:
                        attr = self._read_word()
                        if not attr or attr.startswith("!"):
                            break
                        if attr.startswith("=message="):
                            error_msg = attr[9:]
                    raise MikroTikAPIError(f"Command failed: {error_msg}")
                else:
                    # Ignore unknown tokens
                    pass
            
            return response
            
        except Exception as e:
            logger.error(f"Command failed: {e}")
            raise MikroTikAPIError(f"Command execution failed: {e}")
    
    def _login(self) -> bool:
        """Perform login to MikroTik device"""
        try:
            # Send login command
            self._send_word("/login")
            self._send_word(f"=name={self.username}")
            self._send_word(f"=password={self.password}")
            self._send_word("")
            
            # Read response
            response = self._read_word()
            if response == "!done":
                return True
            elif response == "!trap":
                # Read error message
                while True:
                    word = self._read_word()
                    if not word:
                        break
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def test_connection(self) -> Dict[str, any]:
        """Test connection to MikroTik device"""
        try:
            if not self.connect():
                return {"success": False, "error": "Connection failed"}
            
            # Get system identity
            try:
                identity_response = self._send_command("/system/identity/print")
                device_name = identity_response[0].get("name", "Unknown") if identity_response else "Unknown"
            except:
                device_name = "Unknown"
            
            # Get user count
            try:
                users_response = self._send_command("/user/print")
                total_users = len(users_response)
                
                # Count temporary users
                temp_users = sum(1 for user in users_response if user.get("name", "").startswith("temp_"))
            except:
                total_users = 0
                temp_users = 0
            
            self.disconnect()
            
            return {
                "success": True,
                "device_name": device_name,
                "total_users": total_users,
                "temporary_users": temp_users
            }
            
        except Exception as e:
            self.disconnect()
            return {"success": False, "error": str(e)}
    
    def create_temporary_user(self, username: str, password: str, duration_minutes: int) -> Dict[str, any]:
        """Create temporary user with automatic cleanup"""
        try:
            if not self.connect():
                return {"success": False, "error": "Connection failed"}
            
            # Create user
            user_args = {
                "name": username,
                "password": password,
                "group": "read",  # Limited permissions
                "comment": f"Temporary user - expires in {duration_minutes} minutes"
            }
            
            try:
                self._send_command("/user/add", user_args)
                logger.info(f"Created temporary user {username} on {self.host}")
            except MikroTikAPIError as e:
                self.disconnect()
                return {"success": False, "error": f"Failed to create user: {e}"}
            
            # Create scheduler to remove user
            scheduler_name = f"cleanup_{username}"
            cleanup_time = f"00:00:{duration_minutes:02d}"  # Format as HH:MM:SS
            
            scheduler_args = {
                "name": scheduler_name,
                "start-time": "startup",
                "interval": cleanup_time,
                "on-event": f"/user/remove [find name=\"{username}\"] ; /system/scheduler/remove [find name=\"{scheduler_name}\"]",
                "comment": f"Auto-cleanup for temporary user {username}"
            }
            
            try:
                self._send_command("/system/scheduler/add", scheduler_args)
                logger.info(f"Created cleanup scheduler {scheduler_name} on {self.host}")
            except MikroTikAPIError as e:
                # If scheduler creation fails, remove the user
                try:
                    self._send_command("/user/remove", {"numbers": username})
                except:
                    pass
                self.disconnect()
                return {"success": False, "error": f"Failed to create cleanup scheduler: {e}"}
            
            self.disconnect()
            
            return {
                "success": True,
                "username": username,
                "password": password,
                "duration_minutes": duration_minutes,
                "scheduler_name": scheduler_name
            }
            
        except Exception as e:
            self.disconnect()
            logger.error(f"Failed to create temporary user: {e}")
            return {"success": False, "error": str(e)}
    
    def revoke_temporary_user(self, username: str) -> Dict[str, any]:
        """Manually revoke temporary user"""
        try:
            if not self.connect():
                return {"success": False, "error": "Connection failed"}
            
            # Remove user
            try:
                users_response = self._send_command("/user/print", {"name": username})
                if not users_response:
                    self.disconnect()
                    return {"success": False, "error": "User not found"}
                
                self._send_command("/user/remove", {"numbers": username})
                logger.info(f"Removed temporary user {username} from {self.host}")
            except MikroTikAPIError as e:
                self.disconnect()
                return {"success": False, "error": f"Failed to remove user: {e}"}
            
            # Remove associated scheduler
            scheduler_name = f"cleanup_{username}"
            try:
                schedulers_response = self._send_command("/system/scheduler/print", {"name": scheduler_name})
                if schedulers_response:
                    self._send_command("/system/scheduler/remove", {"numbers": scheduler_name})
                    logger.info(f"Removed cleanup scheduler {scheduler_name} from {self.host}")
            except MikroTikAPIError:
                # Scheduler removal is not critical
                pass
            
            self.disconnect()
            
            return {"success": True, "message": f"User {username} revoked successfully"}
            
        except Exception as e:
            self.disconnect()
            logger.error(f"Failed to revoke temporary user: {e}")
            return {"success": False, "error": str(e)}
    
    def list_temporary_users(self) -> Dict[str, any]:
        """List all temporary users"""
        try:
            if not self.connect():
                return {"success": False, "error": "Connection failed"}
            
            # Get all users
            users_response = self._send_command("/user/print")
            
            # Filter temporary users
            temp_users = []
            for user in users_response:
                username = user.get("name", "")
                if username.startswith("temp_"):
                    temp_users.append({
                        "username": username,
                        "group": user.get("group", ""),
                        "comment": user.get("comment", ""),
                        "last_logged_in": user.get("last-logged-in", "never")
                    })
            
            self.disconnect()
            
            return {
                "success": True,
                "temporary_users": temp_users,
                "count": len(temp_users)
            }
            
        except Exception as e:
            self.disconnect()
            logger.error(f"Failed to list temporary users: {e}")
            return {"success": False, "error": str(e)}

def generate_temp_credentials(prefix: str = "temp_") -> Tuple[str, str]:
    """Generate temporary username and password"""
    # Generate username with timestamp
    timestamp = str(int(time.time()))[-6:]  # Last 6 digits of timestamp
    username = f"{prefix}{timestamp}"
    
    # Generate secure random password
    alphabet = string.ascii_letters + string.digits
    password = ''.join(secrets.choice(alphabet) for _ in range(12))
    
    return username, password

def test_mikrotik_connection(host: str, username: str, password: str, port: int = 8728) -> Dict[str, any]:
    """Test connection to MikroTik device"""
    api = MikroTikAPI(host, username, password, port)
    return api.test_connection()

def create_temp_user_on_device(host: str, service_user: str, service_pass: str, 
                              temp_username: str, temp_password: str, 
                              duration_minutes: int, port: int = 8728) -> Dict[str, any]:
    """Create temporary user on MikroTik device"""
    api = MikroTikAPI(host, service_user, service_pass, port)
    return api.create_temporary_user(temp_username, temp_password, duration_minutes)

def revoke_temp_user_on_device(host: str, service_user: str, service_pass: str, 
                              temp_username: str, port: int = 8728) -> Dict[str, any]:
    """Revoke temporary user on MikroTik device"""
    api = MikroTikAPI(host, service_user, service_pass, port)
    return api.revoke_temporary_user(temp_username)