# 🔌 CodeSage GitHub App 연동 가이드

실제 GitHub 레포에 CodeSage를 붙여 PR 자동 리뷰를 받는 전체 절차.

---

## 0. 사전 준비

```
□ CodeSage 서버가 외부에서 접근 가능한 https URL을 가져야 함
   - 로컬 개발: ngrok로 localhost를 임시 공개 (아래 5번)
   - 운영: ECS/EC2 등에 배포 후 도메인 연결
□ Anthropic API 키 (크레딧 충전된 계정)
```

---

## 1. GitHub App 생성

GitHub → **Settings → Developer settings → GitHub Apps → New GitHub App**

| 항목 | 값 |
|---|---|
| GitHub App name | `CodeSage Reviewer` |
| Homepage URL | 아무 값 (예: 레포 URL) |
| Webhook → Active | ✅ 체크 |
| Webhook URL | `https://<your-server>/webhook` |
| Webhook secret | 긴 랜덤 문자열 (아래 명령으로 생성) |

```bash
# Webhook secret 생성
python -c "import secrets; print(secrets.token_hex(32))"
```

### 권한 (Permissions) — 최소 권한 원칙

| 권한 | 수준 | 이유 |
|---|---|---|
| Pull requests | **Read & write** | diff 읽기 + 코멘트 게시 |
| Contents | **Read-only** | (선택) 전체 파일 fetch로 Linter 정확도↑ |
| Metadata | Read-only | 기본 필수 |

> ⚠️ **코드 push/관리 권한은 절대 주지 않는다.** 리뷰 봇은 코멘트만 달면 된다.

### 이벤트 구독 (Subscribe to events)

```
☑ Pull request
```

생성 후 화면에서 다음 두 가지를 확보:
- **App ID** (숫자)
- **Private key** → `Generate a private key` 클릭 → `.pem` 파일 다운로드

---

## 2. .env 채우기

```bash
ANTHROPIC_API_KEY=sk-ant-...
WEBHOOK_SECRET=<1번에서 만든 secret>
GITHUB_TOKEN=<설치 토큰 또는 PAT — 아래 참고>
```

> **인증 방식 두 가지**
> - **간단(개발용)**: Personal Access Token(PAT)을 `GITHUB_TOKEN`에 넣어 시작.
>   `repo` 또는 fine-grained의 `Pull requests: write` 권한.
> - **정석(운영용)**: GitHub App의 App ID + Private key로 **Installation Access Token**을
>   런타임에 발급(JWT 서명 → 토큰 교환). `github_client.py`에 토큰 발급 로직 추가가
>   다음 확장 작업. (현재 골격은 `GITHUB_TOKEN` 직접 사용 방식)

---

## 3. 서버 실행

```bash
docker compose up -d
curl https://<your-server>/health     # {"status":"ok", ...} 확인
```

---

## 4. 레포에 설치 (Install)

CodeSage App 페이지 → **Install App** → 리뷰받을 레포 선택 → Install.

이제 그 레포에서 PR을 열면:
```
PR opened/synchronize → GitHub가 /webhook 으로 이벤트 전송
  → CodeSage가 리뷰 → PR에 요약 + 인라인 코멘트 게시
```

---

## 5. 로컬에서 진짜 PR 이벤트 받기 (ngrok)

배포 전 로컬에서 실 PR로 테스트하는 방법:

```bash
# 1) 로컬 서버 기동
docker compose up -d

# 2) ngrok로 localhost:8000을 공개 URL로 터널링
ngrok http 8000
#   → https://abc123.ngrok-free.app 같은 주소 발급

# 3) GitHub App의 Webhook URL을 https://abc123.ngrok-free.app/webhook 으로 변경
# 4) 레포에서 PR 생성 → 코멘트가 달리는지 확인
```

---

## 6. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| 401 Invalid signature | `.env`의 `WEBHOOK_SECRET`과 App 설정값 불일치 |
| 코멘트가 안 달림 | `GITHUB_TOKEN` 권한 부족 / 토큰 만료 |
| 인라인 코멘트 422 | 해당 줄이 diff 범위 밖 → CodeSage가 자동으로 로깅 후 스킵 |
| 리뷰가 안 옴 | Webhook 전달 확인: App → Advanced → Recent Deliveries |
| `.env`가 안 읽힘 | OS 환경변수가 같은 이름으로 떠 있으면 그게 우선함 |

---

## 7. 보안 체크리스트

```
□ Webhook 서명(HMAC) 검증 활성 — 가짜 이벤트로 인한 LLM 비용 폭탄 차단
□ GitHub App 최소 권한 (PR read/write + Contents read only)
□ .env, *.pem 파일 git 커밋 금지 (.gitignore 확인)
□ ANTHROPIC_API_KEY / GITHUB_TOKEN 은 Secrets Manager 권장 (운영)
□ Rate limiting (동일 레포 과도 이벤트 방어) — 운영 전 추가 권장
```
