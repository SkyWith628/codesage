"""
SQLAlchemy ORM 모델 (리뷰 기록 영속화).

저장 목적:
    - 비용 모니터링 (토큰/시간)
    - 모델별 성능 비교 (베이스라인 분석)
    - 증분 리뷰 시 '직전 리뷰 시점' 추적
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReviewRun(Base):
    """리뷰 1회 실행 기록."""

    __tablename__ = "review_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_full_name: Mapped[str] = mapped_column(String(255), index=True)
    pr_number: Mapped[int] = mapped_column(index=True)
    head_sha: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    model_used: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    duration_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        # timezone=True → Postgres 'TIMESTAMP WITH TIME ZONE'.
        # default 값이 tz-aware(datetime.now(timezone.utc))라 컬럼도 aware여야 일치.
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    comments: Mapped[list["ReviewCommentRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ReviewCommentRow(Base):
    """게시된 개별 코멘트 기록."""

    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("review_runs.id"))
    file_path: Mapped[str] = mapped_column(String(512))
    line_number: Mapped[int] = mapped_column(default=0)
    severity: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    suggested_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted: Mapped[bool] = mapped_column(default=False)
    github_comment_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    run: Mapped["ReviewRun"] = relationship(back_populates="comments")
