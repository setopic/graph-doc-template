"""CIがPRでもmainと同じ判定をしているかのテスト。

**PRが緑なら、マージした後のmainも緑であること**が最も大事な性質である。
PRだけ`--strict`を外していた頃、tournament-botでPRが緑のままmainが落ち、
3回続けてマージして約10時間気づかなかった（graph-doc-template#6）。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "graph-check.yml"


def branch(text: str, condition: str) -> str:
    """`if` / `elif`の1つの分岐の中身を返す。"""
    start = text.index(condition)
    rest = text[start + len(condition):]
    end = re.search(r"^\s*(elif|else|fi)\b", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


class StrictOnPullRequest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_pull_requests_run_strict_without_the_change_window(self):
        """`--since`を付けない`--strict`なら、G015 / G017でPRを落とさない。"""
        body = branch(self.text, '"pull_request" ]; then')
        strict = [line for line in body.splitlines() if "check --strict" in line]
        self.assertTrue(strict, "PRの分岐にcheck --strictが無い")
        self.assertTrue(all("--since" not in line for line in strict))

    def test_pull_requests_still_list_unfollowed_changes(self):
        body = branch(self.text, '"pull_request" ]; then')
        self.assertIn("check --since", body)

    def test_main_runs_strict(self):
        body = branch(self.text, '"push" ]; then')
        self.assertIn("check --strict", body)


if __name__ == "__main__":
    unittest.main()
