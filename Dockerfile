# ===== CodeSage 멀티스테이지 빌드 =====
# 빌드 단계와 실행 단계를 분리해 최종 이미지 크기를 줄인다.

# --- 1단계: 의존성 빌드 ---
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
# wheel로 미리 빌드해 실행 이미지로 복사 (컴파일 도구를 최종 이미지에서 제외)
RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# --- 2단계: 실행 이미지 ---
FROM python:3.12-slim

# 보안: root가 아닌 전용 유저로 실행
RUN useradd --create-home --uid 1000 codesage

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# --chown으로 복사본을 codesage 소유로 만든다.
# (원본 파일이 소유자 전용 권한이어도 비루트 유저가 읽을 수 있게 보장)
COPY --chown=codesage:codesage app ./app
COPY --chown=codesage:codesage config ./config
COPY --chown=codesage:codesage scripts ./scripts

USER codesage

# 기본 커맨드는 API 서버. worker는 docker-compose에서 command로 덮어쓴다.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
