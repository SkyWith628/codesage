"""worker의 작업 타입 분기(_dispatch) 테스트.

큐에 들어온 raw JSON의 type 판별자를 보고 리뷰/후속 핸들러로
올바르게 라우팅하는지 검증한다. (run_review/run_followup은 가짜로 대체)
"""

from __future__ import annotations

import pytest

from app.models.schemas import FollowupJob, ReviewJob
from app.queue import worker


@pytest.mark.asyncio
async def test_dispatch_routes_review(monkeypatch):
    seen = {}

    async def fake_review(job):
        seen["review"] = job

    async def fake_followup(job):
        seen["followup"] = job

    monkeypatch.setattr(worker, "run_review", fake_review)
    monkeypatch.setattr(worker, "run_followup", fake_followup)

    raw = ReviewJob(repo="o/r", pr_number=1, head_sha="s", action="opened").model_dump_json()
    await worker._dispatch(raw)

    assert "review" in seen and "followup" not in seen


@pytest.mark.asyncio
async def test_dispatch_routes_followup(monkeypatch):
    seen = {}

    async def fake_review(job):
        seen["review"] = job

    async def fake_followup(job):
        seen["followup"] = job

    monkeypatch.setattr(worker, "run_review", fake_review)
    monkeypatch.setattr(worker, "run_followup", fake_followup)

    raw = FollowupJob(repo="o/r", pr_number=1, comment_body="q").model_dump_json()
    await worker._dispatch(raw)

    assert "followup" in seen and "review" not in seen


@pytest.mark.asyncio
async def test_dispatch_defaults_to_review_when_type_missing(monkeypatch):
    """판별자가 없는 옛 형식도 리뷰로 처리(하위호환)."""
    seen = {}

    async def fake_review(job):
        seen["review"] = job

    monkeypatch.setattr(worker, "run_review", fake_review)

    raw = '{"repo": "o/r", "pr_number": 1, "head_sha": "s", "action": "opened"}'
    await worker._dispatch(raw)

    assert "review" in seen
