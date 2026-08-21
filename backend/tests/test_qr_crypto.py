from scripts.generate_keys import generate_key_pair

from app.modules.qr.crypto import ECDSASigner


def test_signer_verifies_authentic_payload() -> None:
    private_key, public_key = generate_key_pair()
    signer = ECDSASigner(private_key, public_key)
    signature = signer.sign(b"passport:123")
    assert signer.verify(b"passport:123", signature)
    assert not signer.verify(b"passport:124", signature)
