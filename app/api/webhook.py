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
from app.models.schemas import FollowupJob, ReviewJob
from app.queue.producer import enqueue_followup_job, enqueue_review_job

logger = logging.getLogger(__name__)
router = APIRouter()

# 리뷰를 트리거할 PR 액션
_REVIEW_ACTIONS = {"opened", "synchronize", "reopened"}


def _is_followup_trigger(payload: dict) -> bool:
    """
    대화형 후속을 발동할지 판단한다.
    조건: 새로 생성된 코멘트 + 봇이 아닌 사람 + 봇 멘션 포함.
    (봇 자신/타 봇 코멘트는 무시 → 무한루프 방지)
    """
    if payload.get("action") != "created":
        return False
    comment = payload.get("comment") or {}
    if (comment.get("user") or {}).get("type") == "Bot":
        return False
    body = comment.get("body") or ""
    return settings.BOT_MENTION.lower() in body.lower()


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

    repo = (payload.get("repository") or {}).get("full_name")
    installation_id = (payload.get("installation") or {}).get("id")

    # 2) PR 이벤트 중 리뷰 대상 액션만 처리
    if x_github_event == "pull_request" and payload.get("action") in _REVIEW_ACTIONS:
        pr = payload["pull_request"]
        job = ReviewJob(
            repo=repo,
            pr_number=pr["number"],
            head_sha=pr["head"]["sha"],
            action=payload["action"],
            # GitHub App이면 설치 ID가 실려 온다 → 설치 토큰 발급에 사용
            installation_id=installation_id,
            # 로컬 시연 모드: 테스트 스크립트가 diff를 직접 실어 보낼 수 있음
            local_diff=payload.get("local_diff"),
        )
        await enqueue_review_job(job)

    # 3) 코멘트 이벤트 — 봇을 멘션한 질문이면 대화형 후속을 등록
    elif x_github_event in ("issue_comment", "pull_request_review_comment") and (
        _is_followup_trigger(payload)
    ):
        is_review_comment = x_github_event == "pull_request_review_comment"
        # issue_comment는 PR/이슈 공용 이벤트 → PR이 아니면(이슈면) 스킵
        pr_number = _pr_number_from_comment(payload, is_review_comment)
        if pr_number is not None:
            comment = payload["comment"]
            job = FollowupJob(
                repo=repo,
                pr_number=pr_number,
                installation_id=installation_id,
                comment_body=comment["body"],
                is_review_comment=is_review_comment,
                reply_to_comment_id=comment["id"] if is_review_comment else None,
            )
            await enqueue_followup_job(job)

    # 4) 즉시 응답 → GitHub 10초 타임아웃/재시도 회피
    return {"status": "accepted"}


def _pr_number_from_comment(payload: dict, is_review_comment: bool) -> int | None:
    """코멘트 이벤트에서 PR 번호를 추출한다. PR이 아니면 None."""
    if is_review_comment:
        return (payload.get("pull_request") or {}).get("number")
    # issue_comment: 'issue'에 pull_request 키가 있어야 PR 코멘트
    issue = payload.get("issue") or {}
    if "pull_request" not in issue:
        return None
    return issue.get("number")
