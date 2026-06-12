"""llm_reviewer의 프롬프트 구성 / JSON 파싱 단위 테스트 (API 키 불필요)."""

from app.review.diff_parser import FileDiff
from app.review.llm_reviewer import (
    _build_prompt,
    _build_system_prompt,
    _extract_json,
    _mock_review,
    _parse_review,
)
from app.models.schemas import Severity

# ── JSON 추출 ────────────────────────────────────────────────────────────────

VALID = '{"summary": "s", "comments": []}'


def test_extract_plain_json():
    assert _extract_json(VALID) == VALID


def test_extract_from_code_fence():
    fenced = f"여기 결과입니다:\n```json\n{VALID}\n```\n끝."
    assert _extract_json(fenced).strip() == VALID


def test_extract_strips_surrounding_prose():
    noisy = f"리뷰: {VALID} (이상입니다)"
    assert _extract_json(noisy) == VALID


# ── 응답 파싱 (방어적) ────────────────────────────────────────────────────────

def test_parse_valid_review():
    text = """{"summary": "보안 이슈 발견",
      "comments": [{"file_path": "auth.py", "line_number": 8,
        "severity": "critical", "category": "security",
        "body": "SQL Injection 위험", "suggested_code": null}]}"""
    result = _parse_review(text)
    assert result.summary == "보안 이슈 발견"
    assert len(result.comments) == 1
    assert result.comments[0].severity == Severity.critical


def test_parse_malformed_json_returns_safe_empty():
    result = _parse_review("이건 JSON이 아님 {깨짐")
    assert result.comments == []


def test_parse_skips_bad_comment_keeps_good():
    text = """{"summary": "혼합", "comments": [
      {"file_path": "a.py", "line_number": 1, "severity": "WRONG",
       "category": "bug", "body": "잘못된 severity"},
      {"file_path": "b.py", "line_number": 2, "severity": "warning",
       "category": "bug", "body": "정상"}]}"""
    result = _parse_review(text)
    # 잘못된 severity 1건은 스킵, 정상 1건은 유지
    assert len(result.comments) == 1
    assert result.comments[0].file_path == "b.py"


# ── 프롬프트 구성 ─────────────────────────────────────────────────────────────

def test_build_prompt_isolates_diff_for_injection_defense():
    files = [FileDiff(path="x.py", patch="+evil", added_lines=[1])]
    prompt = _build_prompt(files, {}, context="")
    # diff가 신뢰 불가 데이터로 격리되어야 함
    assert "<untrusted_code>" in prompt
    assert "</untrusted_code>" in prompt
    assert "x.py" in prompt


def test_build_prompt_includes_linter_findings():
    files = [FileDiff(path="x.py", patch="+a", added_lines=[1])]
    prompt = _build_prompt(files, {"x.py": ["unused import"]}, context="")
    assert "Linter" in prompt
    assert "unused import" in prompt


def test_system_prompt_has_rubric_focus_and_guard():
    sp = _build_system_prompt(["security", "bug"])
    assert "security, bug" in sp          # focus 반영
    assert "critical" in sp               # 루브릭 포함
    assert "untrusted_code" in sp         # 인젝션 방어 규칙


# ── Mock ─────────────────────────────────────────────────────────────────────

def test_mock_review_marked_as_mock():
    files = [FileDiff(path="x.py", patch="+a", added_lines=[5])]
    result = _mock_review(files)
    assert result.model_used == "mock"
    assert result.comments[0].line_number == 5
