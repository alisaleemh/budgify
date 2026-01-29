import base64

from transaction_tracker import web


def test_password_encode_decode_roundtrip():
    key = "Altaf Hussain"
    password = "s3cr3t-pass"
    encoded = web._encode_password(password, key)
    assert encoded.startswith("enc:")
    decoded = web._decode_password(encoded, key)
    assert decoded == password


def test_extract_auth_password_basic():
    creds = base64.b64encode(b"user:pass123").decode("utf-8")
    header = f"Basic {creds}"
    assert web._extract_auth_password(header) == "pass123"


def test_extract_auth_password_bearer():
    assert web._extract_auth_password("Bearer token-value") == "token-value"


def test_extract_auth_password_invalid():
    assert web._extract_auth_password("Basic not-base64!!") is None
    assert web._extract_auth_password("Something else") is None
