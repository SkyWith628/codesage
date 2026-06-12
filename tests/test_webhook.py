"""Webhook 엔드포인트 통합 테스트 (FastAPI TestClient).

서명 검증 + 이벤트 필터링 + 큐 등록까지 실제 HTTP 경로로 검증한다.
(Redis는 호출하지 않도록 enqueue를 가짜로 대체)
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.api.webhook as webhook_mod
from app.core.config import settings
from app.core.security import sign_payload
from app.main import app

client = TestClient(app)


@pytest.fixture
def captured(monkeypatch):
    """enqueue_review_job을 가짜로 바꿔 등록된 작업을 수집."""
    jobs = []

    async def fake_enqueue(job):
        jobs.append(job)

    monkeypatch.setattr(webhook_mod, "enqueue_review_job", fake_enqueue)
    return jobs


def _post(payload: dict, event: str = "pull_request", *, sign: bool = True, secret: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if sign:
        headers["X-Hub-Signature-256"] = sign_payload(body, secret or settings.WEBHOOK_SECRET)
    return client.post("/webhook", content=body, headers=headers)


def _pr_payload(action: str = "opened"):
    return {
        "action": action,
        "repository": {"full_name": "o/r"},
        "pull_request": {"number": 7, "head": {"sha": "abc"}},
    }


def test_valid_signed_pr_opened_enqueues(captured):
    resp = _post(_pr_payload("opened"))
    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0].repo == "o/r" and captured[0].pr_number == 7


def test_bad_signature_rejected(captured):
    resp = _post(_pr_payload("opened"), sign=True, secret="WRONG_SECRET")
    assert resp.status_code == 401
    assert captured == []  # 등록되지 않음


def test_missing_signature_rejected(captured):
    resp = _post(_pr_payload("opened"), sign=False)
    assert resp.status_code == 401
    assert captured == []


def test_irrelevant_action_ignored(captured):
    # PR이지만 'closed'는 리뷰 대상 아님 → 200이지만 등록 안 함
    resp = _post(_pr_payload("closed"))
    assert resp.status_code == 200
    assert captured == []


def test_non_pr_event_ignored(captured):
    resp = _post({"zen": "hi"}, event="ping")
    assert resp.status_code == 200
    assert captured == []
