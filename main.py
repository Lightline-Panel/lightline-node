#!/usr/bin/env python3
"""Lightline Node — Main entry point.

Follows Marzban-node pattern:
  - Auto-generates SSL cert/key on first run
  - Uses mTLS with panel's client certificate for authentication
  - No token-based auth — certificate IS the authentication
  - REST API for panel to manage shadowsocks-rust on this node
"""

import os
import sys
import logging
import uvicorn

from config import (
    SERVICE_HOST, SERVICE_PORT, SS_PORT,
    SSL_CERT_FILE, SSL_KEY_FILE, SSL_CLIENT_CERT_FILE, DEBUG
)
from certificate import generate_certificate

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('lightline-node')


def main():
    # Auto-generate node SSL cert/key if missing
    if not all((os.path.isfile(SSL_CERT_FILE), os.path.isfile(SSL_KEY_FILE))):
        logger.info("Generating self-signed TLS certificate...")
        generate_certificate(SSL_CERT_FILE, SSL_KEY_FILE)

    if not SSL_CLIENT_CERT_FILE:
        logger.warning(
            "Running without SSL_CLIENT_CERT_FILE — anyone can connect to this node! "
            "Set SSL_CLIENT_CERT_FILE to the panel's certificate for secure mTLS.")

    if SSL_CLIENT_CERT_FILE and not os.path.isfile(SSL_CLIENT_CERT_FILE):
        logger.error(
            f"Client certificate file not found: {SSL_CLIENT_CERT_FILE}\n"
            "Copy the panel's certificate to this path, or remove SSL_CLIENT_CERT_FILE to disable mTLS.")
        sys.exit(1)

    logger.info(f"Lightline Node starting on {SERVICE_HOST}:{SERVICE_PORT}")
    logger.info(f"Shadowsocks port: {SS_PORT}")

    kwargs = {
        "host": SERVICE_HOST,
        "port": SERVICE_PORT,
        "log_level": "debug" if DEBUG else "info",
        "ssl_keyfile": SSL_KEY_FILE,
        "ssl_certfile": SSL_CERT_FILE,
    }

    # If client cert is provided, enable mTLS (verify panel's identity)
    if SSL_CLIENT_CERT_FILE:
        kwargs["ssl_ca_certs"] = SSL_CLIENT_CERT_FILE
        kwargs["ssl_cert_reqs"] = 2  # ssl.CERT_REQUIRED
        logger.info("mTLS enabled — only the panel with matching certificate can connect")
    else:
        logger.info("mTLS disabled — any HTTPS client can connect")

    uvicorn.run("service:app", **kwargs)


if __name__ == "__main__":
    main()
