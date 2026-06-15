"""
대화형 후속 작업 오케스트레이션.

흐름: 컨텍스트(PR diff) 수집 → LLM 답변 생성 → 적절한 위치에 게시.
    - 인라인 스레드 답글: 같은 스레드(reply)에 답변
    - PR 대화 코멘트: PR에 새 issue comment로 답변
    - 로컬 모드(local): GitHub 호출 없이 콘솔 출력
"""

from __future__ import annotations

import logging

from app.integrations.github_client import GitHubClient
from app.models.schemas import FollowupJob
from app.review import responder

logger = logging.getLogger(__name__)

# 답변 앞에 붙이는 서명 — 봇 답글 식별 + 일관된 브랜딩.
_SIGNATURE = "🧙 **CodeSage**"


async def run_followup(job: FollowupJob) -> None:
    """한 건의 후속 질문에 답한다."""
    gh = GitHubClient(job.repo, job.installation_id)

    # 1) 컨텍스트 수집 — PR 전체 diff (로컬 모드면 생략)
    diff_context = ""
    if not job.local:
        try:
            diff_context = await gh.fetch_pr_diff(job.pr_number)
        except Exception as exc:  # noqa: BLE001 - diff 못 가져와도 답변은 시도
            logger.warning("후속용 diff 수집 실패(컨텍스트 없이 진행): %s", exc)

    # 2) 답변 생성
    answer_text = await responder.answer(job.comment_body, diff_context)
    body = f"{_SIGNATURE}\n\n{answer_text}"

    # 3) 게시
    if job.local:
        print("\n" + "=" * 60)
        print(f"[후속 답변] {job.repo}#{job.pr_number}")
        print(body)
        print("=" * 60 + "\n")
        return

    if job.is_review_comment and job.reply_to_comment_id is not None:
        await gh.reply_to_review_comment(job.pr_number, job.reply_to_comment_id, body)
    else:
        await gh.post_summary(job.pr_number, body)
    logger.info("후속 답변 게시 완료: %s#%s", job.repo, job.pr_number)
