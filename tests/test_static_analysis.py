"""정적 분석: 재구성/매핑(순수 로직) + ruff 실제 실행(설치 시) 테스트."""

import shutil
from pathlib import Path

import pytest

from app.review.diff_parser import chunk_and_filter
from app.review.static_analysis import reconstruct_new_content, run_linters

# ── 변경 후 파일 재구성 (순수 로직, ruff 불필요) ──────────────────────────────

def test_reconstruct_excludes_removed_keeps_added():
    patch = "@@ -1,2 +1,2 @@\n import os\n-x = 1\n+y = 2\n"
    recon = reconstruct_new_content(patch)
    assert "x = 1" not in recon.content   # 삭제 줄은 빠짐
    assert "y = 2" in recon.content       # 추가 줄은 남음


def test_reconstruct_maps_real_line_numbers():
    # new 시작이 10인 hunk → 첫 줄은 실제 10번
    patch = "@@ -1,1 +10,2 @@\n context\n+added\n"
    recon = reconstruct_new_content(patch)
    assert recon.line_map == [10, 11]


# ── ruff 실제 실행 (설치돼 있을 때만) ─────────────────────────────────────────

ruff_missing = shutil.which("ruff") is None


@pytest.mark.skipif(ruff_missing, reason="ruff 미설치")
def test_ruff_detects_issues_on_changed_lines():
    diff = Path("samples/lint_demo.py.diff").read_text()
    files = chunk_and_filter(diff)
    findings = run_linters(files)

    assert "utils.py" in findings
    joined = " ".join(findings["utils.py"])
    # == None → E711, 미사용 변수 result → F841 가 변경된 줄에서 잡혀야 함
    assert "E711" in joined
    assert "F841" in joined


@pytest.mark.skipif(ruff_missing, reason="ruff 미설치")
def test_ruff_clean_code_returns_no_findings():
    # 문제 없는 변경
    diff = "@@ -0,0 +1,2 @@\n+import os\n+print(os.getcwd())\n"
    # 단일 파일 패치를 chunk_and_filter가 인식하도록 헤더 부여
    full = "diff --git a/clean.py b/clean.py\n--- a/clean.py\n+++ b/clean.py\n" + diff
    files = chunk_and_filter(full)
    findings = run_linters(files)
    assert "clean.py" not in findings
