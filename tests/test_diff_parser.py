"""diff 파싱/필터링 단위 테스트."""

from app.review.diff_parser import chunk_and_filter

SAMPLE_DIFF = """diff --git a/auth.py b/auth.py
--- a/auth.py
+++ b/auth.py
@@ -1,2 +1,4 @@
 import jwt
+SECRET = "x"
+def login():
     pass
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,1 +1,2 @@
+  "noise": true
"""


def test_splits_by_file_and_filters_lock():
    files = chunk_and_filter(SAMPLE_DIFF)
    paths = [f.path for f in files]
    # auth.py는 남고, *.lock 패턴(package-lock.json)은 ignore 정책에 따라 제외
    assert "auth.py" in paths
    assert "package-lock.json" not in paths


def test_tracks_added_line_numbers():
    files = chunk_and_filter(SAMPLE_DIFF)
    auth = next(f for f in files if f.path == "auth.py")
    # @@ +1,4 → 추가 줄(SECRET, def login)이 2번/3번 줄로 잡혀야 함
    assert 2 in auth.added_lines
    assert 3 in auth.added_lines


def test_empty_diff_returns_empty():
    assert chunk_and_filter("") == []
