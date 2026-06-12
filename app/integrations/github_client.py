"""
GitHub REST API 래퍼.

운영 모드에서만 실제로 호출된다. 로컬 시연(local_diff) 모드에서는
diff를 직접 받으므로 이 클라이언트가 필요 없다.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GitHubClient:
    """특정 레포에 대한 GitHub API 호출을 캡슐화."""

    def __init__(self, repo: str) -> None:
        self.repo = repo  # "owner/name"
        self._headers = {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def fetch_pr_diff(self, pr_number: int) -> str:
        """PR의 통합 diff 문자열을 가져온다 (diff 미디어타입)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/pulls/{pr_number}"
        headers = {**self._headers, "Accept": "application/vnd.github.v3.diff"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def fetch_compare_diff(self, base_sha: str, head_sha: str) -> str:
        """두 커밋 사이(base...head)의 diff만 가져온다 (증분 리뷰용)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/compare/{base_sha}...{head_sha}"
        headers = {**self._headers, "Accept": "application/vnd.github.diff"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text

    async def post_summary(self, pr_number: int, body: str) -> None:
        """PR 본문에 요약 코멘트를 단다 (issue comment)."""
        url = f"{settings.GITHUB_API_BASE}/repos/{self.repo}/issues/{pr_number}/comments"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers, json={"body": body})
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
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers, json=data)
            if resp.status_code >= 400:
                # 줄 번호가 diff 범위를 벗어나면 422 — 치명적이지 않으니 로깅만
                logger.warning("인라인 코멘트 실패(%s): %s", resp.status_code, resp.text[:200])
                return None
            return resp.json().get("id")
