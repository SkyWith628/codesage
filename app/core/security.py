"""
GitHub Webhook 서명(HMAC) 검증 모듈.

/webhook 은 인터넷에 공개된 엔드포인트이므로, 누구나 가짜 PR 이벤트를
보내 우리 LLM 비용을 폭증시킬 수 있다. 서명 검증이 1차 방어선이다.
"""

from __future__ import annotations

import hashlib
import hmac


def verify_github_signature(
    payload_body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """
    GitHub Webhook의 HMAC-SHA256 서명을 검증한다.

    Args:
        payload_body: 원본 요청 바디 (반드시 파싱 전 raw bytes)
        signature_header: 'X-Hub-Signature-256' 헤더 값 (예: "sha256=abc...")
        secret: GitHub Webhook 설정 시 등록한 비밀키
    Returns:
        서명이 유효하면 True, 아니면 False
    """
    if not signature_header:
        return False

    # 우리가 가진 비밀키로 같은 방식의 해시를 직접 계산
    expected = "sha256=" + hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # 타이밍 공격 방지: 일반 == 비교 금지, compare_digest 사용
    # (== 는 글자 일치 개수에 따라 비교 시간이 달라져 비밀이 샐 수 있음)
    return hmac.compare_digest(expected, signature_header)


def sign_payload(payload_body: bytes, secret: str) -> str:
    """
    테스트/로컬 시연용: payload에 대한 올바른 서명 헤더 값을 생성한다.
    (scripts/send_fake_pr.py 가 진짜 GitHub처럼 서명을 붙이기 위해 사용)
    """
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"
