#!/usr/bin/env python3
"""Generate authenticated, encrypted COLORA QR codes.

The AES key and P-256 private key are created once and persisted.  Back them up:
losing either key makes existing codes unusable.  The AES key must be provisioned
to trusted COLORA scanner builds; it must never be published with an ordinary web
site if confidentiality is required.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import qrcode
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "colora-secure://v1."
VERSION = b"\x01"
NONCE_SIZE = 12
RAW_SIGNATURE_SIZE = 64


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_keys(key_directory: str | Path = "colora_keys") -> tuple[bytes, ec.EllipticCurvePrivateKey]:
    """Load the scanner keys, creating them atomically on first use."""
    directory = Path(key_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    aes_path, signing_path = directory / "aes-256.key", directory / "ecdsa-p256-private.pem"

    if aes_path.exists() != signing_path.exists():
        raise RuntimeError("Incomplete COLORA key set; restore both key files from backup")
    if aes_path.exists():
        aes_key = aes_path.read_bytes()
        private_key = serialization.load_pem_private_key(signing_path.read_bytes(), password=None)
        if len(aes_key) != 32 or not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(private_key.curve, ec.SECP256R1):
            raise ValueError("The stored COLORA keys are not AES-256 and ECDSA P-256 keys")
        return aes_key, private_key

    aes_key = AESGCM.generate_key(bit_length=256)
    private_key = ec.generate_private_key(ec.SECP256R1())
    _exclusive_write(aes_path, aes_key)
    _exclusive_write(
        signing_path,
        private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
    )
    return aes_key, private_key


def _exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def scanner_configuration(aes_key: bytes, private_key: ec.EllipticCurvePrivateKey) -> dict[str, object]:
    """Return the values consumed by ``ColoraScanner`` (treat the AES value as secret)."""
    numbers = private_key.public_key().public_numbers()
    return {
        "aesKeyBase64Url": _b64url(aes_key),
        "publicKeyJwk": {
            "kty": "EC", "crv": "P-256", "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")), "ext": True,
        },
    }


def secure_url(url: str, aes_key: bytes, private_key: ec.EllipticCurvePrivateKey) -> str:
    """Encrypt and sign an HTTP(S) URL and return its COLORA URI."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must be an absolute HTTP(S) URL without embedded credentials")
    nonce = os.urandom(NONCE_SIZE)
    encrypted = AESGCM(aes_key).encrypt(nonce, url.encode("utf-8"), PREFIX.encode("ascii"))
    authenticated_payload = VERSION + nonce + encrypted
    der_signature = private_key.sign(authenticated_payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return PREFIX + base64.b85encode(authenticated_payload + raw_signature).decode("ascii")


def url_to_qr(url: str, output: str | Path, key_directory: str | Path = "colora_keys") -> str:
    """Create a level-H QR PNG and return the encoded proprietary URI."""
    aes_key, private_key = generate_keys(key_directory)
    uri = secure_url(url, aes_key, private_key)
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    qr.make_image(fill_color="black", back_color="white").save(output)
    return uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an encrypted and signed COLORA QR code")
    parser.add_argument("url", help="absolute HTTP(S) destination")
    parser.add_argument("-o", "--output", default="colora-secure-qr.png")
    parser.add_argument("--key-directory", default="colora_keys")
    parser.add_argument("--print-scanner-config", action="store_true", help="print scanner key props (sensitive)")
    args = parser.parse_args()
    uri = url_to_qr(args.url, args.output, args.key_directory)
    print(f"Created {args.output}\n{uri}")
    if args.print_scanner_config:
        print(json.dumps(scanner_configuration(*generate_keys(args.key_directory)), indent=2))


if __name__ == "__main__":
    main()
