"""G019（Markdown の表が途中で切れている）のテスト。

**グラフの検査は通るのに、GitHub 上の表示だけが壊れる**という種類の問題である。
実際に 2 件見つかった。README のコマンド表（段落を挿し込んで 14 行が流れた）と、
ドメインノードの用語表（段落 3 つを挟んで 1 行が取り残された）。

どちらも `check` は通っていた。`G013` の用語表パーサは行ベースなので、
取り残された行すら拾えている。**機械は困らず、読む人だけが困る。**

**誤検出を出さないことが最も大事。** ERROR なので、外すと派生プロジェクトの
CI が一斉に落ちる。実データ 435 ファイルに当てて、本物 2 件・誤検出 0 件を
確かめたうえで入れた。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph.loader import load
from tools.graph.model import ERROR
from tools.graph.rules import find_broken_tables, rule_g019_broken_tables

from tests.test_strict_mode import build_docs

GOOD_TABLE = """# 題

| 用語 | 意味 |
| --- | --- |
| 形式 | 対戦の組み方 |
| 進行中 | 結果を入れている状態 |
"""


class FindBrokenTablesTest(unittest.TestCase):
    def lines(self, text: str) -> list[int]:
        return [lineno for lineno, _ in find_broken_tables(text)]

    def test_intact_table_is_clean(self) -> None:
        self.assertEqual(self.lines(GOOD_TABLE), [])

    def test_paragraph_inside_table(self) -> None:
        """README で実際に起きた形。段落の後ろの行が表から外れる。"""
        text = (
            "| a | b |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
            "\n"
            "ここに段落を書いてしまった。\n"
            "| 3 | 4 |\n"
        )
        self.assertEqual(self.lines(text), [6])

    def test_blank_line_inside_table(self) -> None:
        """空行でも表は終わる。**段落が無くても壊れる。**"""
        text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n| 3 | 4 |\n"
        self.assertEqual(self.lines(text), [5])

    def test_two_tables_separated_by_paragraph_are_fine(self) -> None:
        """段落を挟んだ 2 つの表は正しい。**2 つ目にヘッダと区切りがある。**"""
        text = (
            "| a | b |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
            "\n"
            "説明の段落。\n"
            "\n"
            "| c | d |\n"
            "| --- | --- |\n"
            "| 3 | 4 |\n"
        )
        self.assertEqual(self.lines(text), [])

    def test_table_example_in_code_block_is_ignored(self) -> None:
        """規約文書は表の書き方をコードブロックで例示する。そこは数えない。"""
        text = "本文。\n\n```markdown\n| a | b |\n| --- | --- |\n```\n"
        self.assertEqual(self.lines(text), [])

    def test_broken_example_in_code_block_is_ignored(self) -> None:
        """**壊れた表を例として載せても落ちない。**

        この規約自身が `graph-rules.md` に悪い例を書くので、
        ここが効かないと自分の文書で落ちる。
        """
        text = "悪い例:\n\n```markdown\n説明。\n| 3 | 4 |\n```\n"
        self.assertEqual(self.lines(text), [])

    def test_tilde_fence_is_ignored(self) -> None:
        text = "本文。\n\n~~~\n説明。\n| 3 | 4 |\n~~~\n"
        self.assertEqual(self.lines(text), [])

    def test_lone_row_without_separator(self) -> None:
        """区切り行が無い表は、そもそも表として描画されない。"""
        text = "本文。\n\n| a | b |\n| 1 | 2 |\n"
        self.assertEqual(self.lines(text), [3])

    def test_reports_the_line_content(self) -> None:
        text = "段落。\n| 終了 | 全対戦が確定した |\n"
        found = find_broken_tables(text)
        self.assertEqual(len(found), 1)
        self.assertIn("終了", found[0][1])

    def test_indented_row_is_still_a_row(self) -> None:
        """リストの中の表もある。字下げされていても見る。"""
        text = "説明。\n  | a | b |\n"
        self.assertEqual(self.lines(text), [2])


class RuleG019Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        build_docs(self.tmp)

    def run_rule(self):
        return rule_g019_broken_tables(load(self.tmp))

    def test_clean_repository_passes(self) -> None:
        self.assertEqual(self.run_rule(), [])

    def test_broken_table_in_a_node_is_an_error(self) -> None:
        path = self.tmp / "docs" / "20-domain" / "dom-01-booking.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n段落。\n| 終了 | 説明 |\n",
            encoding="utf-8",
            newline="\n",
        )
        issues = self.run_rule()
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G019")
        self.assertEqual(issues[0].severity, ERROR)
        self.assertIn("dom-01-booking.md", issues[0].location)

    def test_readme_is_scanned_too(self) -> None:
        """**実際に壊れていたのは README だった。** グラフの外も見る。"""
        (self.tmp / "README.md").write_text(
            "# 題\n\n段落。\n| a | b |\n", encoding="utf-8", newline="\n"
        )
        issues = self.run_rule()
        self.assertEqual([i.location for i in issues], ["README.md"])

    def test_root_markdown_other_than_readme_is_scanned(self) -> None:
        (self.tmp / "CONTRIBUTING.md").write_text(
            "# 題\n\n段落。\n| a | b |\n", encoding="utf-8", newline="\n"
        )
        self.assertEqual(
            [i.location for i in self.run_rule()], ["CONTRIBUTING.md"]
        )


if __name__ == "__main__":
    unittest.main()
