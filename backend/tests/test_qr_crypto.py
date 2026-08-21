import base64
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.modules.qr.crypto import (
    ChecksumError,
    InvalidSignatureError,
    QRCrypto,
    SchemeError,
)


@pytest.fixture
def key_pair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def mutate(uri: str, offset: int) -> str:
    token = bytearray(base64.b85decode(uri.removeprefix("dppassport://v1.")))
    token[offset] ^= 1
    return "dppassport://v1." + base64.b85encode(token).decode("ascii")


def test_generate_returns_valid_uri_scheme(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    result = QRCrypto.generate(str(uuid.uuid4()), key_pair[0], "keyA")
    assert result.startswith("dppassport://v1.")
    assert len(base64.b85decode(result.removeprefix("dppassport://v1."))) == 109


def test_verify_valid_qr_returns_product_uuid(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    product_id = uuid.uuid4()
    result = QRCrypto.verify(QRCrypto.generate(str(product_id), key_pair[0], "keyA"), {"keyA": key_pair[1]})
    assert result["product_uuid"] == str(product_id)


def test_verify_tampered_payload_raises(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    uri = QRCrypto.generate(str(uuid.uuid4()), key_pair[0], "keyA")
    with pytest.raises(InvalidSignatureError):
        QRCrypto.verify(mutate(uri, 10), {"keyA": key_pair[1]})


def test_verify_tampered_signature_raises(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    uri = QRCrypto.generate(str(uuid.uuid4()), key_pair[0], "keyA")
    with pytest.raises(InvalidSignatureError):
        QRCrypto.verify(mutate(uri, 70), {"keyA": key_pair[1]})


@pytest.mark.parametrize("uri", ["https://evil.com/fake", "zxing://fake"])
def test_wrong_uri_scheme_raises(uri: str, key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    with pytest.raises(SchemeError):
        QRCrypto.verify(uri, {"keyA": key_pair[1]})


def test_checksum_corruption_detected(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    uri = QRCrypto.generate(str(uuid.uuid4()), key_pair[0], "keyA")
    with pytest.raises(ChecksumError):
        QRCrypto.verify(mutate(uri, 42), {"keyA": key_pair[1]})


def test_different_key_id_raises(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    uri = QRCrypto.generate(str(uuid.uuid4()), key_pair[0], "keyA")
    with pytest.raises(InvalidSignatureError):
        QRCrypto.verify(uri, {"keyB": other.public_key()})


def test_encode_decode_roundtrip_preserves_uuid(key_pair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    for _ in range(50):
        product_id = uuid.uuid4()
        uri = QRCrypto.generate(str(product_id), key_pair[0], "keyA")
        assert QRCrypto.verify(uri, {"keyA": key_pair[1]})["product_uuid"] == str(product_id)
