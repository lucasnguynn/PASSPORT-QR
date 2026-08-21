"""Generate the DPP ECDSA P-256 signing keys.

Usage: install ``cryptography`` and run ``python scripts/generate_keys.py``.
Copy each emitted value into the matching variable in ``.env``. Keep the
private key secret; only the public key may be distributed to verifiers.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def generate_key_pair() -> tuple[str, str]:
    """Return a base64-encoded PKCS#8 private key and SPKI public key."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return (
        base64.b64encode(private_bytes).decode("ascii"),
        base64.b64encode(public_bytes).decode("ascii"),
    )


def main() -> None:
    """Write environment-ready keys to standard output."""
    private_key, public_key = generate_key_pair()
    print(f"ECDSA_PRIVATE_KEY_B64={private_key}")
    print(f"ECDSA_PUBLIC_KEY_B64={public_key}")
    print("ACTIVE_KEY_ID=key_001")


if __name__ == "__main__":
    main()
