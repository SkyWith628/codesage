"""
컨텍스트 수집기 (Should 단계).

변경된 코드만으로는 부족할 때, 관련 함수 정의나 레포 컨벤션을
LLM 프롬프트에 추가로 끼워넣는다(RAG의 단순 버전).

※ 골격 단계에서는 codesage.yaml의 guidelines(팀 컨벤션)만 반환한다.
   추후 벡터DB 기반 관련 코드 검색으로 확장.
"""

from __future__ import annotations

from app.core.config import get_policy
from app.review.diff_parser import FileDiff


def build(files: list[FileDiff]) -> str:
    """LLM 프롬프트에 추가할 컨텍스트 문자열을 만든다."""
    policy = get_policy().get("review", {})
    guidelines = policy.get("guidelines", "").strip()

    parts: list[str] = []
    if guidelines:
        parts.append("# 팀 컨벤션\n" + guidelines)

    # TODO(확장): 변경 함수가 참조하는 정의를 벡터 검색해 추가
    return "\n\n".join(parts)
