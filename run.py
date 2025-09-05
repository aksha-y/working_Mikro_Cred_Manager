#!/usr/bin/env python3
"""
Startup script for Mikrotik-Manager
"""

import uvicorn
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

def main():
    """Main function to start the application"""

    # Load environment from .env before reading values
    env_path = current_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    # Configuration
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 8000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'

    # Optional TLS
    certfile = os.getenv('SSL_CERTFILE')
    keyfile = os.getenv('SSL_KEYFILE')
    https_port = int(os.getenv('HTTPS_PORT', port))
    use_ssl = bool(certfile and keyfile)

    # Add HSTS and proxy headers when behind a reverse proxy
    os.environ.setdefault('FORWARDED_ALLOW_IPS', '*')  # allow X-Forwarded-* parsing by Uvicorn

    # Startup banner
    print("🚀 Starting Mikrotik-Manager...")
    if use_ssl:
        print(f"🔒 SSL enabled")
        print(f"📍 Server will be available at: https://{host}:{https_port}")
    else:
        print(f"📍 Server will be available at: http://{host}:{port}")
    print(f"🔧 Debug mode: {'Enabled' if debug else 'Disabled'}")
    print("=" * 60)

    # Start the server
    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=https_port if use_ssl else port,
            reload=debug,
            log_level="info" if not debug else "debug",
            access_log=True,
            ssl_certfile=certfile if use_ssl else None,
            ssl_keyfile=keyfile if use_ssl else None,
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
