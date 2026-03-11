"""Lightline Node — Self-signed certificate generation."""

import logging
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def generate_certificate(cert_file: str, key_file: str):
    """Generate a self-signed TLS certificate and private key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'lightline-node'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Lightline'),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )

    Path(cert_file).parent.mkdir(parents=True, exist_ok=True)
    Path(key_file).parent.mkdir(parents=True, exist_ok=True)

    with open(key_file, 'wb') as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    with open(cert_file, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    logger.info(f"Generated self-signed certificate: {cert_file}")
    return cert_file, key_file
