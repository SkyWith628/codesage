"""파이프라인 통합 테스트 (로컬 모드, mock LLM).

GitHub/Claude를 호출하지 않는 local_diff + mock 경로로 전체 흐름을 검증한다.
"""

import pytest

from app.models.schemas import ReviewJob
from app.review.pipeline import run_review

LOCAL_DIFF = """diff --git a/auth.py b/auth.py
--- a/auth.py
+++ b/auth.py
@@ -1,1 +1,2 @@
 import jwt
+SECRET = "hardcoded"
"""


@pytest.mark.asyncio
async def test_run_review_local_mode_no_crash(capsys):
    job = ReviewJob(
        repo="demo/sandbox",
        pr_number=1,
        head_sha="fakesha",
        action="opened",
        local_diff=LOCAL_DIFF,
    )
    # 키가 없으면 mock 리뷰 → 콘솔에 결과 출력. 예외 없이 완주하면 성공.
    await run_review(job)
    out = capsys.readouterr().out
    assert "CodeSage Review" in out


@pytest.mark.asyncio
async def test_run_review_empty_diff_returns_silently():
    job = ReviewJob(
        repo="demo/sandbox",
        pr_number=2,
        head_sha="fakesha",
        action="opened",
        local_diff="",
    )
    # 변경이 없으면 조용히 종료 (예외 없음)
    await run_review(job)
