"""
환경변수(.env)와 정책 파일(codesage.yaml)을 로딩하는 설정 모듈.

설계 의도:
    - 비밀 정보/인프라 주소 = 환경변수 (.env, 배포 환경마다 다름)
    - 리뷰 정책(모델, focus, guidelines) = YAML (운영자가 자주 손댐)
    두 가지를 분리해, 비개발자도 정책을 바꿀 수 있게 한다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. .env 파일을 자동으로 읽는다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Gemini API (Google) ---
    GEMINI_API_KEY: str = ""
    REVIEW_MODEL: str = "gemini-2.5-flash"        # 리뷰용 (무료 티어, 품질 균형)
    SUMMARY_MODEL: str = "gemini-2.5-flash-lite"  # 대화 응답용 (가벼움·높은 RPM)

    # --- GitHub ---
    WEBHOOK_SECRET: str = "change-me"
    GITHUB_TOKEN: str = ""              # PAT 폴백 (App 미설정 시 사용)
    GITHUB_API_BASE: str = "https://api.github.com"

    # 대화형 후속을 트리거하는 멘션 문자열 (이 단어로 봇을 호출).
    BOT_MENTION: str = "@codesage"

    # --- GitHub App (설치 토큰 자동 발급) ---
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY: str = ""       # PEM 본문 (줄바꿈은 \n으로 이스케이프 가능)
    GITHUB_APP_PRIVATE_KEY_PATH: str = ""  # 또는 PEM 파일 경로 (위보다 우선)

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    QUEUE_KEY: str = "codesage:review:queue"

    # --- DB (비어 있으면 영속화 건너뜀) ---
    DATABASE_URL: str = ""

    # --- 정책 파일 경로 ---
    CONFIG_PATH: str = "config/codesage.yaml"

    @property
    def llm_enabled(self) -> bool:
        """Gemini API 키가 있으면 True. 없으면 mock 리뷰로 동작."""
        return bool(self.GEMINI_API_KEY)

    @property
    def db_enabled(self) -> bool:
        """DATABASE_URL이 있으면 True. 없으면 DB 저장을 건너뜀."""
        return bool(self.DATABASE_URL)

    @property
    def github_app_private_key(self) -> str:
        """
        App 비밀키(PEM)를 반환한다.
        PATH가 지정되면 파일에서 읽고, 아니면 인라인 키의 \\n 이스케이프를 복원한다.
        """
        if self.GITHUB_APP_PRIVATE_KEY_PATH:
            return Path(self.GITHUB_APP_PRIVATE_KEY_PATH).read_text(encoding="utf-8")
        return self.GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")

    @property
    def github_app_enabled(self) -> bool:
        """App ID와 비밀키(인라인 또는 파일)가 모두 있으면 App 모드."""
        has_key = bool(self.GITHUB_APP_PRIVATE_KEY or self.GITHUB_APP_PRIVATE_KEY_PATH)
        return bool(self.GITHUB_APP_ID) and has_key


@lru_cache
def get_settings() -> Settings:
    """Settings 싱글턴. 매 호출마다 .env를 다시 읽지 않도록 캐싱."""
    return Settings()


@lru_cache
def get_policy() -> dict[str, Any]:
    """codesage.yaml 리뷰 정책을 dict로 로딩 (캐싱)."""
    path = Path(get_settings().CONFIG_PATH)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# 모듈 전역에서 편하게 쓰기 위한 별칭
settings = get_settings()
