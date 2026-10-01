"""コードスパンの判定のテスト（setopic/graph-doc-template#24）。

コードスパンは、開きと同じ数のバッククォートで閉じる（CommonMark）。
バッククォート1つだけを数える判定だと、`` ` `` のようにバッククォートを含む
コードスパンの後ろで組み合わせがずれ、同じ行のコードの中と外が入れ替わる。

判定は2か所で使っている。リンクを数える`strip_non_prose`（loader）と、
書き換えない範囲を決める`_apply_outside_protected`（rename・linkify）である。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.linkify import linkify
from tools.graph.loader import WIKILINK_RE, load, strip_non_prose
from tools.graph.rename import _apply_outside_protected

from .test_strict_mode import build_docs

USECASE_PATH = "docs/30-usecases/uc-01-confirm-booking.md"

# #17 で G004 を出した行と同じ形
DOUBLE_BACKTICK_LINE = "コードスパン（`` ` ``で囲んだ範囲）の中にある`[[ID]]`は数えない。"


def links(text: str) -> list[str]:
    return WIKILINK_RE.findall(strip_non_prose(text))


class StripNonProseTest(unittest.TestCase):
    def test_code_after_double_backtick_span_is_not_a_link(self) -> None:
        self.assertEqual(links(DOUBLE_BACKTICK_LINE), [])

    def test_link_between_code_spans_is_kept(self) -> None:
        self.assertEqual(links("`a` [[UC-01]] `b`"), ["UC-01"])

    def test_link_after_double_backtick_span_is_kept(self) -> None:
        self.assertEqual(links("`` ` ``の後ろの[[UC-01]]"), ["UC-01"])

    def test_span_may_contain_single_backticks(self) -> None:
        self.assertEqual(links("``[[UC-01]] と `x` を書く``"), [])

    def test_unclosed_backtick_is_plain_text(self) -> None:
        """閉じていないバッククォートは、ただの文字として扱う（CommonMark と同じ）。"""
        self.assertEqual(links("`の後ろの[[UC-01]]"), ["UC-01"])

    def test_span_does_not_cross_lines(self) -> None:
        self.assertEqual(links("`開き\n[[UC-01]]\n閉じ`"), ["UC-01"])


class ApplyOutsideProtectedTest(unittest.TestCase):
    def test_transform_skips_code_after_double_backtick_span(self) -> None:
        result = _apply_outside_protected(DOUBLE_BACKTICK_LINE, lambda s: s.replace("ID", "XX"))
        self.assertEqual(result, DOUBLE_BACKTICK_LINE)

    def test_transform_reaches_text_between_spans(self) -> None:
        result = _apply_outside_protected("`` ` `` ID `ID`", lambda s: s.replace("ID", "XX"))
        self.assertEqual(result, "`` ` `` XX `ID`")


class LinkifyWithDoubleBacktickTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)

    def body(self, rel: str) -> str:
        return (self.tmp / rel).read_text(encoding="utf-8")

    def test_does_not_rewrite_code_after_double_backtick_span(self) -> None:
        path = self.tmp / USECASE_PATH
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n`` ` ``で囲む例として`[[DOM-01]]`と書き、本文では[[DOM-01]]を指す。\n",
            encoding="utf-8",
        )
        linkify(load(self.tmp), self.tmp, self.tmp / schema.DOCS_DIR)
        text = self.body(USECASE_PATH)
        self.assertIn("`[[DOM-01]]`", text)
        self.assertIn("本文では[DOM-01](../20-domain/dom-01-booking.md)を指す", text)


if __name__ == "__main__":
    unittest.main()
