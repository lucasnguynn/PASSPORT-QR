import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


class ECDSASigner:
    """Sign and verify payloads with ECDSA P-256 and SHA-256."""

    def __init__(self, private_key_b64: str, public_key_b64: str) -> None:
        private = serialization.load_pem_private_key(base64.b64decode(private_key_b64), None)
        public = serialization.load_pem_public_key(base64.b64decode(public_key_b64))
        if not isinstance(private, ec.EllipticCurvePrivateKey) or not isinstance(
            public, ec.EllipticCurvePublicKey
        ):
            raise ValueError("Configured keys must be elliptic-curve keys")
        self._private_key = private
        self._public_key = public

    def sign(self, payload: bytes) -> str:
        """Return a URL-safe base64 signature without padding."""
        signature = self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def verify(self, payload: bytes, signature: str) -> bool:
        """Return whether a URL-safe base64 signature is authentic."""
        try:
            padding = "=" * (-len(signature) % 4)
            decoded = base64.urlsafe_b64decode(signature + padding)
            self._public_key.verify(decoded, payload, ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, ValueError):
            return False
        return True
