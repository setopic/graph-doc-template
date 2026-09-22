"""G022（同じ用語が複数のドメインノードで定義されている）のテスト。

**意図した再掲を鳴らさないこと**が最も大事な性質である。
定義元へリンクしている行は黙り、リンクの無い重複だけが鳴る。
tournament-bot では重複 5 件のうち 3 件がリンクつきの再掲で、鳴るのは 2 件だった。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph.model import Node
from tools.graph.rules import rule_g022_duplicate_terms

from .helpers import make_graph

DOMAIN_DIR = Path("/tmp/g022/docs/20-domain")


def domain(node_id: str, rows: list[tuple[str, str]], node_type: str = "domain") -> Node:
    table = "| 用語 | 意味 | 旧称 |\n| --- | --- | --- |\n" + "".join(
        f"| {term} | {meaning} | — |\n" for term, meaning in rows
    )
    name = f"{node_id.lower()}.md"
    return Node(
        id=node_id,
        type=node_type,
        title=node_id,
        status="stable",
        tags=[],
        path=DOMAIN_DIR / name,
        rel=f"docs/20-domain/{name}",
        meta={},
        body="## 用語\n\n" + table,
        edges=[],
    )


def run(*nodes: Node):
    return rule_g022_duplicate_terms(make_graph(list(nodes)))


class DuplicateTerms(unittest.TestCase):
    def test_same_term_in_two_nodes_without_links_warns(self):
        issues = run(
            domain("DOM-01", [("裁定", "報告が来ない対戦の勝者を決める")]),
            domain("DOM-02", [("裁定", "申請を承認または却下する")]),
        )
        self.assertEqual([i.code for i in issues], ["G022"])
        self.assertIn("DOM-01 / DOM-02", issues[0].message)
        self.assertEqual(issues[0].location, "docs/20-domain/dom-01.md")

    def test_a_restatement_that_links_to_the_owner_is_silent(self):
        """他のノードの語を載せるときは、定義元へリンクすれば鳴らない。"""
        issues = run(
            domain("DOM-01", [("試合形式", "何試合行い、勝者をどう導くか")]),
            domain("DOM-02", [("試合形式", "何試合行うか（[DOM-01](./dom-01.md)）")]),
        )
        self.assertEqual(issues, [])

    def test_a_wikilink_also_counts(self):
        issues = run(
            domain("DOM-01", [("棄権", "対戦を行えなかったこと")]),
            domain("DOM-02", [("棄権", "[[DOM-01]] の呼び名をそのまま使う")]),
        )
        self.assertEqual(issues, [])

    def test_two_restatements_of_one_owner_are_silent(self):
        issues = run(
            domain("DOM-01", [("試合形式", "（[DOM-03](./dom-03.md)）")]),
            domain("DOM-02", [("試合形式", "（[DOM-03](./dom-03.md)）")]),
            domain("DOM-03", [("試合形式", "何試合行い、勝者をどう導くか")]),
        )
        self.assertEqual(issues, [])

    def test_a_link_to_a_node_that_does_not_define_the_term_does_not_count(self):
        """リンクがあっても、指す先が同じ語を定義していなければ定義元ではない。"""
        issues = run(
            domain("DOM-01", [("裁定", "勝者を決める")]),
            domain("DOM-02", [("裁定", "承認する（[DOM-03](./dom-03.md) と同じ立場）")]),
            domain("DOM-03", [("申請", "申し出ること")]),
        )
        self.assertEqual([i.code for i in issues], ["G022"])

    def test_emphasis_does_not_hide_a_duplicate(self):
        issues = run(
            domain("DOM-01", [("**範囲**", "始まりから終わりまで")]),
            domain("DOM-02", [("範囲", "どこまでの対戦に効くか")]),
        )
        self.assertEqual([i.code for i in issues], ["G022"])

    def test_only_domain_nodes_are_compared(self):
        issues = run(
            domain("DOM-01", [("裁定", "勝者を決める")]),
            domain("UC-01", [("裁定", "承認する")], node_type="usecase"),
        )
        self.assertEqual(issues, [])

    def test_one_node_listing_a_term_twice_is_not_a_duplicate(self):
        issues = run(domain("DOM-01", [("範囲", "一戦"), ("範囲", "以降すべて")]))
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
