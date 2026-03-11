"""Lightline Node — Configuration.

Follows Marzban-node pattern:
  - Node auto-generates SSL cert/key on first run
  - Panel's client certificate (SSL_CLIENT_CERT_FILE) used for mTLS verification
  - REST API on SERVICE_PORT (default 62050)
  - Shadowsocks on SS_PORT (default 8388)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

SERVICE_HOST = os.environ.get('SERVICE_HOST', '0.0.0.0')
SERVICE_PORT = int(os.environ.get('SERVICE_PORT', '62050'))

SS_PORT = int(os.environ.get('SS_PORT', '8388'))

SSL_CERT_FILE = os.environ.get('SSL_CERT_FILE', '/var/lib/lightline-node/ssl_cert.pem')
SSL_KEY_FILE = os.environ.get('SSL_KEY_FILE', '/var/lib/lightline-node/ssl_key.pem')
SSL_CLIENT_CERT_FILE = os.environ.get('SSL_CLIENT_CERT_FILE', '')

DEBUG = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')
