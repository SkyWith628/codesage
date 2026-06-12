"""
리뷰 파이프라인 오케스트레이션.

6단계(수집 → 청킹/필터 → 정적분석 → 컨텍스트 → LLM → 게시)를 지휘한다.
각 단계는 독립 모듈이라, 한 단계만 교체/테스트할 수 있다 (단일 책임 원칙).
"""

from __future__ import annotations

import logging
import time

from app.db.session import get_last_reviewed_sha, save_review
from app.models.schemas import ReviewJob
from app.review import (
    comment_poster,
    context_builder,
    diff_parser,
    llm_reviewer,
    static_analysis,
)

logger = logging.getLogger(__name__)


async def run_review(job: ReviewJob) -> None:
    """한 PR에 대한 리뷰 전체 흐름을 실행한다."""
    start = time.monotonic()

    # 1) Diff 수집 — 증분 조건이면 '직전 리뷰 이후 변경분'만
    last_sha = await get_last_reviewed_sha(job.repo, job.pr_number)
    incremental = diff_parser.is_incremental(job.action, last_sha, job.head_sha)
    logger.info(
        "리뷰 모드: %s (%s#%s)",
        "증분(incremental)" if incremental else "전체(full)",
        job.repo, job.pr_number,
    )
    diff_text = await diff_parser.fetch_diff(job, last_sha)

    # 2) 파일 단위 청킹 + 무시 파일 필터링
    files = diff_parser.chunk_and_filter(diff_text)
    if not files:
        logger.info("리뷰할 코드 변경 없음: %s#%s", job.repo, job.pr_number)
        return

    # 3) 정적 분석 (기계적 이슈 1차 수집)
    lint_findings = static_analysis.run_linters(files)

    # 4) 컨텍스트 수집 (팀 컨벤션 등)
    context = context_builder.build(files)

    # 5) LLM 리뷰 (구조화 JSON)
    result = await llm_reviewer.review(files, lint_findings, context)

    # 6) 게시 (콘솔 또는 GitHub)
    await comment_poster.post(job, result)

    # 7) 기록 저장 (DB 있으면)
    duration_ms = int((time.monotonic() - start) * 1000)
    await save_review(job, result, duration_ms)
    logger.info(
        "리뷰 완료: %s#%s — 코멘트 %d건, %dms (model=%s)",
        job.repo, job.pr_number, len(result.comments), duration_ms, result.model_used,
    )
