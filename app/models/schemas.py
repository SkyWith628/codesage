"""
Pydantic 입출력 스펙 (계약).

LLM 출력을 자유 텍스트가 아니라 이 스키마로 강제(Structured Output)해야
comment_poster가 정확한 파일/줄에 인라인 코멘트를 달 수 있다.
"""

from __future__ import annotations

from enum import Enum

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

    repo: str                       # "owner/name"
    pr_number: int
    head_sha: str
    action: str                     # "opened"(전체) | "synchronize"(증분)
    # 로컬 시연 모드: diff를 직접 실어 보내면 GitHub 호출을 건너뛴다.
    local_diff: str | None = None


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
