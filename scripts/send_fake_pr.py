"""
로컬 시연용: 진짜 GitHub처럼 서명을 붙여 가짜 PR Webhook을 서버에 전송한다.

사용법:
    # 서버 실행 후(다른 터미널):
    python scripts/send_fake_pr.py --diff samples/buggy_login.py.diff

GitHub 없이도 전체 파이프라인(수신→큐→worker→리뷰→콘솔 출력)을 확인할 수 있다.
diff를 payload의 local_diff 필드에 실어 보내므로 worker가 GitHub를 호출하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

# app 패키지를 import 할 수 있도록 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.security import sign_payload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="CodeSage 로컬 시연용 가짜 PR 전송")
    parser.add_argument("--diff", required=True, help="전송할 diff 파일 경로")
    parser.add_argument("--url", default="http://localhost:8000/webhook")
    parser.add_argument("--repo", default="demo/sandbox")
    parser.add_argument("--pr", type=int, default=1)
    parser.add_argument(
        "--action",
        default="opened",
        choices=["opened", "synchronize", "reopened"],
        help="PR 이벤트 액션 (synchronize = 새 커밋 push → 증분 리뷰)",
    )
    parser.add_argument("--sha", default="fakesha123", help="head 커밋 sha")
    args = parser.parse_args()

    diff_text = Path(args.diff).read_text(encoding="utf-8")

    payload = {
        "action": args.action,
        "repository": {"full_name": args.repo},
        "pull_request": {
            "number": args.pr,
            "head": {"sha": args.sha},
        },
        "local_diff": diff_text,   # ★ 로컬 모드 트리거
    }

    body = json.dumps(payload).encode("utf-8")
    signature = sign_payload(body, settings.WEBHOOK_SECRET)

    resp = httpx.post(
        args.url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
        },
        timeout=10,
    )
    print(f"→ 서버 응답: {resp.status_code} {resp.json()}")
    print("worker 로그(다른 터미널)에서 리뷰 결과를 확인하세요.")


if __name__ == "__main__":
    main()
