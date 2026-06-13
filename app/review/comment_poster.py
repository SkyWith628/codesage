"""
리뷰 결과 게시기.

두 가지 출력 모드를 같은 인터페이스로 처리한다:
    - 운영 모드: GitHub PR에 요약 + 인라인 코멘트 게시
    - 로컬 모드(local_diff): 콘솔에 보기 좋게 출력 (GitHub 호출 안 함)
"""

from __future__ import annotations

import logging

from app.core.config import get_policy
from app.integrations.github_client import GitHubClient
from app.models.schemas import ReviewJob, ReviewResult, Severity

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {Severity.suggestion: 0, Severity.warning: 1, Severity.critical: 2}
_SEVERITY_EMOJI = {
    Severity.critical: "🔴",
    Severity.warning: "🟡",
    Severity.suggestion: "💡",
}


def _filter_and_limit(result: ReviewResult) -> ReviewResult:
    """정책의 min_severity / max_comments를 적용해 코멘트를 걸러낸다."""
    policy = get_policy().get("review", {})
    min_sev = Severity(policy.get("min_severity", "suggestion"))
    max_n = policy.get("max_comments", 20)
    threshold = _SEVERITY_ORDER[min_sev]

    kept = [c for c in result.comments if _SEVERITY_ORDER[c.severity] >= threshold]
    # 심각도 높은 순으로 정렬 후 상한 적용
    kept.sort(key=lambda c: _SEVERITY_ORDER[c.severity], reverse=True)
    result.comments = kept[:max_n]
    return result


def _build_summary_body(result: ReviewResult) -> str:
    """PR 상단에 달 요약 코멘트(markdown)를 만든다."""
    counts = {sev: 0 for sev in Severity}
    for c in result.comments:
        counts[c.severity] += 1
    badge = (
        f"🔴 Critical {counts[Severity.critical]} · "
        f"🟡 Warning {counts[Severity.warning]} · "
        f"💡 Suggestion {counts[Severity.suggestion]}"
    )
    return f"## 🧙 CodeSage Review\n\n{result.summary}\n\n**발견:** {badge}"


async def post(job: ReviewJob, result: ReviewResult) -> None:
    """모드에 맞춰 결과를 게시한다."""
    result = _filter_and_limit(result)

    if job.local_diff is not None:
        _post_to_console(job, result)
    else:
        await _post_to_github(job, result)


def _post_to_console(job: ReviewJob, result: ReviewResult) -> None:
    """로컬 시연: 콘솔에 출력."""
    print("\n" + "=" * 60)
    print(_build_summary_body(result))
    print("=" * 60)
    for c in result.comments:
        emoji = _SEVERITY_EMOJI[c.severity]
        print(f"\n{emoji} [{c.category.value}] {c.file_path}:{c.line_number}")
        print(f"   {c.body}")
        if c.suggested_code:
            print(f"   💡 제안:\n   {c.suggested_code}")
    print("\n" + "=" * 60 + "\n")


async def _post_to_github(job: ReviewJob, result: ReviewResult) -> None:
    """운영: GitHub PR에 게시."""
    gh = GitHubClient(job.repo, job.installation_id)
    await gh.post_summary(job.pr_number, _build_summary_body(result))
    for c in result.comments:
        emoji = _SEVERITY_EMOJI[c.severity]
        body = f"{emoji} **[{c.category.value}]** {c.body}"
        if c.suggested_code:
            body += f"\n\n```suggestion\n{c.suggested_code}\n```"
        await gh.post_inline_comment(
            job.pr_number, job.head_sha, c.file_path, c.line_number, body
        )
