"""
GitHub 인증 토큰 해결(resolve) 모듈.

두 가지 인증 방식을 하나의 함수(resolve_token)로 추상화한다:
    - GitHub App 모드: App 비밀키로 JWT를 만들어 '설치 토큰(installation token)'을
      발급받아 쓴다. 설치된 레포 범위로만 유효한 1시간짜리 단기 토큰.
    - PAT 폴백: App 설정이 없으면 기존 GITHUB_TOKEN(개인 액세스 토큰)을 그대로 쓴다.

왜 설치 토큰인가:
    PAT(Personal Access Token)는 한 계정에 묶인 정적 토큰이라 유출 시 피해가 크고,
    설치된 모든 레포에 광범위한 권한을 갖는다. GitHub App 설치 토큰은
    "이 레포에, 1시간 동안만" 유효해 최소 권한 원칙(least privilege)에 맞는다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
import jwt  # PyJWT (RS256 서명용 cryptography 포함)

from app.core.config import settings

logger = logging.getLogger(__name__)

# installation_id -> (token, expires_at). 프로세스 내 캐시.
# 설치 토큰은 1시간 유효하므로 매 호출마다 발급하면 낭비 + rate limit 위험.
_token_cache: dict[int, tuple[str, datetime]] = {}
# 동시 태스크가 같은 설치에 대해 중복 발급하지 않도록 직렬화.
_mint_lock = asyncio.Lock()

# 만료 직전 갱신 여유(초). 시계 오차/네트워크 지연 대비.
_REFRESH_MARGIN_SECONDS = 60


def _build_app_jwt() -> str:
    """
    App 자체를 인증하는 JWT를 만든다 (RS256, App 비밀키로 서명).

    이 JWT로는 레포 작업을 못 하고, '설치 토큰을 발급받는' 용도로만 쓴다.
    GitHub 규칙상 만료는 최대 10분.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,   # 60초 backdate: 서버 간 시계 오차 허용 (GitHub 권장)
        "exp": now + 600,  # 10분 (GitHub 상한)
        "iss": settings.GITHUB_APP_ID,
    }
    return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


def _parse_expires_at(value: str) -> datetime:
    """GitHub의 ISO8601 만료시각('...Z')을 timezone-aware datetime으로 변환."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_valid(token_exp: tuple[str, datetime]) -> bool:
    """캐시된 토큰이 (여유 시간을 두고) 아직 유효한지."""
    _, expires_at = token_exp
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    return remaining > _REFRESH_MARGIN_SECONDS


async def _request_installation_token(installation_id: int) -> tuple[str, datetime]:
    """GitHub에 설치 토큰 발급을 요청한다."""
    app_jwt = _build_app_jwt()
    url = f"{settings.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["token"], _parse_expires_at(data["expires_at"])


async def _installation_token(installation_id: int) -> str:
    """캐시를 우선 보고, 없거나 만료 임박이면 새로 발급한다."""
    cached = _token_cache.get(installation_id)
    if cached is not None and _is_valid(cached):
        return cached[0]

    # 락 안에서 다시 확인(double-checked): 대기 중 다른 태스크가 이미 발급했을 수 있음.
    async with _mint_lock:
        cached = _token_cache.get(installation_id)
        if cached is not None and _is_valid(cached):
            return cached[0]
        token, expires_at = await _request_installation_token(installation_id)
        _token_cache[installation_id] = (token, expires_at)
        logger.info("설치 토큰 발급: installation=%s (만료 %s)", installation_id, expires_at)
        return token


async def resolve_token(installation_id: int | None) -> str:
    """
    GitHub API 호출에 쓸 Bearer 토큰을 돌려준다.

    - App 모드(App 설정 + installation_id 존재): 설치 토큰을 발급/캐시해서 사용
    - 그 외: PAT(GITHUB_TOKEN) 폴백
    """
    if settings.github_app_enabled and installation_id is not None:
        return await _installation_token(installation_id)
    return settings.GITHUB_TOKEN
