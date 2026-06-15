"""GitHub 인증 토큰 해결(resolve) 테스트.

검증 범위:
    - App 미설정 → PAT 폴백
    - App 설정 + installation_id → 설치 토큰 발급
    - 캐시 적중(만료 전 재발급 안 함) / 만료 임박 시 재발급
    - App JWT(RS256)가 실제로 서명·검증되는지
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.integrations import github_auth


@pytest.fixture(autouse=True)
def _clear_cache():
    """각 테스트는 깨끗한 토큰 캐시에서 시작한다."""
    github_auth._token_cache.clear()
    yield
    github_auth._token_cache.clear()


@pytest.fixture
def app_mode(monkeypatch):
    """App 모드가 켜진 것처럼 설정값을 주입."""
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "12345")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "dummy")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", "")
    assert settings.github_app_enabled


@pytest.mark.asyncio
async def test_pat_fallback_when_app_disabled(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", "")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", "")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "pat-token")

    # installation_id가 있어도 App이 꺼져 있으면 PAT를 쓴다.
    assert await github_auth.resolve_token(None) == "pat-token"
    assert await github_auth.resolve_token(999) == "pat-token"


@pytest.mark.asyncio
async def test_app_mode_mints_installation_token(app_mode, monkeypatch):
    future = datetime.now(timezone.utc) + timedelta(hours=1)

    async def fake_request(installation_id):
        return f"tok-{installation_id}", future

    monkeypatch.setattr(github_auth, "_request_installation_token", fake_request)

    assert await github_auth.resolve_token(42) == "tok-42"


@pytest.mark.asyncio
async def test_cache_hit_avoids_remint(app_mode, monkeypatch):
    calls = {"n": 0}
    future = datetime.now(timezone.utc) + timedelta(hours=1)

    async def fake_request(installation_id):
        calls["n"] += 1
        return "tok", future

    monkeypatch.setattr(github_auth, "_request_installation_token", fake_request)

    await github_auth.resolve_token(7)
    await github_auth.resolve_token(7)
    assert calls["n"] == 1  # 두 번째는 캐시 적중


@pytest.mark.asyncio
async def test_expiring_token_is_reminted(app_mode, monkeypatch):
    # 만료 30초 전(갱신 여유 60초 안쪽) 토큰을 캐시에 심어둔다 → 재발급되어야 함.
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    github_auth._token_cache[5] = ("stale", soon)

    future = datetime.now(timezone.utc) + timedelta(hours=1)

    async def fake_request(installation_id):
        return "fresh", future

    monkeypatch.setattr(github_auth, "_request_installation_token", fake_request)

    assert await github_auth.resolve_token(5) == "fresh"


def test_build_app_jwt_is_valid_rs256(monkeypatch):
    """생성된 JWT가 공개키로 검증되고 iss/exp가 올바른지."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    monkeypatch.setattr(settings, "GITHUB_APP_ID", "999")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", pem)
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY_PATH", "")

    token = github_auth._build_app_jwt()
    decoded = jwt.decode(token, public_pem, algorithms=["RS256"])
    assert decoded["iss"] == "999"
    assert decoded["exp"] > decoded["iat"]
