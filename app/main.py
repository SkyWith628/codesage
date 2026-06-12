"""
CodeSage API 서버 진입점 (FastAPI 앱).

실행: uvicorn app.main:app --host 0.0.0.0 --port 8000
이 프로세스는 'Webhook 수신 + 큐 등록'만 담당한다. 리뷰는 worker가 처리.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api import health, webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="CodeSage – AI Code Review Agent",
    description="GitHub PR을 자동 리뷰하는 AI 에이전트",
    version="0.1.0",
)

app.include_router(health.router, tags=["health"])
app.include_router(webhook.router, tags=["webhook"])


@app.get("/")
async def root() -> dict:
    return {"name": "CodeSage", "docs": "/docs", "health": "/health"}
