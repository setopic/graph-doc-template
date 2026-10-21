"""`stats`の構造の見直しの候補、`path`、`render --budget`のテスト。"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.graph import cli, structure
from tools.graph.model import Edge, Node

from tests.helpers import make_graph
from tests.test_strict_mode import build_docs

DOCS = Path("/tmp/structure/docs")
DIRS = {
    "architecture": "10-architecture",
    "domain": "20-domain",
    "usecase": "30-usecases",
    "contract": "40-contracts",
    "adr": "50-adr",
}


def make(node_id: str, node_type: str, body: str = "", deps=(), mentions=(), refines=()) -> Node:
    name = f"{node_id.lower()}.md"
    node = Node(
        id=node_id,
        type=node_type,
        title=f"{node_id}の題",
        status="stable",
        tags=[],
        path=DOCS / DIRS[node_type] / name,
        rel=f"docs/{DIRS[node_type]}/{name}",
        meta={},
        body=body,
        edges=[],
    )
    for kind, targets, origin in (
        ("depends_on", deps, "frontmatter"),
        ("refines", refines, "frontmatter"),
        ("mentions", mentions, "body"),
    ):
        for dst in targets:
            node.edges.append(Edge(src=node_id, dst=dst, kind=kind, origin=origin))
    return node


TERMS = (
    "## 用語\n\n"
    "| 用語 | 意味 |\n"
    "| --- | --- |\n"
    "| 予約 | 資源を確保した記録 |\n"
    "| **保持期限** | 仮予約を確定できる期限 |\n"
)


class DependedCounts(unittest.TestCase):
    def test_counts_depends_on_most_first(self):
        graph = make_graph(
            [
                make("ARCH-01", "architecture"),
                make("DOM-01", "domain", deps=("ARCH-01",)),
                make("UC-01", "usecase", deps=("DOM-01", "ARCH-01")),
            ]
        )
        self.assertEqual(structure.depended_counts(graph), [("ARCH-01", 2), ("DOM-01", 1)])


class UnusedNodes(unittest.TestCase):
    def test_a_node_nobody_depends_on_is_listed_except_the_top_layer(self):
        graph = make_graph(
            [
                make("ARCH-01", "architecture"),
                make("ARCH-02", "architecture"),
                make("DOM-01", "domain", deps=("ARCH-01",)),
                make("CON-01", "contract", deps=("DOM-01",)),
            ]
        )
        self.assertEqual([n.id for n in structure.unused_nodes(graph)], ["ARCH-02"])

    def test_refines_counts_as_use(self):
        graph = make_graph(
            [
                make("DOM-01", "domain"),
                make("DOM-02", "domain", refines=("DOM-01",)),
                make("UC-01", "usecase", deps=("DOM-02",)),
            ]
        )
        self.assertEqual([n.id for n in structure.unused_nodes(graph)], [])

    def test_layer_exempt_types_are_ignored(self):
        graph = make_graph([make("ADR-0001", "adr"), make("UC-01", "usecase")])
        self.assertEqual(structure.unused_nodes(graph), [])


class UnusedTerms(unittest.TestCase):
    def test_a_term_no_dependent_writes_is_listed(self):
        graph = make_graph(
            [
                make("DOM-01", "domain", TERMS),
                make("UC-01", "usecase", "予約を確定する。", deps=("DOM-01",)),
            ]
        )
        self.assertEqual(structure.unused_terms(graph), [("DOM-01", "保持期限")])

    def test_paired_terms_on_one_row_are_looked_up_one_by_one(self):
        pair = TERMS + "| 付与 / 剥奪 | ロールを足す / 外す |\n| A/B | 2つの案を比べること |\n"
        graph = make_graph(
            [
                make("DOM-01", "domain", pair),
                make("UC-01", "usecase", "予約の保持期限に、ロールを付与する。", deps=("DOM-01",)),
            ]
        )
        self.assertEqual(structure.unused_terms(graph), [("DOM-01", "剥奪"), ("DOM-01", "A/B")])

    def test_indirect_dependents_count(self):
        graph = make_graph(
            [
                make("DOM-01", "domain", TERMS),
                make("UC-01", "usecase", "予約を確定する。", deps=("DOM-01",)),
                make("CON-01", "contract", "保持期限を過ぎたら409を返す。", deps=("UC-01",)),
            ]
        )
        self.assertEqual(structure.unused_terms(graph), [])

    def test_a_node_without_dependents_is_left_to_unused_nodes(self):
        graph = make_graph([make("DOM-01", "domain", TERMS)])
        self.assertEqual(structure.unused_terms(graph), [])


class BodyOnlyReferences(unittest.TestCase):
    def test_a_mention_toward_a_lower_layer_without_depends_on_is_listed(self):
        graph = make_graph(
            [
                make("DOM-01", "domain"),
                make("UC-01", "usecase", mentions=("DOM-01",)),
            ]
        )
        pairs = structure.body_only_references(graph)
        self.assertEqual([(a.id, b.id) for a, b in pairs], [("UC-01", "DOM-01")])

    def test_an_indirect_prerequisite_is_not_listed(self):
        graph = make_graph(
            [
                make("ARCH-01", "architecture"),
                make("DOM-01", "domain", deps=("ARCH-01",)),
                make("UC-01", "usecase", deps=("DOM-01",), mentions=("ARCH-01",)),
            ]
        )
        self.assertEqual(structure.body_only_references(graph), [])

    def test_a_mention_toward_a_higher_layer_is_navigation(self):
        graph = make_graph(
            [
                make("DOM-01", "domain", mentions=("UC-01",)),
                make("UC-01", "usecase", deps=("DOM-01",)),
            ]
        )
        self.assertEqual(structure.body_only_references(graph), [])


class ShortestPath(unittest.TestCase):
    def setUp(self):
        self.graph = make_graph(
            [
                make("ARCH-01", "architecture"),
                make("DOM-01", "domain", deps=("ARCH-01",)),
                make("UC-01", "usecase", deps=("DOM-01",)),
                make("CON-01", "contract", deps=("UC-01", "ARCH-01")),
            ]
        )

    def test_the_shortest_route_is_chosen(self):
        self.assertEqual(
            structure.shortest_path(self.graph, "CON-01", "ARCH-01"),
            [("", "CON-01"), ("depends_on", "ARCH-01")],
        )

    def test_only_the_prerequisite_direction_is_followed(self):
        self.assertIsNone(structure.shortest_path(self.graph, "ARCH-01", "CON-01"))

    def test_mentions_are_not_followed(self):
        graph = make_graph(
            [make("DOM-01", "domain"), make("UC-01", "usecase", mentions=("DOM-01",))]
        )
        self.assertIsNone(structure.shortest_path(graph, "UC-01", "DOM-01"))


class Budget(unittest.TestCase):
    # リポジトリのdocs/を読まない。派生ではサンプルのUC-01が無く、graph.tomlで種別を
    # 差し替えたリポジトリでは、configureの結果が後に実行するテストにまで残る
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        build_docs(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.tmp), *argv])
        return code, out.getvalue()

    def test_chars_are_reported_and_nodes_over_the_budget_are_omitted(self):
        code, out = self.run_cli("render", "--format", "json", "--focus", "UC-01", "--budget", "1")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual([n["id"] for n in data["nodes"]], ["UC-01"])
        self.assertGreater(data["nodes"][0]["chars"], 0)
        self.assertTrue(data["omitted"])
        self.assertTrue(all(e["src"] == "UC-01" and e["dst"] == "UC-01" for e in data["edges"]))

    def test_without_a_budget_there_is_no_omitted_key(self):
        _, out = self.run_cli("render", "--format", "json", "--focus", "UC-01")
        self.assertNotIn("omitted", json.loads(out))

    def test_budget_needs_focus_and_json(self):
        code, _ = self.run_cli("render", "--format", "json", "--budget", "100")
        self.assertEqual(code, 1)

    def test_a_farther_hop_is_dropped_once_a_nearer_one_was(self):
        graph = make_graph(
            [
                make("ARCH-01", "architecture", "a" * 10),
                make("DOM-01", "domain", "d" * 100, deps=("ARCH-01",)),
                make("UC-01", "usecase", "u" * 10, deps=("DOM-01",)),
            ]
        )
        distance = graph.hops(["UC-01"], depth=2)
        kept, omitted = cli._fit_budget(graph, distance, 50)
        self.assertEqual(kept, {"UC-01"})
        self.assertEqual([n.id for n in omitted], ["DOM-01", "ARCH-01"])


if __name__ == "__main__":
    unittest.main()
