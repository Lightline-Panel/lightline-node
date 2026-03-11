"""Lightline Node — Configuration."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

NODE_PORT = int(os.environ.get('NODE_PORT', '9090'))
NODE_HOST = os.environ.get('NODE_HOST', '0.0.0.0')
NODE_TOKEN = os.environ.get('NODE_TOKEN', '')

OUTLINE_API_URL = os.environ.get('OUTLINE_API_URL', '')
OUTLINE_API_KEY = os.environ.get('OUTLINE_API_KEY', '')

SSL_CERT_FILE = os.environ.get('SSL_CERT_FILE', '/var/lib/lightline-node/cert.pem')
SSL_KEY_FILE = os.environ.get('SSL_KEY_FILE', '/var/lib/lightline-node/key.pem')
