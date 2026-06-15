"""코멘트 게시 테스트: 콘솔 모드 + GitHub 모드(가짜 클라이언트) + 필터링."""

import pytest

from app.models.schemas import (
    Category,
    ReviewComment,
    ReviewJob,
    ReviewResult,
    Severity,
)
from app.review import comment_poster


def _comment(sev=Severity.critical, cat=Category.security, path="a.py", line=3):
    return ReviewComment(
        file_path=path, line_number=line, severity=sev, category=cat, body="이슈"
    )


@pytest.mark.asyncio
async def test_console_mode_outputs_summary_and_comment(capsys):
    job = ReviewJob(repo="o/r", pr_number=1, head_sha="s", action="opened", local_diff="x")
    result = ReviewResult(summary="요약", comments=[_comment()])
    await comment_poster.post(job, result)
    out = capsys.readouterr().out
    assert "CodeSage Review" in out
    assert "a.py:3" in out


@pytest.mark.asyncio
async def test_github_mode_posts_summary_and_inline(monkeypatch):
    posts = {"summary": [], "inline": []}

    class FakeGitHub:
        def __init__(self, repo, installation_id=None):
            self.repo = repo

        async def post_summary(self, pr, body):
            posts["summary"].append((pr, body))

        async def post_inline_comment(self, pr, sha, path, line, body):
            posts["inline"].append((path, line))
            return 1

    monkeypatch.setattr(comment_poster, "GitHubClient", FakeGitHub)

    # local_diff 없음 → GitHub 운영 모드
    job = ReviewJob(repo="o/r", pr_number=5, head_sha="sha", action="opened")
    result = ReviewResult(summary="요약", comments=[_comment(path="auth.py", line=8)])
    await comment_poster.post(job, result)

    assert len(posts["summary"]) == 1
    assert posts["summary"][0][0] == 5
    assert posts["inline"] == [("auth.py", 8)]


@pytest.mark.asyncio
async def test_comments_sorted_critical_first(monkeypatch):
    order = []

    class FakeGitHub:
        def __init__(self, repo, installation_id=None):
            pass

        async def post_summary(self, pr, body):
            pass

        async def post_inline_comment(self, pr, sha, path, line, body):
            order.append(path)
            return 1

    monkeypatch.setattr(comment_poster, "GitHubClient", FakeGitHub)

    job = ReviewJob(repo="o/r", pr_number=1, head_sha="sha", action="opened")
    result = ReviewResult(
        summary="s",
        comments=[
            _comment(sev=Severity.suggestion, path="low.py"),
            _comment(sev=Severity.critical, path="high.py"),
        ],
    )
    await comment_poster.post(job, result)
    # 심각도 높은 것이 먼저 게시되어야 함
    assert order[0] == "high.py"
