"""증분 리뷰 판단 로직 + fetch_diff 모드 분기 테스트 (네트워크/DB 불필요)."""

import pytest

from app.models.schemas import ReviewJob
from app.review.diff_parser import fetch_diff, is_incremental

# ── is_incremental (순수 함수) ────────────────────────────────────────────────

def test_synchronize_with_new_sha_is_incremental():
    assert is_incremental("synchronize", last_sha="abc", head_sha="def") is True


def test_synchronize_without_prior_review_is_full():
    # 직전 리뷰 sha 없음 → 전체 리뷰
    assert is_incremental("synchronize", last_sha=None, head_sha="def") is False


def test_synchronize_same_sha_is_full():
    # head가 안 바뀜 → 증분 아님
    assert is_incremental("synchronize", last_sha="abc", head_sha="abc") is False


def test_opened_is_always_full():
    # 최초 PR(open)은 prior sha가 있어도 전체 리뷰
    assert is_incremental("opened", last_sha="abc", head_sha="def") is False


# ── fetch_diff 모드 분기 (로컬 모드는 항상 local_diff 사용) ─────────────────────

@pytest.mark.asyncio
async def test_fetch_diff_local_mode_ignores_sha():
    job = ReviewJob(
        repo="demo/sandbox", pr_number=1, head_sha="def",
        action="synchronize", local_diff="LOCAL_DIFF_CONTENT",
    )
    # 로컬 모드면 증분 조건이어도 GitHub을 안 부르고 local_diff 반환
    out = await fetch_diff(job, last_sha="abc")
    assert out == "LOCAL_DIFF_CONTENT"


@pytest.mark.asyncio
async def test_fetch_diff_incremental_calls_compare(monkeypatch):
    """운영 모드 + 증분 조건이면 compare diff를 호출하는지 검증 (GitHub은 가짜로 대체)."""
    calls = {}

    class FakeGitHub:
        def __init__(self, repo, installation_id=None):
            calls["repo"] = repo

        async def fetch_compare_diff(self, base, head):
            calls["compare"] = (base, head)
            return "COMPARE_DIFF"

        async def fetch_pr_diff(self, pr_number):
            calls["full"] = pr_number
            return "FULL_DIFF"

    monkeypatch.setattr("app.review.diff_parser.GitHubClient", FakeGitHub)

    job = ReviewJob(repo="o/r", pr_number=7, head_sha="newsha", action="synchronize")
    out = await fetch_diff(job, last_sha="oldsha")

    assert out == "COMPARE_DIFF"
    assert calls["compare"] == ("oldsha", "newsha")
    assert "full" not in calls


@pytest.mark.asyncio
async def test_fetch_diff_full_mode_calls_pr_diff(monkeypatch):
    """opened 이벤트는 PR 전체 diff를 호출."""
    calls = {}

    class FakeGitHub:
        def __init__(self, repo, installation_id=None):
            pass

        async def fetch_pr_diff(self, pr_number):
            calls["full"] = pr_number
            return "FULL_DIFF"

    monkeypatch.setattr("app.review.diff_parser.GitHubClient", FakeGitHub)

    job = ReviewJob(repo="o/r", pr_number=7, head_sha="sha", action="opened")
    out = await fetch_diff(job, last_sha="oldsha")

    assert out == "FULL_DIFF"
    assert calls["full"] == 7
