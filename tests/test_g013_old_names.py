"""G013（依存先の用語表が使わない語）のテスト。

**1.19 までの列名も読み続けること**が最も大事な性質である。
見出しが合わない表は用語表として読まないので、読むのをやめると、
取り込んだ派生で G013 が黙って止まる（34 枚の表がこの列名だった）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph.model import Edge, Node
from tools.graph.rules import forbidden_terms, rule_g013_term_consistency, term_rows

from .helpers import make_graph


def make(node_id: str, node_type: str, body: str) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        title=node_id,
        status="stable",
        tags=[],
        path=Path(f"/tmp/g013/{node_id}.md"),
        rel=f"docs/{node_id}.md",
        meta={},
        body=body,
        edges=[],
    )


def owner(header: str, row: str) -> Node:
    return make("DOM-01", "domain", f"## 用語\n\n{header}\n| --- | --- | --- |\n{row}\n")


def dependent(body: str) -> Node:
    child = make("UC-01", "usecase", body)
    child.edges.append(Edge(src="UC-01", dst="DOM-01", kind="depends_on", origin="frontmatter"))
    return child


class OldNames(unittest.TestCase):
    def test_an_old_name_is_reported_in_a_dependent(self):
        graph = make_graph(
            [
                owner("| 用語 | 意味 | 旧称 |", "| 得点 | 取ったゴール数 | スコア（文字列だった頃の名前） |"),
                dependent("## 概要\n\nスコアを記録する。\n"),
            ]
        )
        issues = rule_g013_term_consistency(graph)
        self.assertEqual([i.code for i in issues], ["G013"])
        self.assertIn("'得点' を使ってください", issues[0].message)
        self.assertIn("文字列だった頃の名前", issues[0].message)

    def test_the_legacy_column_is_still_read(self):
        """1.19 までの「使ってはいけない言い換え」の表も、取り込んだ後に検査が止まらない。"""
        graph = make_graph(
            [
                owner("| 用語 | 意味 | 使ってはいけない言い換え |", "| エントリー | 出る意思 | 参加 |"),
                dependent("## 概要\n\n参加を受け付ける。\n"),
            ]
        )
        self.assertEqual([i.code for i in rule_g013_term_consistency(graph)], ["G013"])

    def test_both_columns_are_read_when_a_table_has_both(self):
        body = (
            "## 用語\n\n| 用語 | 意味 | 旧称 | 使ってはいけない言い換え |\n"
            "| --- | --- | --- | --- |\n| 得点 | ゴール数 | スコア | 点数 |\n"
        )
        self.assertEqual(sorted(forbidden_terms(body)), ["スコア", "点数"])

    def test_a_table_without_the_column_checks_nothing_but_is_still_a_term_table(self):
        body = "## 用語\n\n| 用語 | 意味 |\n| --- | --- |\n| 範囲 | 始まりから終わりまで |\n"
        self.assertEqual(forbidden_terms(body), {})
        self.assertEqual(term_rows(body), [{"用語": "範囲", "意味": "始まりから終わりまで"}])

    def test_placeholder_rows_are_not_terms(self):
        """雛形の空行を用語として数えない。"""
        body = "## 用語\n\n| 用語 | 意味 | 旧称 |\n| --- | --- | --- |\n|  |  |  |\n"
        self.assertEqual(term_rows(body), [])


if __name__ == "__main__":
    unittest.main()
