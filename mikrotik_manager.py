import logging
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import secrets
import string
import socket

# Use our RouterOS API client
from mikrotik_api import MikroTikAPI

load_dotenv()

class MikroTikManager:
    def __init__(self):
        # Read-only from env; don't ship insecure defaults in public repo
        self.service_user = os.getenv('MIKROTIK_SERVICE_USER') or ""
        self.service_pass = os.getenv('MIKROTIK_SERVICE_PASSWORD') or ""
        # API port (default 8728)
        try:
            self.api_port = int(os.getenv('MIKROTIK_API_PORT', '8728'))
        except Exception:
            self.api_port = 8728
        # TLS control: explicit env flag overrides heuristics
        tls_env = (os.getenv('MIKROTIK_API_TLS') or '').strip().lower()
        if tls_env in ('1', 'true', 'yes', 'on'):
            self.use_tls = True
        elif tls_env in ('0', 'false', 'no', 'off'):
            self.use_tls = False
        else:
            # Default heuristic: only 8729 is API-SSL by default; all other ports assume plain API
            self.use_tls = (self.api_port == 8729)
    
    def connect_to_device(self, ip_address: str, username: str = None, password: str = None):
        """Quick TCP connectivity test against configured API port"""
        try:
            # Use service account credentials if not provided (kept for future use)
            if not username:
                username = self.service_user
            if not password:
                password = self.service_pass
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((ip_address, self.api_port))
            sock.close()
            
            if result == 0:
                logging.info(f"TCP port {self.api_port} reachable on {ip_address}")
                return {"connected": True, "ip": ip_address, "port": self.api_port}
            else:
                logging.error(f"Cannot reach API port {self.api_port} on {ip_address}")
                return None
            
        except Exception as e:
            logging.error(f"Failed to connect to MikroTik device at {ip_address}: {e}")
            return None
    
    def test_connection(self, ip_address: str):
        """Test connection and fetch router identity when possible."""
        try:
            # Require API login first to avoid misleading fallback identities
            api_port = self.api_port
            use_tls = self.use_tls
            connection = self.connect_to_device(ip_address)
            if not connection:
                return {"success": False, "error": f"Cannot reach port {api_port}"}

            identity = None
            try:
                api = MikroTikAPI(host=ip_address, username=self.service_user, password=self.service_pass, port=api_port, use_tls=use_tls)
                if api.connect():
                    # Try with proplist first
                    ident_resp = api._send_command("/system/identity/print", {".proplist": "name"})
                    if not (isinstance(ident_resp, list) and ident_resp and (ident_resp[0].get("name") or ident_resp[0].get("identity"))):
                        # Fallback: full response
                        ident_resp = api._send_command("/system/identity/print")
                    if isinstance(ident_resp, list) and ident_resp:
                        identity = ident_resp[0].get("name") or ident_resp[0].get("identity")
                api.disconnect()
            except Exception as e:
                logging.warning(f"Failed to fetch identity from {ip_address}:{api_port}: {e}")

            # Do not fail if identity is missing; consider connection successful but report identity=null
            if not identity:
                return {"success": True, "device_name": None, "identity": None, "message": "Connected, identity not readable"}

            return {"success": True, "device_name": identity, "identity": identity, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_device_info(self, ip_address: str):
        """Fetch live device info including user counts."""
        try:
            # Quick TCP check first
            test = self.test_connection(ip_address)
            if not test.get("success"):
                return {"success": False, "error": test.get("error", "Connection failed")}
            
            use_tls = self.use_tls
            api = MikroTikAPI(host=ip_address, username=self.service_user, password=self.service_pass, port=self.api_port, use_tls=use_tls)
            if not api.connect():
                return {"success": False, "error": "API login failed"}
            
            total_users = 0
            temp_users = 0
            device_name = None
            
            try:
                # Get identity
                try:
                    identity = api._send_command("/system/identity/print", {".proplist": "name"})
                    if not (isinstance(identity, list) and identity and (identity[0].get("name") or identity[0].get("identity"))):
                        identity = api._send_command("/system/identity/print")
                    if identity and isinstance(identity, list):
                        name = identity[0].get("name") or identity[0].get("identity")
                        if name:
                            device_name = name
                except Exception:
                    pass
                
                # Get users
                users = api._send_command("/user/print") or []
                # Exclude disabled and expired users if flags present
                total_users = 0
                for u in users:
                    # RouterOS sends '.id' and other keys; disabled often comes as 'disabled'='true'
                    if u.get('disabled') in ('true', 'yes'):  # skip disabled
                        continue
                    total_users += 1
                # Count temp users primarily by comment marker
                temp_marker = os.getenv("TEMP_USER_COMMENT_MARKER", "Temporary user")
                temp_users = 0
                if isinstance(users, list):
                    for u in users:
                        name = u.get("name", "")
                        comment = u.get("comment", "")
                        if temp_marker.lower() in comment.lower():
                            temp_users += 1
            finally:
                api.disconnect()
            
            # If router returns suspiciously low counts, fall back to DB-known active requests for this IP
            try:
                if total_users <= 1 or temp_users == 0:
                    from database import db as _db
                    # Ensure expired rows are marked before counting
                    _db.execute_query(
                        "UPDATE credential_requests SET status='expired' WHERE status='active' AND expires_at <= datetime('now') AND wan_ip=?",
                        (ip_address,)
                    )
                    rows = _db.execute_query(
                        "SELECT COUNT(*) as cnt FROM credential_requests WHERE wan_ip=? AND status='active'",
                        (ip_address,)
                    ) or [{"cnt": 0}]
                    db_count = rows[0].get("cnt", 0)
                    # Only override temp_users to reflect active temp accounts we created
                    if temp_users == 0 and db_count:
                        temp_users = int(db_count)
            except Exception:
                pass

            # Final sanity: ensure total_users is at least temp_users + service account when possible
            try:
                if total_users == 0 and temp_users > 0:
                    total_users = temp_users + 1
                elif total_users < temp_users:
                    total_users = temp_users + 1
            except Exception:
                pass

            return {
                "success": True,
                "device_name": device_name,
                "total_users": total_users,
                "temporary_users": temp_users
            }
        except Exception as e:
            logging.error(f"Failed to get device info for {ip_address}: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_temp_credentials(self, prefix: str = "temp-"):
        """Generate temporary username and password with a configurable prefix.
        Add a short random suffix to avoid collisions under concurrency.
        """
        timestamp = str(int(datetime.now().timestamp()))
        rand_suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        username = f"{prefix}{timestamp}-{rand_suffix}"
        # Secure random password
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        return username, password

    def map_role_to_group(self, role: str) -> str:
        """Map portal role to MikroTik group."""
        mapping = {
            'admin': 'full',
            'full_access': 'full',
            'write_access': 'write',
            'read_only': 'read'
        }
        return mapping.get(role, 'read')
    
    def create_temporary_user(self, ip_address: str, duration_minutes: int, username_prefix: str = "temp-", group: str = None):
        """Create temporary user on MikroTik device using RouterOS API and schedule cleanup."""
        try:
            # Ensure TCP reachability first
            connection_test = self.test_connection(ip_address)
            if not connection_test.get("success"):
                return {"success": False, "error": f"Cannot connect to device: {connection_test.get('error', 'unreachable')}"}

            # Prepare credentials
            temp_username, temp_password = self.generate_temp_credentials(prefix=username_prefix)
            if not group:
                group = 'read'

            api = MikroTikAPI(host=ip_address, username=self.service_user, password=self.service_pass, port=self.api_port, use_tls=self.use_tls)
            if not api.connect():
                return {"success": False, "error": "API login failed"}

            # 1) Create user with selected group
            try:
                api._send_command("/user/add", {
                    "name": temp_username,
                    "password": temp_password,
                    "group": group,
                    "comment": f"Temporary user - expires in {duration_minutes} minutes"
                })
                logging.info(f"Created temporary user {temp_username} on {ip_address} (group={group})")
            except Exception as e:
                api.disconnect()
                return {"success": False, "error": f"Failed to create user: {e}"}

            # 2) Create one-shot scheduler to remove user
            try:
                scheduler_name = f"cleanup-{temp_username}"
                hh = duration_minutes // 60
                mm = duration_minutes % 60
                interval_str = f"{hh:02d}:{mm:02d}:00"

                cleanup_script = (
                    f":log info \"Cleaning up temporary user: {temp_username}\"; "
                    f"/user remove [find name=\"{temp_username}\"]; "
                    f":log info \"Temporary user {temp_username} removed\"; "
                    f"/system scheduler remove [find name=\"{scheduler_name}\"]; "
                    f":log info \"Cleanup scheduler {scheduler_name} removed\""
                )

                api._send_command("/system/scheduler/add", {
                    "name": scheduler_name,
                    "interval": interval_str,
                    "on-event": cleanup_script,
                    "comment": f"Auto cleanup for {temp_username}"
                })
                logging.info(f"Created cleanup scheduler {scheduler_name} on {ip_address} with interval {interval_str}")
            except Exception as e:
                # Best-effort rollback: remove created user
                try:
                    api._send_command("/user/remove", {"numbers": temp_username})
                except Exception:
                    pass
                api.disconnect()
                return {"success": False, "error": f"Failed to create cleanup scheduler: {e}"}

            # 3) Try to read identity using the newly-created temp credentials (if service credentials couldn't read it)
            device_identity = None
            try:
                if not connection_test.get("identity"):
                    api_temp = MikroTikAPI(host=ip_address, username=temp_username, password=temp_password, port=self.api_port, use_tls=self.use_tls)
                    if api_temp.connect():
                        ident_resp = api_temp._send_command("/system/identity/print", {".proplist": "name"})
                        if not (isinstance(ident_resp, list) and ident_resp and (ident_resp[0].get("name") or ident_resp[0].get("identity"))):
                            ident_resp = api_temp._send_command("/system/identity/print")
                        if isinstance(ident_resp, list) and ident_resp:
                            device_identity = ident_resp[0].get("name") or ident_resp[0].get("identity")
                    api_temp.disconnect()
                else:
                    device_identity = connection_test.get("identity")
            except Exception:
                pass

            api.disconnect()
            return {
                "success": True,
                "username": temp_username,
                "password": temp_password,
                "duration_minutes": duration_minutes,
                "message": "Temporary user created successfully",
                "device_identity": device_identity
            }
        except Exception as e:
            logging.error(f"Failed to create temporary user on {ip_address}: {e}")
            return {"success": False, "error": str(e)}
    
    def revoke_temporary_user(self, ip_address: str, username: str):
        """Revoke temporary user on MikroTik device (remove user and associated scheduler)."""
        try:
            connection_test = self.test_connection(ip_address)
            if not connection_test["success"]:
                return {"success": False, "error": f"Cannot connect to device: {connection_test['error']}"}

            api = MikroTikAPI(host=ip_address, username=self.service_user, password=self.service_pass, port=self.api_port)
            if not api.connect():
                return {"success": False, "error": "API login failed"}

            try:
                # Remove user (by name)
                api._send_command("/user/remove", {"numbers": username})
            except Exception as e:
                # Continue to try removing scheduler even if user missing
                logging.warning(f"While revoking, user remove failed for {username} on {ip_address}: {e}")
            
            try:
                # Remove associated scheduler if exists
                scheduler_name = f"cleanup-{username}"
                api._send_command("/system/scheduler/remove", {"numbers": scheduler_name})
            except Exception:
                pass

            api.disconnect()
            return {"success": True, "message": f"User {username} revoked successfully"}
        except Exception as e:
            logging.error(f"Failed to revoke temporary user {username} on {ip_address}: {e}")
            return {"success": False, "error": str(e)}

    def fetch_identity_debug(self, ip_address: str, username: str = None, password: str = None):
        """Return raw identity responses for debugging.
        Tries with provided creds or service creds; returns raw proplist and full outputs.
        """
        result = {
            "ip": ip_address,
            "port": self.api_port,
            "use_tls": self.use_tls,
            "connect_ok": False,
            "login_ok": False,
            "identity_proplist": None,
            "identity_full": None,
            "parsed": None,
            "error": None,
        }
        try:
            user = username or self.service_user
            pwd = password or self.service_pass
            api = MikroTikAPI(host=ip_address, username=user, password=pwd, port=self.api_port, use_tls=self.use_tls)
            if not api.connect():
                result["error"] = "API login failed"
                return result
            result["connect_ok"] = True
            result["login_ok"] = True
            try:
                proplist_resp = api._send_command("/system/identity/print", {".proplist": "name"})
            except Exception as e:
                proplist_resp = {"error": str(e)}
            try:
                full_resp = api._send_command("/system/identity/print")
            except Exception as e:
                full_resp = {"error": str(e)}
            api.disconnect()
            result["identity_proplist"] = proplist_resp
            result["identity_full"] = full_resp
            # Parse name
            try:
                if isinstance(proplist_resp, list) and proplist_resp:
                    name = proplist_resp[0].get("name") or proplist_resp[0].get("identity")
                elif isinstance(full_resp, list) and full_resp:
                    name = full_resp[0].get("name") or full_resp[0].get("identity")
                else:
                    name = None
                result["parsed"] = name
            except Exception:
                result["parsed"] = None
            return result
        except Exception as e:
            result["error"] = str(e)
            return result