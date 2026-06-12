"""
GitHub Webhook 수신 라우터.

역할: 문지기. 서명을 검증하고, 리뷰 작업을 큐에 등록만 한 뒤 즉시 응답한다.
실제 리뷰는 worker가 처리하므로 여기서는 절대 기다리지 않는다.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.security import verify_github_signature
from app.models.schemas import ReviewJob
from app.queue.producer import enqueue_review_job

logger = logging.getLogger(__name__)
router = APIRouter()

# 리뷰를 트리거할 PR 액션
_REVIEW_ACTIONS = {"opened", "synchronize", "reopened"}


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
):
    # 1) 서명 검증은 반드시 '원본 바이트'로 (파싱 후 재직렬화하면 서명 불일치)
    raw_body = await request.body()
    if not verify_github_signature(
        raw_body, x_hub_signature_256, settings.WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    # 2) PR 이벤트 중 리뷰 대상 액션만 처리
    if x_github_event == "pull_request" and payload.get("action") in _REVIEW_ACTIONS:
        pr = payload["pull_request"]
        job = ReviewJob(
            repo=payload["repository"]["full_name"],
            pr_number=pr["number"],
            head_sha=pr["head"]["sha"],
            action=payload["action"],
            # 로컬 시연 모드: 테스트 스크립트가 diff를 직접 실어 보낼 수 있음
            local_diff=payload.get("local_diff"),
        )
        await enqueue_review_job(job)

    # 3) 즉시 응답 → GitHub 10초 타임아웃/재시도 회피
    return {"status": "accepted"}
