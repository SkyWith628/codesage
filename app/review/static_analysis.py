"""
정적 분석(Linter) 어댑터.

"미사용 import, == None, 미사용 변수" 같은 기계적 이슈는 Linter가 0원에 정확히 잡는다.
LLM에게는 맥락적 판단만 맡기기 위한 1차 필터.

핵심 난제: Linter는 '파일 전체'가 필요한데 우리에겐 'diff'만 있다.
해결: 패치에서 '변경 후 파일'을 재구성해 Linter에 투입하고,
      결과 줄번호를 실제 new파일 줄번호로 매핑한 뒤 '변경된 줄'의 이슈만 채택한다.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass

from app.review.diff_parser import FileDiff, _parse_hunk_start

logger = logging.getLogger(__name__)

# (실제 줄번호, 규칙코드, 메시지)
Finding = tuple[int, str, str]


# ─────────────────────────────────────────────────────────────────────────────
# Linter 어댑터
# ─────────────────────────────────────────────────────────────────────────────


class _Linter:
    """언어별 Linter 어댑터의 공통 인터페이스."""

    language = ""

    def is_available(self) -> bool:
        raise NotImplementedError

    def lint(self, path: str, content: str) -> list[Finding]:
        raise NotImplementedError


class RuffLinter(_Linter):
    """Python 정적 분석기 ruff 어댑터 (stdin으로 코드 전달)."""

    language = "python"

    def is_available(self) -> bool:
        return shutil.which("ruff") is not None

    def lint(self, path: str, content: str) -> list[Finding]:
        try:
            proc = subprocess.run(
                ["ruff", "check", "--output-format=json", "--stdin-filename", path, "-"],
                input=content,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("ruff 실행 실패: %s", exc)
            return []

        out = proc.stdout.strip()
        if not out:
            return []
        try:
            items = json.loads(out)
        except json.JSONDecodeError:
            logger.warning("ruff 출력 파싱 실패: %s", proc.stderr[:200])
            return []

        findings: list[Finding] = []
        for it in items:
            loc = it.get("location") or {}
            row = loc.get("row")
            if row:
                findings.append((int(row), it.get("code") or "", it.get("message") or ""))
        return findings


class EslintLinter(_Linter):
    """JS/TS 정적 분석기 eslint 어댑터. 미설치 시 자동 비활성화."""

    language = "javascript"

    def is_available(self) -> bool:
        return shutil.which("eslint") is not None

    def lint(self, path: str, content: str) -> list[Finding]:
        try:
            proc = subprocess.run(
                ["eslint", "--format", "json", "--stdin", "--stdin-filename", path],
                input=content,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("eslint 실행 실패: %s", exc)
            return []

        out = proc.stdout.strip()
        if not out:
            return []
        try:
            report = json.loads(out)  # [{ messages: [{line, ruleId, message}] }]
        except json.JSONDecodeError:
            return []

        findings: list[Finding] = []
        for file_report in report:
            for m in file_report.get("messages", []):
                line = m.get("line")
                if line:
                    findings.append((int(line), m.get("ruleId") or "", m.get("message") or ""))
        return findings


# 어댑터 싱글턴 (확장자 → Linter)
_RUFF = RuffLinter()
_ESLINT = EslintLinter()


def _select_linter(path: str) -> _Linter | None:
    if path.endswith(".py"):
        return _RUFF
    if path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return _ESLINT
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 변경 후 파일 재구성 + 줄번호 매핑
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Reconstructed:
    """패치로부터 복원한 '변경 후' 코드와 줄번호 매핑."""

    content: str
    # line_map[i] = 재구성 본문 i번째 줄의 '실제 new파일' 줄번호
    line_map: list[int]


def reconstruct_new_content(patch: str) -> Reconstructed:
    """
    unified diff 패치에서 '변경 후' 코드를 복원한다.
    - context(' ')/추가('+') 줄은 살리고 삭제('-') 줄은 버린다.
    - 동시에 각 줄의 실제 new파일 줄번호를 기록(diff_parser와 동일한 계산).
    """
    out_lines: list[str] = []
    line_map: list[int] = []
    new_no = 0

    for line in patch.splitlines():
        if line.startswith("@@"):
            new_no = _parse_hunk_start(line)
            continue
        if line == "":  # 빈 context 줄
            out_lines.append("")
            line_map.append(new_no)
            new_no += 1
            continue

        tag, text = line[0], line[1:]
        if tag == "+":
            out_lines.append(text)
            line_map.append(new_no)
            new_no += 1
        elif tag == " ":
            out_lines.append(text)
            line_map.append(new_no)
            new_no += 1
        elif tag == "-":
            continue  # 삭제 줄: 새 파일엔 없음
        else:
            continue  # '\ No newline at end of file' 등

    return Reconstructed("\n".join(out_lines) + "\n", line_map)


# ─────────────────────────────────────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────────────────────────────────────


def run_linters(files: list[FileDiff]) -> dict[str, list[str]]:
    """
    파일별 정적 분석 결과를 반환한다. { 파일경로: ["L8: E711 ...", ...] }
    변경된 줄(added_lines)의 이슈만 채택해 기존 코드의 잡음을 제거한다.
    """
    results: dict[str, list[str]] = {}

    for fd in files:
        linter = _select_linter(fd.path)
        if linter is None or not linter.is_available():
            continue

        recon = reconstruct_new_content(fd.patch)
        if not recon.content.strip():
            continue

        raw = linter.lint(fd.path, recon.content)
        added = set(fd.added_lines)
        msgs: list[str] = []
        for recon_line, code, message in raw:
            # 재구성 줄번호 → 실제 new파일 줄번호
            if not (1 <= recon_line <= len(recon.line_map)):
                continue
            real_line = recon.line_map[recon_line - 1]
            # 변경된 줄의 이슈만 보고
            if added and real_line not in added:
                continue
            msgs.append(f"L{real_line}: {code} {message}".rstrip())

        if msgs:
            results[fd.path] = msgs

    return results
