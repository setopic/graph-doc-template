"""G023（契約が「対応」に挙げたユースケースを depends_on に書いていない）のテスト。

**読む場所を絞ること**が最も大事な性質である。見出しが「対応」で始まる列と
「対応するユースケース:」の行だけを読み、本文の道案内のリンクは読まない
（読むと tournament-bot だけで 29 件当たった）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph.model import Edge, Node
from tools.graph.rules import rule_g023_contract_use_cases

from .helpers import make_graph

DOCS = Path("/tmp/g023/docs")


def make(node_id: str, node_type: str, rel_dir: str, body: str = "", deps: tuple[str, ...] = ()) -> Node:
    name = f"{node_id.lower()}.md"
    node = Node(
        id=node_id,
        type=node_type,
        title=node_id,
        status="stable",
        tags=[],
        path=DOCS / rel_dir / name,
        rel=f"docs/{rel_dir}/{name}",
        meta={},
        body=body,
        edges=[],
    )
    for dep in deps:
        node.edges.append(Edge(src=node_id, dst=dep, kind="depends_on", origin="frontmatter"))
    return node


def usecase(node_id: str) -> Node:
    return make(node_id, "usecase", "30-usecases")


def contract(body: str, deps: tuple[str, ...] = ()) -> Node:
    return make("CON-01", "contract", "40-contracts", body, deps)


INTERACTION = (
    "| 種別 | 識別子 | 実行できる人 | 対応 |\n"
    "| --- | --- | --- | --- |\n"
    "| コマンド | `/entry` | 選手 | [UC-01](../30-usecases/uc-01.md) |\n"
    "| ボタン | `retire` | 代表 | [UC-02](../30-usecases/uc-02.md) |\n"
)


def run(*nodes: Node):
    return rule_g023_contract_use_cases(make_graph(list(nodes)))


class ContractUseCases(unittest.TestCase):
    def test_a_use_case_in_the_column_but_not_in_depends_on_warns(self):
        issues = run(contract(INTERACTION, deps=("UC-01",)), usecase("UC-01"), usecase("UC-02"))
        self.assertEqual([i.code for i in issues], ["G023"])
        self.assertIn("UC-02", issues[0].message)
        self.assertNotIn("UC-01", issues[0].message)

    def test_everything_in_depends_on_is_silent(self):
        self.assertEqual(run(contract(INTERACTION, deps=("UC-01", "UC-02")), usecase("UC-01"), usecase("UC-02")), [])

    def test_the_exception_flow_column_is_read(self):
        body = (
            "| 状況 | 返すもの | 誰に見えるか | 対応する例外フロー |\n"
            "| --- | --- | --- | --- |\n"
            "| 認証が無効 | 401 | 担当者 | [UC-03](../30-usecases/uc-03.md) E1 |\n"
        )
        issues = run(contract(body), usecase("UC-03"))
        self.assertEqual([i.code for i in issues], ["G023"])

    def test_the_http_line_is_read(self):
        body = "対応するユースケース: [UC-01](../30-usecases/uc-01.md)\n"
        self.assertEqual([i.code for i in run(contract(body), usecase("UC-01"))], ["G023"])

    def test_a_borrowed_behaviour_counts(self):
        """「UC-25 と同じ」も前提として数える（借りている UC が仕様そのもの）。"""
        body = (
            "| 種別 | 識別子 | 置き場所 | 実行できる人 | 対応 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| ボタン | `code` | スレッド | 選手 | [UC-25](../30-usecases/uc-25.md) と同じ |\n"
        )
        self.assertEqual([i.code for i in run(contract(body), usecase("UC-25"))], ["G023"])

    def test_the_template_guidance_in_a_comment_is_ignored(self):
        body = "対応するユースケース: <!-- depends_on に書いた UC への [[UC-01]] -->\n"
        self.assertEqual(run(contract(body), usecase("UC-01")), [])

    def test_links_elsewhere_in_the_body_are_ignored(self):
        """本文の道案内は数えない。"""
        body = "入口は [UC-01](../30-usecases/uc-01.md) と同じ形である。\n\n" + INTERACTION.replace(
            "[UC-02](../30-usecases/uc-02.md)", "[UC-01](../30-usecases/uc-01.md)"
        )
        body += "\n| 引数 | 説明 |\n| --- | --- |\n| `match` | [UC-02](../30-usecases/uc-02.md) のとき必須 |\n"
        self.assertEqual(run(contract(body, deps=("UC-01",)), usecase("UC-01"), usecase("UC-02")), [])

    def test_only_use_cases_are_expected(self):
        """「対応」の列に ADR やドメインのリンクがあっても、依存は求めない。"""
        body = (
            "| 種別 | 識別子 | 実行できる人 | 対応 |\n"
            "| --- | --- | --- | --- |\n"
            "| ボタン | `x` | 選手 | [UC-01](../30-usecases/uc-01.md)（[ADR-0001](../50-adr/adr-0001.md)） |\n"
        )
        adr = make("ADR-0001", "adr", "50-adr")
        self.assertEqual(run(contract(body, deps=("UC-01",)), usecase("UC-01"), adr), [])

    def test_only_contracts_are_checked(self):
        node = make("UC-09", "usecase", "30-usecases", INTERACTION)
        self.assertEqual(run(node, usecase("UC-01"), usecase("UC-02")), [])


if __name__ == "__main__":
    unittest.main()
