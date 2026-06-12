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

    # --- Claude API ---
    ANTHROPIC_API_KEY: str = ""
    REVIEW_MODEL: str = "claude-opus-4-8"
    SUMMARY_MODEL: str = "claude-haiku-4-5"

    # --- GitHub ---
    WEBHOOK_SECRET: str = "change-me"
    GITHUB_TOKEN: str = ""
    GITHUB_API_BASE: str = "https://api.github.com"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    QUEUE_KEY: str = "codesage:review:queue"

    # --- DB (비어 있으면 영속화 건너뜀) ---
    DATABASE_URL: str = ""

    # --- 정책 파일 경로 ---
    CONFIG_PATH: str = "config/codesage.yaml"

    @property
    def llm_enabled(self) -> bool:
        """Claude API 키가 있으면 True. 없으면 mock 리뷰로 동작."""
        return bool(self.ANTHROPIC_API_KEY)

    @property
    def db_enabled(self) -> bool:
        """DATABASE_URL이 있으면 True. 없으면 DB 저장을 건너뜀."""
        return bool(self.DATABASE_URL)


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
