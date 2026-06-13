"""
GitHub REST API 래퍼.

운영 모드에서만 실제로 호출된다. 로컬 시연(local_diff) 모드에서는
diff를 직접 받으므로 이 클라이언트가 필요 없다.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.integrations.github_auth import resolve_token

logger = logging.getLogger(__name__)


class GitHubClient:
    """특정 레포에 대한 GitHub API 호출을 캡슐화."""

    def __init__(self, repo: str, installation_id: int | None = None) -> None:
        self.repo = repo  # "owner/name"
        # 토큰은 만료되므로 생성 시점에 고정하지 않고 호출마다 해결(resolve)한다.
        self.installation_id = installation_id

    async def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        """호출 직전에 유효한 토큰으로 인증 헤더를 구성한다."""
        token = await resolve_token(self.installation_id)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def fetch_pr_diff(self, pr_number: int) -> str:
        """PR의 통합 diff 문자열을 가져온다 (diff 미디어타입)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/pulls/{pr_number}"
        headers = await self._headers(accept="application/vnd.github.v3.diff")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def fetch_compare_diff(self, base_sha: str, head_sha: str) -> str:
        """두 커밋 사이(base...head)의 diff만 가져온다 (증분 리뷰용)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/compare/{base_sha}...{head_sha}"
        headers = await self._headers(accept="application/vnd.github.diff")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def post_summary(self, pr_number: int, body: str) -> None:
        """PR 본문에 요약 코멘트를 단다 (issue comment)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/issues/{pr_number}/comments"
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json={"body": body})
            resp.raise_for_status()

    async def reply_to_review_comment(
        self, pr_number: int, comment_id: int, body: str
    ) -> None:
        """인라인 리뷰 코멘트 스레드에 답글을 단다 (같은 스레드에 묶임)."""
        url = (
            f"{settings.GITHUB_API_BASE}/repos/{self.repo}"
            f"/pulls/{pr_number}/comments/{comment_id}/replies"
        )
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json={"body": body})
            resp.raise_for_status()

    async def post_inline_comment(
        self, pr_number: int, commit_sha: str, path: str, line: int, body: str
    ) -> int | None:
        """특정 파일/줄에 인라인 리뷰 코멘트를 단다. 반환: 생성된 코멘트 id."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/pulls/{pr_number}/comments"
        data = {
            "body": body,
            "commit_id": commit_sha,
            "path": path,
            "line": line,
            "side": "RIGHT",  # 변경 후(오른쪽) 코드 기준
        }
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=data)
            if resp.status_code >= 400:
                # 줄 번호가 diff 범위를 벗어나면 422 — 치명적이지 않으니 로깅만
                logger.warning("인라인 코멘트 실패(%s): %s", resp.status_code, resp.text[:200])
                return None
            return resp.json().get("id")
