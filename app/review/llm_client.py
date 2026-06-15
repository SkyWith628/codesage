"""
Gemini 호출 공통 래퍼.

reviewer(구조화 리뷰)와 responder(대화 응답)가 같은 방식으로 Gemini를 부르므로,
'클라이언트 생성 + 일시적 오류 재시도'를 한 곳에 모은다 (DRY).

핵심: 무료 티어 모델은 순간 과부하로 503/429를 자주 던진다. 이는 '일시적'이므로
지수 백오프(간격을 2배씩 늘림) + 지터(무작위 지연)로 재시도하면 대부분 통과한다.
키/요청 오류(400·401·403)는 재시도해도 소용없으므로 즉시 예외를 전파한다.
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.core.config import settings

logger = logging.getLogger(__name__)

# 재시도할 가치가 있는 '일시적' HTTP 상태 코드.
#   429: 레이트리밋(요청 과다)  500: 내부 오류  503: 과부하  504: 게이트웨이 타임아웃
_TRANSIENT_CODES = {429, 500, 503, 504}

_MAX_ATTEMPTS = 4   # 최초 1회 + 재시도 3회
_MAX_BACKOFF = 8.0  # 단일 대기 상한(초)


async def generate(model: str, contents: str, config):  # noqa: ANN201
    """
    Gemini generate_content를 호출하고, 일시적 오류면 지수 백오프로 재시도한다.

    Args:
        model: 모델 ID (예: gemini-2.5-flash)
        contents: user 프롬프트 문자열
        config: types.GenerateContentConfig (system_instruction 등)
    Returns:
        google.genai의 GenerateContentResponse
    Raises:
        APIError: 비일시적 오류이거나, 재시도를 모두 소진한 경우
    """
    from google import genai
    from google.genai.errors import APIError

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except APIError as exc:
            code = getattr(exc, "code", None)
            # 비일시적이거나 마지막 시도면 그대로 전파 → 호출측이 '리뷰 실패'로 처리
            if code not in _TRANSIENT_CODES or attempt == _MAX_ATTEMPTS:
                raise
            # 지수 백오프(1, 2, 4초…) + 지터(0~0.5초)
            delay = min(2.0 ** (attempt - 1), _MAX_BACKOFF) + random.uniform(0, 0.5)
            logger.warning(
                "Gemini 일시적 오류(code=%s) → %.1fs 후 재시도 (%d/%d)",
                code, delay, attempt, _MAX_ATTEMPTS,
            )
            await asyncio.sleep(delay)
