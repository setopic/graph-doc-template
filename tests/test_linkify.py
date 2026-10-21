"""linkify（本文の[[ID]]を相対リンクに直す）のテスト。

**グラフを変えないこと**が最も大事な性質である。loaderは`[[ID]]`と
相対リンクの両方を同じ`mentions`として拾うので、書き換えても
参照の集合は一致していなければならない。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.linkify import linkify
from tools.graph.loader import load

from tests.test_strict_mode import build_docs

USECASE_PATH = "docs/30-usecases/uc-01-confirm-booking.md"


class LinkifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)

    def _run(self, **kwargs) -> list[str]:
        return linkify(load(self.tmp), self.tmp, self.tmp / schema.DOCS_DIR, **kwargs)

    def append(self, rel: str, text: str) -> None:
        path = self.tmp / rel
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")

    def body(self, rel: str) -> str:
        return (self.tmp / rel).read_text(encoding="utf-8")

    def test_rewrites_wikilink_to_relative_link(self) -> None:
        self.append(USECASE_PATH, "\n本文から [[DOM-01]] を参照する。\n")
        changed = self._run()
        self.assertIn(USECASE_PATH, changed)
        self.assertIn(
            "[DOM-01](../20-domain/dom-01-booking.md)",
            self.body(USECASE_PATH),
        )
        self.assertNotIn("[[DOM-01]]", self.body(USECASE_PATH))

    def test_keeps_display_label(self) -> None:
        self.append(USECASE_PATH, "\n[[DOM-01|予約という概念]] を見る。\n")
        self._run()
        self.assertIn(
            "[予約という概念](../20-domain/dom-01-booking.md)",
            self.body(USECASE_PATH),
        )

    def test_does_not_touch_code(self) -> None:
        """**規約や雛形に載せた「書き方の例」を壊さない。**"""
        self.append(
            USECASE_PATH,
            "\n書き方の例:\n\n```markdown\n- [[DOM-01]] と書く\n```\n\n"
            "インラインの `[[DOM-01]]` も同じ。\n",
        )
        self._run()
        text = self.body(USECASE_PATH)
        self.assertIn("- [[DOM-01]] と書く", text)
        self.assertIn("`[[DOM-01]]`", text)

    def test_unknown_id_is_left_alone(self) -> None:
        """存在しないidは残す。消すとG004の検査をすり抜ける。"""
        self.append(USECASE_PATH, "\n[[ARCH-99]] は存在しない。\n")
        self._run()
        self.assertIn("[[ARCH-99]]", self.body(USECASE_PATH))

    def test_idempotent(self) -> None:
        self.append(USECASE_PATH, "\n[[DOM-01]] を参照する。\n")
        self._run()
        self.assertEqual(self._run(), [], "2回目は書き換えが起きないはず")

    def test_dry_run_does_not_write(self) -> None:
        self.append(USECASE_PATH, "\n[[DOM-01]] を参照する。\n")
        before = self.body(USECASE_PATH)
        changed = self._run(dry_run=True)
        self.assertIn(USECASE_PATH, changed)
        self.assertEqual(self.body(USECASE_PATH), before)

    def test_graph_is_unchanged(self) -> None:
        """**これがlinkifyを入れられる根拠。** 参照の集合が変わらない。"""
        self.append(USECASE_PATH, "\n[[DOM-01]] を参照する。\n")

        def mentions(graph) -> set[tuple[str, str]]:
            return {
                (edge.src, edge.dst)
                for node in graph.nodes.values()
                for edge in node.edges
                if edge.kind == schema.BODY_EDGE_KIND and edge.resolved
            }

        before = mentions(load(self.tmp))
        self._run()
        self.assertEqual(mentions(load(self.tmp)), before)

    def test_scans_root_markdown_too(self) -> None:
        """READMEのようにグラフ外のファイルも直す。"""
        readme = self.tmp / "README.md"
        readme.write_text("# 題\n\n[[DOM-01]] を見る。\n", encoding="utf-8")
        changed = self._run()
        self.assertIn("README.md", changed)
        # 下向きの相対パスには ./が付く（renameが張り替えるときと同じ形）
        self.assertIn(
            "[DOM-01](./docs/20-domain/dom-01-booking.md)",
            readme.read_text(encoding="utf-8"),
        )

    def test_writes_lf_even_on_windows(self) -> None:
        """書き戻しでCRLFに化けない。**バイトで見る。**

        テキストとして読み直すとPythonが改行を正規化してしまい、
        CRLFになっていても気付けない。gitも`text=auto eol=lf`で
        コミット時に直すので`git status`にも出ない。
        """
        path = self.tmp / USECASE_PATH
        path.write_bytes(b"# uc\n\n[[DOM-01]] \xe3\x82\x92\xe8\xa6\x8b\xe3\x82\x8b\xe3\x80\x82\n")
        self._run()
        self.assertNotIn(b"\r\n", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
