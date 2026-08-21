"""Compact, signed Digital Product Passport QR tokens."""

import base64
import binascii
import os
import struct
import time
import uuid
from typing import TypedDict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

PREFIX = "dppassport://v1."
SIGNED_LENGTH = 45
TOKEN_LENGTH = 109


class SchemeError(ValueError):
    """Raised when a token does not use the supported DPP URI format."""


class ChecksumError(ValueError):
    """Raised when the transport checksum is corrupt."""


class InvalidSignatureError(ValueError):
    """Raised when authenticity cannot be established."""


class VerifiedQR(TypedDict):
    product_uuid: str
    key_id: str
    timestamp: int
    nonce_hex: str


class QRCrypto:
    """Generate and authenticate fixed-width P-256 QR payloads."""

    @staticmethod
    def generate(
        product_uuid: str,
        private_key: ec.EllipticCurvePrivateKey,
        key_id: str,
    ) -> str:
        """Generate a signed QR token and return its complete DPP URI."""
        if not isinstance(private_key.curve, ec.SECP256R1):
            raise ValueError("QR signing requires an ECDSA P-256 private key")
        try:
            encoded_key_id = key_id.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("key_id must contain ASCII characters only") from exc
        if not encoded_key_id or len(encoded_key_id) > 4 or "\x00" in key_id:
            raise ValueError("key_id must contain between one and four ASCII bytes")

        payload = struct.pack(
            ">B4s16sI16s",
            1,
            encoded_key_id.ljust(4, b"\x00"),
            os.urandom(16),
            int(time.time()),
            uuid.UUID(product_uuid).bytes,
        )
        checksum = struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)
        signed_data = payload + checksum
        der_signature = private_key.sign(signed_data, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = signed_data + signature
        return PREFIX + base64.b85encode(token).decode("ascii")

    @staticmethod
    def verify(
        uri: str,
        public_keys: dict[str, ec.EllipticCurvePublicKey],
    ) -> VerifiedQR:
        """Verify a QR URI and return its authenticated identity fields."""
        if not isinstance(uri, str) or not uri.startswith(PREFIX):
            raise SchemeError("Unsupported QR URI scheme or version")
        try:
            token = base64.b85decode(uri[len(PREFIX) :])
        except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
            raise SchemeError("QR payload is not valid Base85") from exc
        if len(token) != TOKEN_LENGTH:
            raise SchemeError("QR payload must be exactly 109 bytes")

        payload, expected_checksum = token[:41], token[41:45]
        actual_checksum = struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)
        # Payload corruption is indistinguishable from signature tampering, while
        # an isolated checksum change is reported as a transport checksum failure.
        if expected_checksum != actual_checksum:
            try:
                repaired_token = payload + actual_checksum + token[45:]
                QRCrypto._verify_signature(repaired_token, public_keys)
            except InvalidSignatureError as exc:
                raise InvalidSignatureError("QR payload signature is invalid") from exc
            raise ChecksumError("QR payload checksum does not match")
        QRCrypto._verify_signature(token, public_keys)

        version, raw_key_id, nonce, timestamp, raw_uuid = struct.unpack(">B4s16sI16s", payload)
        if version != 1:
            raise SchemeError("Unsupported QR payload version")
        try:
            key_id = raw_key_id.rstrip(b"\x00").decode("ascii")
        except UnicodeDecodeError as exc:
            raise InvalidSignatureError("QR key identifier is invalid") from exc
        return {
            "product_uuid": str(uuid.UUID(bytes=raw_uuid)),
            "key_id": key_id,
            "timestamp": timestamp,
            "nonce_hex": nonce.hex(),
        }

    @staticmethod
    def _verify_signature(
        token: bytes, public_keys: dict[str, ec.EllipticCurvePublicKey]
    ) -> None:
        """Verify the fixed-width signature against the embedded key identifier."""
        try:
            key_id = token[1:5].rstrip(b"\x00").decode("ascii")
            public_key = public_keys[key_id]
            r = int.from_bytes(token[45:77], "big")
            s = int.from_bytes(token[77:109], "big")
            public_key.verify(
                encode_dss_signature(r, s), token[:SIGNED_LENGTH], ec.ECDSA(hashes.SHA256())
            )
        except (KeyError, UnicodeDecodeError, ValueError, InvalidSignature) as exc:
            raise InvalidSignatureError("QR payload signature is invalid") from exc
