"""
Pydantic 입출력 스펙 (계약).

LLM 출력을 자유 텍스트가 아니라 이 스키마로 강제(Structured Output)해야
comment_poster가 정확한 파일/줄에 인라인 코멘트를 달 수 있다.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """이슈 심각도. critical > warning > suggestion 순."""

    critical = "critical"      # 즉시 수정 필수 (버그/보안/데이터 손실)
    warning = "warning"        # 수정 권장
    suggestion = "suggestion"  # 선택적 개선


class Category(str, Enum):
    """이슈 분류."""

    bug = "bug"
    security = "security"
    performance = "performance"
    style = "style"


class ReviewJob(BaseModel):
    """큐에 등록되는 리뷰 작업 단위."""

    # 큐에서 작업 종류를 구분하는 판별자(worker가 분기에 사용).
    type: Literal["review"] = "review"
    repo: str                       # "owner/name"
    pr_number: int
    head_sha: str
    action: str                     # "opened"(전체) | "synchronize"(증분)
    # GitHub App 설치 ID. 있으면 설치 토큰을 발급해 인증한다(없으면 PAT 폴백).
    installation_id: int | None = None
    # 로컬 시연 모드: diff를 직접 실어 보내면 GitHub 호출을 건너뛴다.
    local_diff: str | None = None


class FollowupJob(BaseModel):
    """리뷰 코멘트에 달린 사용자 질문에 답하는 후속 작업."""

    type: Literal["followup"] = "followup"
    repo: str
    pr_number: int
    installation_id: int | None = None
    comment_body: str               # 사용자가 남긴 질문(멘션 포함)
    # True: 인라인 코드 스레드 답글 / False: PR 대화(issue) 코멘트
    is_review_comment: bool = False
    # 스레드에 답글을 달 대상 코멘트 id (인라인일 때만).
    reply_to_comment_id: int | None = None
    # 로컬 시연 모드: GitHub 호출 없이 콘솔에 출력.
    local: bool = False


class ReviewComment(BaseModel):
    """LLM이 생성하는 개별 인라인 코멘트."""

    file_path: str
    line_number: int
    severity: Severity
    category: Category
    body: str                       # 사람이 읽을 코멘트 본문
    suggested_code: str | None = None  # 제안 코드(있으면)


class ReviewResult(BaseModel):
    """리뷰 1회의 전체 결과."""

    summary: str                                  # PR 요약 (본문 코멘트)
    comments: list[ReviewComment] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""
