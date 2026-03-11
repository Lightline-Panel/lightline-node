#!/usr/bin/env python3
"""Lightline Node — Main entry point."""

import os
import sys
import logging
import uvicorn

from config import NODE_PORT, NODE_HOST, NODE_TOKEN, OUTLINE_API_URL, SSL_CERT_FILE, SSL_KEY_FILE
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

    if not OUTLINE_API_URL:
        logger.error("OUTLINE_API_URL is required. Set it in .env")
        sys.exit(1)

    # Generate self-signed cert if not present
    if not (os.path.isfile(SSL_CERT_FILE) and os.path.isfile(SSL_KEY_FILE)):
        logger.info("Generating self-signed TLS certificate...")
        generate_certificate(SSL_CERT_FILE, SSL_KEY_FILE)

    logger.info(f"Lightline Node starting on {NODE_HOST}:{NODE_PORT}")
    logger.info(f"Outline API: {OUTLINE_API_URL}")

    uvicorn.run(
        "service:app",
        host=NODE_HOST,
        port=NODE_PORT,
        ssl_keyfile=SSL_KEY_FILE,
        ssl_certfile=SSL_CERT_FILE,
        log_level="info",
    )


if __name__ == "__main__":
    main()
