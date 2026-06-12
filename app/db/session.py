"""
DB 세션 관리. DATABASE_URL이 없으면 모든 영속화를 우아하게 건너뛴다
(로컬 시연은 DB 없이도 동작해야 하므로).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.db_models import Base
from app.models.schemas import ReviewJob, ReviewResult

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def _get_factory() -> async_sessionmaker | None:
    """엔진/세션 팩토리를 지연 초기화. DB 미설정 시 None."""
    global _engine, _session_factory
    if not settings.db_enabled:
        return None
    if _session_factory is None:
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """앱 시작 시 테이블 생성 (없으면). 운영에선 Alembic 마이그레이션 권장."""
    if not settings.db_enabled or _engine is None:
        factory = _get_factory()
        if factory is None:
            logger.info("DATABASE_URL 미설정 → DB 영속화 비활성화")
            return
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_last_reviewed_sha(repo: str, pr_number: int) -> str | None:
    """
    이 PR을 가장 최근에 리뷰한 head_sha를 반환한다 (증분 리뷰 기준점).
    DB가 없거나 이전 리뷰가 없으면 None → 호출측은 전체 리뷰로 폴백.
    """
    factory = _get_factory()
    if factory is None:
        return None
    from sqlalchemy import select

    from app.models.db_models import ReviewRun

    try:
        async with factory() as session:
            stmt = (
                select(ReviewRun.head_sha)
                .where(
                    ReviewRun.repo_full_name == repo,
                    ReviewRun.pr_number == pr_number,
                )
                .order_by(ReviewRun.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.warning("직전 리뷰 sha 조회 실패(무시): %s", exc)
        return None


async def save_review(job: ReviewJob, result: ReviewResult, duration_ms: int) -> None:
    """리뷰 결과를 DB에 저장 (best-effort). 실패해도 파이프라인은 진행."""
    factory = _get_factory()
    if factory is None:
        return
    from app.models.db_models import ReviewCommentRow, ReviewRun

    try:
        async with factory() as session:
            run = ReviewRun(
                repo_full_name=job.repo,
                pr_number=job.pr_number,
                head_sha=job.head_sha,
                model_used=result.model_used,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                duration_ms=duration_ms,
                comments=[
                    ReviewCommentRow(
                        file_path=c.file_path,
                        line_number=c.line_number,
                        severity=c.severity.value,
                        category=c.category.value,
                        body=c.body,
                        suggested_code=c.suggested_code,
                        posted=True,
                    )
                    for c in result.comments
                ],
            )
            session.add(run)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - 영속화 실패는 치명적이지 않음
        logger.warning("리뷰 기록 저장 실패(무시): %s", exc)
