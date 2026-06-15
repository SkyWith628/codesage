"""대화형 후속 테스트.

검증 범위:
    - webhook: 멘션된 PR 코멘트(issue/review) → 후속 작업 등록
    - webhook: 멘션 없음 / 봇 코멘트 / 비-PR 이슈 → 무시
    - run_followup: 인라인 답글 vs PR 코멘트 게시 경로 분기 (가짜 클라이언트)
    - responder: 키 없을 때 mock 답변
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.api.webhook as webhook_mod
from app.core.config import settings
from app.core.security import sign_payload
from app.main import app
from app.models.schemas import FollowupJob
from app.review import followup, responder

client = TestClient(app)


# ── webhook 트리거 ────────────────────────────────────────────────────────────


@pytest.fixture
def captured(monkeypatch):
    """enqueue_followup_job을 가짜로 바꿔 등록된 후속 작업을 수집."""
    jobs = []

    async def fake_enqueue(job):
        jobs.append(job)

    monkeypatch.setattr(webhook_mod, "enqueue_followup_job", fake_enqueue)
    return jobs


def _post(payload: dict, event: str):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "X-GitHub-Event": event,
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sign_payload(body, settings.WEBHOOK_SECRET),
    }
    return client.post("/webhook", content=body, headers=headers)


def _issue_comment(body: str, *, is_pr: bool = True, user_type: str = "User"):
    issue = {"number": 7}
    if is_pr:
        issue["pull_request"] = {"url": "x"}
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "issue": issue,
        "comment": {"id": 100, "body": body, "user": {"type": user_type}},
        "installation": {"id": 55},
    }


def _review_comment(body: str, user_type: str = "User"):
    return {
        "action": "created",
        "repository": {"full_name": "o/r"},
        "pull_request": {"number": 7},
        "comment": {"id": 200, "body": body, "user": {"type": user_type}},
    }


def test_mentioned_issue_comment_enqueues(captured):
    resp = _post(_issue_comment("@codesage 이거 왜 이래?"), "issue_comment")
    assert resp.status_code == 200
    assert len(captured) == 1
    job = captured[0]
    assert job.pr_number == 7 and job.is_review_comment is False
    assert job.reply_to_comment_id is None and job.installation_id == 55


def test_mentioned_review_comment_replies_in_thread(captured):
    resp = _post(_review_comment("@codesage 설명해줘"), "pull_request_review_comment")
    assert resp.status_code == 200
    assert len(captured) == 1
    job = captured[0]
    assert job.is_review_comment is True
    assert job.reply_to_comment_id == 200  # 그 코멘트 스레드에 답글


def test_comment_without_mention_ignored(captured):
    resp = _post(_issue_comment("그냥 일반 코멘트"), "issue_comment")
    assert resp.status_code == 200
    assert captured == []


def test_bot_comment_ignored_to_prevent_loop(captured):
    # 봇이 단 코멘트는 멘션이 있어도 무시 (무한루프 방지)
    resp = _post(_issue_comment("@codesage 재귀!", user_type="Bot"), "issue_comment")
    assert resp.status_code == 200
    assert captured == []


def test_non_pr_issue_comment_ignored(captured):
    # 일반 이슈(코드 PR 아님)의 코멘트는 무시
    resp = _post(_issue_comment("@codesage 질문", is_pr=False), "issue_comment")
    assert resp.status_code == 200
    assert captured == []


# ── run_followup 게시 경로 ────────────────────────────────────────────────────


class _FakeGitHub:
    def __init__(self, repo, installation_id=None):
        self.calls = []

    async def fetch_pr_diff(self, pr_number):
        return "diff --git a/x b/x\n+added"

    async def reply_to_review_comment(self, pr_number, comment_id, body):
        self.calls.append(("reply", comment_id, body))

    async def post_summary(self, pr_number, body):
        self.calls.append(("summary", pr_number, body))


@pytest.fixture
def fake_gh(monkeypatch):
    instances = []

    def factory(repo, installation_id=None):
        gh = _FakeGitHub(repo, installation_id)
        instances.append(gh)
        return gh

    monkeypatch.setattr(followup, "GitHubClient", factory)
    # LLM 호출 없이 고정 답변
    async def fake_answer(question, diff_context):
        return "답변입니다."

    monkeypatch.setattr(followup.responder, "answer", fake_answer)
    return instances


@pytest.mark.asyncio
async def test_run_followup_review_comment_replies(fake_gh):
    job = FollowupJob(
        repo="o/r", pr_number=7, comment_body="@codesage q",
        is_review_comment=True, reply_to_comment_id=200,
    )
    await followup.run_followup(job)
    calls = fake_gh[0].calls
    assert calls[0][0] == "reply" and calls[0][1] == 200
    assert "CodeSage" in calls[0][2] and "답변입니다." in calls[0][2]


@pytest.mark.asyncio
async def test_run_followup_issue_comment_posts_summary(fake_gh):
    job = FollowupJob(
        repo="o/r", pr_number=7, comment_body="@codesage q", is_review_comment=False
    )
    await followup.run_followup(job)
    calls = fake_gh[0].calls
    assert calls[0][0] == "summary" and calls[0][1] == 7


@pytest.mark.asyncio
async def test_run_followup_local_prints(capsys, monkeypatch):
    async def fake_answer(question, diff_context):
        return "로컬 답변"

    monkeypatch.setattr(followup.responder, "answer", fake_answer)
    job = FollowupJob(repo="o/r", pr_number=7, comment_body="q", local=True)
    await followup.run_followup(job)
    out = capsys.readouterr().out
    assert "로컬 답변" in out


@pytest.mark.asyncio
async def test_responder_mock_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    out = await responder.answer("질문", "diff")
    assert "MOCK" in out
