"""
Diff 수집 / 파싱 / 청킹 / 필터링.

LLM에 통째로 던지면 토큰 폭증 + 노이즈가 많으므로,
파일 단위로 쪼개고 리뷰할 가치가 없는 파일은 걸러낸다.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field

from app.core.config import get_policy
from app.integrations.github_client import GitHubClient
from app.models.schemas import ReviewJob

logger = logging.getLogger(__name__)


@dataclass
class FileDiff:
    """한 파일의 변경 묶음."""

    path: str
    patch: str                         # 해당 파일의 diff 텍스트 (@@ ... 포함)
    added_lines: list[int] = field(default_factory=list)  # 변경 후 추가된 줄 번호


def is_incremental(action: str, last_sha: str | None, head_sha: str) -> bool:
    """
    증분 리뷰 조건: 새 커밋 push(synchronize) + 직전에 리뷰한 sha가 있고
    그 sha가 현재 head와 다를 때. (순수 함수 — 단위 테스트 용이)
    """
    return action == "synchronize" and bool(last_sha) and last_sha != head_sha


async def fetch_diff(job: ReviewJob, last_sha: str | None = None) -> str:
    """
    리뷰 대상 diff 원문을 가져온다.
    - local_diff가 있으면 그대로 사용 (로컬 시연 모드)
    - 증분 조건이면 직전 sha...head 사이 diff만 (운영 모드)
    - 아니면 PR 전체 diff (운영 모드)
    """
    if job.local_diff is not None:
        return job.local_diff
    gh = GitHubClient(job.repo, job.installation_id)
    if is_incremental(job.action, last_sha, job.head_sha):
        return await gh.fetch_compare_diff(last_sha, job.head_sha)  # type: ignore[arg-type]
    return await gh.fetch_pr_diff(job.pr_number)


def chunk_and_filter(diff_text: str) -> list[FileDiff]:
    """
    unified diff 문자열을 파일 단위(FileDiff)로 분해하고,
    정책상 무시 대상인 파일을 걸러낸다.
    """
    policy = get_policy().get("review", {})
    ignore_patterns: list[str] = policy.get("ignore", [])

    files = _split_by_file(diff_text)
    result: list[FileDiff] = []
    for fd in files:
        if _is_ignored(fd.path, ignore_patterns):
            logger.debug("무시: %s", fd.path)
            continue
        if not fd.added_lines:
            continue  # 추가/변경된 줄이 없으면(순수 삭제 등) 스킵
        result.append(fd)
    return result


def _split_by_file(diff_text: str) -> list[FileDiff]:
    """unified diff를 'diff --git' 경계로 잘라 파일별 FileDiff 생성."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_line_no = 0

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current is not None:
                files.append(current)
            current = None
        elif line.startswith("+++ b/"):
            path = line[len("+++ b/"):].strip()
            current = FileDiff(path=path, patch="")
        elif line.startswith("@@"):
            # @@ -a,b +c,d @@  → c가 변경 후 시작 줄 번호
            new_line_no = _parse_hunk_start(line)
            if current:
                current.patch += line + "\n"
        elif current is not None:
            current.patch += line + "\n"
            if line.startswith("+") and not line.startswith("+++"):
                current.added_lines.append(new_line_no)
                new_line_no += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass  # 삭제 줄은 변경 후 줄 번호를 증가시키지 않음
            else:
                new_line_no += 1  # context 줄

    if current is not None:
        files.append(current)
    return files


def _parse_hunk_start(hunk_header: str) -> int:
    """'@@ -1,4 +10,6 @@' 에서 변경 후 시작 줄(10)을 추출."""
    try:
        plus_part = hunk_header.split("+")[1]
        return int(plus_part.split(",")[0].split(" ")[0])
    except (IndexError, ValueError):
        return 1


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """glob 패턴 중 하나라도 매칭되면 무시."""
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)
