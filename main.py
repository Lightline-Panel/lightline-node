#!/usr/bin/env python3
"""Lightline Node — Main entry point.

Runs a REST API agent that manages a local shadowsocks-rust/libev server.
No external Outline Server required.
"""

import os
import sys
import logging
import uvicorn

from config import NODE_PORT, NODE_HOST, NODE_TOKEN, SS_PORT, SSL_CERT_FILE, SSL_KEY_FILE
from certificate import generate_certificate

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('lightline-node')


def main():
    if not NODE_TOKEN:
        logger.error("NODE_TOKEN is required. Set it in .env")
        sys.exit(1)

    logger.info(f"Lightline Node starting on {NODE_HOST}:{NODE_PORT}")
    logger.info(f"Shadowsocks port: {SS_PORT}")

    # SSL is optional — disabled by default for easier panel connectivity
    use_ssl = os.environ.get('ENABLE_SSL', '').lower() in ('true', '1', 'yes')
    kwargs = {
        "host": NODE_HOST,
        "port": NODE_PORT,
        "log_level": "info",
    }

    if use_ssl:
        if not (os.path.isfile(SSL_CERT_FILE) and os.path.isfile(SSL_KEY_FILE)):
            logger.info("Generating self-signed TLS certificate...")
            generate_certificate(SSL_CERT_FILE, SSL_KEY_FILE)
        kwargs["ssl_keyfile"] = SSL_KEY_FILE
        kwargs["ssl_certfile"] = SSL_CERT_FILE
        logger.info("SSL enabled")
    else:
        logger.info("SSL disabled (set ENABLE_SSL=true to enable)")

    uvicorn.run("service:app", **kwargs)


if __name__ == "__main__":
    main()
