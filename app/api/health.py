"""헬스체크 엔드포인트. 로드밸런서/K8s가 서버 생존을 확인하는 데 사용."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """서버 상태와 주요 기능 활성화 여부를 반환."""
    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,   # Claude 키 존재 여부
        "db_enabled": settings.db_enabled,     # DB 영속화 여부
    }
