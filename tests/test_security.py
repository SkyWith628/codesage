"""HMAC 서명 검증 단위 테스트."""

from app.core.security import sign_payload, verify_github_signature

SECRET = "test-secret"


def test_valid_signature_passes():
    body = b'{"hello": "world"}'
    sig = sign_payload(body, SECRET)
    assert verify_github_signature(body, sig, SECRET) is True


def test_tampered_body_fails():
    body = b'{"hello": "world"}'
    sig = sign_payload(body, SECRET)
    tampered = b'{"hello": "evil"}'
    assert verify_github_signature(tampered, sig, SECRET) is False


def test_missing_signature_fails():
    assert verify_github_signature(b"x", None, SECRET) is False


def test_wrong_secret_fails():
    body = b'{"a": 1}'
    sig = sign_payload(body, SECRET)
    assert verify_github_signature(body, sig, "other-secret") is False
