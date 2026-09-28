"""Self-signed HTTPS certificate so Android Chrome allows camera + motion sensors.

Chrome shows a warning the first time: tap "Advanced" -> "Proceed". The private
key never leaves the laptop (laptop/certs is gitignored).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import logging
import socket
from pathlib import Path

log = logging.getLogger(__name__)
HOTSPOT_GATEWAY = "192.168.137.1"  # Windows Mobile Hotspot address of this laptop


def local_ipv4s() -> list[str]:
    ips = {HOTSPOT_GATEWAY, "127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        log.warning("could not list local IPs")
    return sorted(ips)


def ensure_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Return (cert, key) paths, generating them on first use."""
    cert_path, key_path = cert_dir / "cert.pem", cert_dir / "key.pem"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VisionPilot laptop")])
    alt_names = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in local_ipv4s()]
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_dir.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    log.info("Generated self-signed certificate in %s", cert_dir)
    return cert_path, key_path
