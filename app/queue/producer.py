"""
리뷰 작업을 Redis 큐에 등록하는 생산자(Producer).

Webhook 핸들러는 이 함수만 호출하고 즉시 응답한다.
실제 무거운 리뷰는 worker.py가 큐에서 꺼내 처리한다 (수신/처리 분리).
"""

from __future__ import annotations

import logging

import redis.asyncio as redis

from app.core.config import settings
from app.models.schemas import ReviewJob

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    """Redis 비동기 클라이언트 싱글턴."""
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def enqueue_review_job(job: ReviewJob) -> None:
    """리뷰 작업을 큐 왼쪽에 push한다 (FIFO: worker는 오른쪽에서 pop)."""
    client = _get_client()
    await client.lpush(settings.QUEUE_KEY, job.model_dump_json())
    logger.info("작업 등록: %s#%s (action=%s)", job.repo, job.pr_number, job.action)
