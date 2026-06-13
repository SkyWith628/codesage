"""
큐에서 작업을 꺼내 리뷰 파이프라인을 실행하는 소비자(Consumer).

별도 프로세스로 실행된다:
    python -m app.queue.worker

여러 개를 띄우면 그만큼 동시 처리량이 늘어난다 (수평 확장).
"""

from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as redis

from app.core.config import settings
from app.db.session import init_db
from app.models.schemas import FollowupJob, ReviewJob
from app.review.followup import run_followup
from app.review.pipeline import run_review

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("codesage.worker")


async def consume_loop() -> None:
    """큐를 무한 폴링하며 작업을 하나씩 처리한다."""
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    await init_db()
    logger.info("Worker 시작. 큐 대기 중: %s", settings.QUEUE_KEY)

    while True:
        # brpop: 작업이 들어올 때까지 블로킹 (busy-wait 방지). timeout=5초마다 깨어남.
        item = await client.brpop(settings.QUEUE_KEY, timeout=5)
        if item is None:
            continue  # 타임아웃 — 작업 없음, 다시 대기

        _, raw = item  # (queue_key, value)
        try:
            await _dispatch(raw)
        except Exception:  # noqa: BLE001 - 한 작업 실패가 worker를 죽이면 안 됨
            logger.exception("작업 처리 실패 (건너뜀): %s", raw[:200])


async def _dispatch(raw: str) -> None:
    """작업 JSON의 type 판별자를 보고 알맞은 핸들러로 보낸다."""
    job_type = json.loads(raw).get("type", "review")
    if job_type == "followup":
        job = FollowupJob.model_validate_json(raw)
        logger.info("후속 처리 시작: %s#%s", job.repo, job.pr_number)
        await run_followup(job)
        logger.info("후속 처리 완료: %s#%s", job.repo, job.pr_number)
    else:
        job = ReviewJob.model_validate_json(raw)
        logger.info("리뷰 처리 시작: %s#%s", job.repo, job.pr_number)
        await run_review(job)
        logger.info("리뷰 처리 완료: %s#%s", job.repo, job.pr_number)


if __name__ == "__main__":
    asyncio.run(consume_loop())
