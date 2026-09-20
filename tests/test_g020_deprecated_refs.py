"""G020（取り下げた決定を現在の根拠として引いている）のテスト。

**問題は「参照していること」ではなく「現在の根拠として引いていること」である。**
歴史として引くのは正当なので、`G019` と違ってエラーにはできない。
`G009`〜`G015` と同じ警告にして、承知のうえで放置できる形にする。

**黙る条件を実データで決めた。** 7 リポジトリに当てて、

- 段落の中で置き換え先も指していれば黙る → 44 ノード
- 文書のどこかで指していれば黙る → 28 ノード。**本物を 1 件取りこぼした**
- ADR をまるごと除外 → 31 ノード。**本物を 3 件とも取りこぼした**

段落に絞った案だけが、断って引いている 3 件を黙らせたうえで、
理由の節で古い決定を引いている 3 件を残せた。ここはその判定を固定する。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph.loader import load
from tools.graph.model import WARN, Node
from tools.graph.rules import (
    rule_g020_deprecated_references,
    superseded_index,
    unacknowledged_citations,
)

from .helpers import make_graph


def node(
    node_id: str,
    *,
    type_: str = "usecase",
    status: str = "stable",
    body: str = "",
    supersedes: list[str] | None = None,
) -> Node:
    meta = {"id": node_id, "type": type_, "title": node_id, "status": status}
    if supersedes is not None:
        meta["supersedes"] = supersedes
    return Node(
        id=node_id,
        type=type_,
        title=node_id,
        status=status,
        tags=[],
        path=Path(f"docs/{node_id}.md"),
        rel=f"docs/{node_id}.md",
        meta=meta,
        body=body,
    )


# 取り下げられた決定と、それを置き換えた決定。どのテストもこの 2 つを使う。
OLD = node("ADR-0008", type_="adr", status="deprecated")
NEW = node("ADR-0014", type_="adr", status="stable", supersedes=["ADR-0008"])


class Citations(unittest.TestCase):
    """段落単位の判定そのもの。"""

    def cite(self, body: str, **kw) -> list[str]:
        citing = node("UC-01", body=body, **kw)
        graph = make_graph([OLD, NEW, citing])
        return unacknowledged_citations(citing, graph, superseded_index(graph))

    def test_bare_citation_is_flagged(self) -> None:
        """断りなく引いている。**これが直したい形。**"""
        self.assertEqual(self.cite("報告期限は締めである（[[ADR-0008]]）。"), ["ADR-0008"])

    def test_successor_in_same_paragraph_is_silent(self) -> None:
        """その場で置き換え先も指していれば、承知のうえと見なす。"""
        self.assertEqual(
            self.cite("以前は締めだった（[[ADR-0008]]。いまは [[ADR-0014]]）。"), []
        )

    def test_successor_in_another_paragraph_still_flags(self) -> None:
        """**文書のどこかにあれば足りる、にはしない。**

        長い文書では別の話題で置き換え先に触れているだけで黙ってしまい、
        実データで本物を取りこぼした。
        """
        body = "報告期限は締めである（[[ADR-0008]]）。\n\n別の話。[[ADR-0014]] を見よ。\n"
        self.assertEqual(self.cite(body), ["ADR-0008"])

    def test_superseding_node_may_cite_what_it_replaces(self) -> None:
        """置き換えた側は指さないほうがおかしい。"""
        citing = node(
            "ADR-0014",
            type_="adr",
            body="[[ADR-0008]] を置き換える。",
            supersedes=["ADR-0008"],
        )
        graph = make_graph([OLD, citing])
        self.assertEqual(
            unacknowledged_citations(citing, graph, superseded_index(graph)), []
        )

    def test_chain_successor_may_cite_two_decisions_back(self) -> None:
        """**連鎖の先にいる側も、遡って引いてよい。**

        `A → B → C` のとき、`C` が `A` を引くのは「あちらはこう決めていた」と
        書いているだけで、直接の置き換え先 `B` を引くのと変わらない。
        実データでは `ADR-0007` が 2 つ前の `ADR-0004` を 4 箇所で引いていた。
        """
        mid = node("ADR-0010", type_="adr", status="deprecated", supersedes=["ADR-0008"])
        head = node(
            "ADR-0012",
            type_="adr",
            body="[[ADR-0008]] と同じ結論だが、理由がまったく違う。",
            supersedes=["ADR-0010"],
        )
        graph = make_graph([OLD, mid, head])
        self.assertEqual(
            unacknowledged_citations(head, graph, superseded_index(graph)), []
        )

    def test_pointing_at_the_head_of_the_chain_is_silent(self) -> None:
        """**連鎖の先端（現在の決定）を指すのも承知のうえである。**

        `A → B → C` と置き換わったとき、**現在の決定 `C` を指すほうが、
        直接の置き換え先 `B` を指すより正しい。** 片方しか認めないと、
        正しく書いた文書が鳴る。実データの表（「ADR-0004 の時点」と
        「現在（ADR-0007）」を並べたもの）がこれで落ちていた。
        """
        mid = node("ADR-0010", type_="adr", status="deprecated", supersedes=["ADR-0008"])
        head = node("ADR-0012", type_="adr", supersedes=["ADR-0010"])
        citing = node("ARCH-01", type_="architecture", body="[[ADR-0008]] の時点と、いまの [[ADR-0012]]。")
        graph = make_graph([OLD, mid, head, citing])
        self.assertEqual(
            unacknowledged_citations(citing, graph, superseded_index(graph)), []
        )

    def test_chain_is_listed_in_the_message(self) -> None:
        """指し直す先の候補は連鎖ぶん並べる。"""
        mid = node("ADR-0010", type_="adr", status="deprecated", supersedes=["ADR-0008"])
        head = node("ADR-0012", type_="adr", supersedes=["ADR-0010"])
        citing = node("UC-01", body="[[ADR-0008]] による。")
        issues = rule_g020_deprecated_references(make_graph([OLD, mid, head, citing]))
        self.assertIn("ADR-0008（置き換え先: ADR-0010 / ADR-0012）", issues[0].message)

    def test_superseding_cycle_does_not_hang(self) -> None:
        """`supersedes` の循環は `G006` の仕事。**ここで止まらないことだけを見る。**"""
        a = node("ADR-0030", type_="adr", status="deprecated", supersedes=["ADR-0031"])
        b = node("ADR-0031", type_="adr", status="deprecated", supersedes=["ADR-0030"])
        citing = node("UC-01", body="[[ADR-0030]] による。")
        issues = rule_g020_deprecated_references(make_graph([a, b, citing]))
        self.assertEqual(len(issues), 1)

    def test_table_row_counts_as_one_paragraph(self) -> None:
        """表は空行を挟まないので 1 段落。同じ表の中で断れば黙る。"""
        body = (
            "| 決定 | 扱い |\n"
            "| --- | --- |\n"
            "| [[ADR-0008]] | [[ADR-0014]] が置き換えた |\n"
        )
        self.assertEqual(self.cite(body), [])

    def test_code_block_is_ignored(self) -> None:
        """規約文書と雛形は書き方をコードブロックで例示する。そこは数えない。"""
        self.assertEqual(self.cite("説明。\n\n```\n[[ADR-0008]]\n```\n"), [])

    def test_html_comment_is_ignored(self) -> None:
        """雛形の記入案内はコメントの中にある。"""
        self.assertEqual(self.cite("<!-- 例: [[ADR-0008]] を引く -->\n本文。\n"), [])

    def test_stable_target_is_not_flagged(self) -> None:
        """取り下げていない決定を引くのは当たり前。"""
        self.assertEqual(self.cite("[[ADR-0014]] による。"), [])

    def test_unresolved_link_is_ignored(self) -> None:
        """リンク切れは G004 の仕事。ここでは黙る。"""
        self.assertEqual(self.cite("[[ADR-9999]] による。"), [])


class Rule(unittest.TestCase):
    """ルールとしての出方。"""

    def issues(self, *nodes: Node):
        return rule_g020_deprecated_references(make_graph([OLD, NEW, *nodes]))

    def test_warns_not_errors(self) -> None:
        """**歴史参照が正当なので、エラーにはできない。**"""
        issues = self.issues(node("UC-01", body="[[ADR-0008]] による。"))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, WARN)
        self.assertEqual(issues[0].code, "G020")
        self.assertEqual(issues[0].location, "docs/UC-01.md")

    def test_message_names_the_successor(self) -> None:
        """どこを指し直せばよいかを、読まずに分かる形で出す。"""
        issues = self.issues(node("UC-01", body="[[ADR-0008]] による。"))
        self.assertIn("ADR-0008（置き換え先: ADR-0014）", issues[0].message)

    def test_settled_adr_is_exempt(self) -> None:
        """**確定した ADR は不変の記録。** 本文を直させる指摘は成立しない。

        決定を変えるときは本文を書き換えず、新しい ADR を起こす。古い ADR に
        要るのは後継へのリンクだけで、本文の維持は要らない。
        **直せないものを鳴らし続けると `--strict` が塞がるだけである。**
        """
        self.assertEqual(
            self.issues(node("ADR-0020", type_="adr", body="[[ADR-0008]] による。")), []
        )

    def test_unsettled_adr_is_still_checked(self) -> None:
        """**確定前はまだ決めている途中なので、直してよい。**"""
        for status in ("draft", "review"):
            with self.subTest(status=status):
                issues = self.issues(
                    node("ADR-0020", type_="adr", status=status, body="[[ADR-0008]] による。")
                )
                self.assertEqual(len(issues), 1)

    def test_non_adr_layers_are_checked_whatever_the_status(self) -> None:
        """現在の設計を述べる層は、確定していても「いまの姿」に保つ場所である。"""
        for type_ in ("architecture", "domain", "usecase", "contract"):
            with self.subTest(type_=type_):
                citing = node("X-01", type_=type_, body="[[ADR-0008]] による。")
                self.assertEqual(len(self.issues(citing)), 1)

    def test_index_nodes_are_exempt(self) -> None:
        """一覧は取り下げたものも並べる。それが仕事である。"""
        self.assertEqual(
            self.issues(node("IDX-ADR", type_="index", body="- [[ADR-0008]]")), []
        )

    def test_deprecated_node_may_cite_deprecated(self) -> None:
        """歴史が歴史を引いている。"""
        self.assertEqual(
            self.issues(
                node("UC-02", status="deprecated", body="[[ADR-0008]] による。")
            ),
            [],
        )

    def test_one_issue_per_node(self) -> None:
        """節ごとではなくノードごとに 1 件。指し先は並べて出す。"""
        old2 = node("ADR-0003", type_="adr", status="deprecated")
        body = "[[ADR-0008]] による。\n\nまた [[ADR-0003]] による。\n"
        graph = make_graph([OLD, NEW, old2, node("UC-01", body=body)])
        issues = rule_g020_deprecated_references(graph)
        self.assertEqual(len(issues), 1)
        self.assertIn("ADR-0003", issues[0].message)
        self.assertIn("ADR-0008", issues[0].message)

    def test_target_without_successor_says_so(self) -> None:
        """置き換えずに取り下げただけの決定もある。指し直す先が無いと書く。"""
        graph = make_graph([OLD, node("UC-01", body="[[ADR-0008]] による。")])
        issues = rule_g020_deprecated_references(graph)
        self.assertIn("置き換え先なし", issues[0].message)


class MarkdownLinks(unittest.TestCase):
    """`[題](./xxx.md)` の形も数える。**実データではこちらが主だった。**"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = self.tmp / "docs"
        (self.docs / "50-adr").mkdir(parents=True)

    def write(self, rel: str, text: str) -> None:
        (self.docs / rel).write_text(text, encoding="utf-8", newline="\n")

    def build(self, citing_body: str) -> None:
        self.write(
            "index.md",
            "---\nid: IDX-ROOT\ntype: index\ntitle: 目次\nstatus: stable\n---\n\n"
            "# 目次\n\n- [ADR-0008](./50-adr/adr-0008-old.md)\n"
            "- [ADR-0014](./50-adr/adr-0014-new.md)\n",
        )
        self.write(
            "50-adr/adr-0008-old.md",
            "---\nid: ADR-0008\ntype: adr\ntitle: 古い決定\nstatus: deprecated\n---\n\n"
            "# 古い決定\n",
        )
        self.write(
            "50-adr/adr-0014-new.md",
            "---\nid: ADR-0014\ntype: adr\ntitle: 新しい決定\nstatus: stable\n"
            "supersedes:\n  - ADR-0008\n---\n\n# 新しい決定\n",
        )
        self.write(
            "50-adr/adr-0020-citing.md",
            # **確定前なので対象に残る。** stable にすると不変の記録として黙る。
            "---\nid: ADR-0020\ntype: adr\ntitle: 引いている決定\nstatus: review\n---\n\n"
            "# 引いている決定\n\n" + citing_body,
        )

    def codes(self) -> list[str]:
        graph = load(self.tmp)
        return [i.location for i in rule_g020_deprecated_references(graph)]

    def test_markdown_link_to_deprecated_is_flagged(self) -> None:
        self.build("報告期限は締めである（[ADR-0008](./adr-0008-old.md)）。\n")
        self.assertEqual(self.codes(), ["docs/50-adr/adr-0020-citing.md"])

    def test_markdown_link_with_successor_is_silent(self) -> None:
        self.build(
            "以前は締めだった（[ADR-0008](./adr-0008-old.md)。"
            "いまは [ADR-0014](./adr-0014-new.md)）。\n"
        )
        self.assertEqual(self.codes(), [])


if __name__ == "__main__":
    unittest.main()


class Readme(unittest.TestCase):
    """README はノードではないが、決定を引く。**ここで見ないと誰も見ない。**

    7 リポジトリの実測で 3 つの README が取り下げ済みの ADR を現在の根拠として
    引いていた。1 つは**移った先の事実を古いまま述べていた**（「3 つの Bot を
    同居」。置き換えた決定の題は「台数を問わない」）。
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def issues(self, readme: str):
        (self.tmp / "README.md").write_text(readme, encoding="utf-8")
        graph = make_graph([OLD, NEW])
        graph.root = self.tmp
        return rule_g020_deprecated_references(graph)

    def test_bare_citation_is_flagged(self) -> None:
        issues = self.issues("**設計の勘所。** [[ADR-0008]] による。")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G020")
        self.assertEqual(issues[0].severity, WARN)
        self.assertEqual(issues[0].location, "README.md")

    def test_successor_in_same_paragraph_is_silent(self) -> None:
        """判定はノードと同じ。段落の中で置き換え先も指していれば黙る。"""
        self.assertEqual(
            self.issues("以前は [[ADR-0008]] だった（いまは [[ADR-0014]]）。"), []
        )

    def test_generated_diagram_is_ignored(self) -> None:
        """README の図は自動生成で、取り下げたノードも題ごと並ぶ。

        **コードブロックなので数えない。** ここを数えると、図を持つ README が
        すべて鳴る。
        """
        readme = """説明。

```mermaid
graph LR
  A["[[ADR-0008]]"]
```
"""
        self.assertEqual(self.issues(readme), [])

    def test_relative_links_resolve_from_the_repository_root(self) -> None:
        """**README はリポジトリの根から書く。** ノードは自分のディレクトリから。

        基準を取り違えるとリンクが解決できず、**黙って 0 件になる。**
        """
        old = Node(
            id="ADR-0008",
            type="adr",
            title="ADR-0008",
            status="deprecated",
            tags=[],
            path=self.tmp / "docs" / "adr-0008.md",
            rel="docs/adr-0008.md",
            meta={
                "id": "ADR-0008",
                "type": "adr",
                "title": "ADR-0008",
                "status": "deprecated",
            },
            body="",
        )
        graph = make_graph([old, NEW])
        graph.root = self.tmp
        (self.tmp / "README.md").write_text(
            "**設計の勘所。** [ADR-0008](docs/adr-0008.md) による。", encoding="utf-8"
        )
        issues = rule_g020_deprecated_references(graph)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].location, "README.md")

    def test_missing_readme_is_silent(self) -> None:
        graph = make_graph([OLD, NEW])
        graph.root = self.tmp
        self.assertEqual(rule_g020_deprecated_references(graph), [])

    def test_partial_graph_without_root_is_silent(self) -> None:
        """部分グラフには root が無い。**検査が落ちてはいけない。**"""
        self.assertEqual(rule_g020_deprecated_references(make_graph([OLD, NEW])), [])
