"""`graph review`（AI lint）のテスト。

**ここでネットワークに出てはいけない。** 送信は差し替え可能な関数にしてあるので、
すべてモックで確かめる。実際に API を叩くのは人が手で 1 回だけ試す。
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.graph import cli, review
from tools.graph.model import Edge, Node

from .helpers import make_graph


def node(node_id="DOM-01", node_type="domain", body="## 定義\n仮の本文\n") -> Node:
    return Node(
        id=node_id,
        type=node_type,
        title=node_id,
        status="stable",
        tags=[],
        path=Path(f"/tmp/{node_id}.md"),
        rel=f"docs/{node_id}.md",
        meta={},
        body=body,
        edges=[],
    )


def api_response(findings: list[dict]) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"findings": findings})}]}


class ParseFindings(unittest.TestCase):
    def test_reads_a_well_formed_response(self):
        data = api_response(
            [{"code": "A001", "quote": "適切に", "message": "曖昧", "suggestion": "基準を書く"}]
        )
        found = review.parse_findings(node(), data)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].code, "A001")
        self.assertEqual(found[0].message, "曖昧")

    def test_unwraps_a_fenced_code_block(self):
        """モデルが ```json で包むことがある。"""
        inner = json.dumps({"findings": [{"code": "A002", "message": "冗長"}]})
        data = {"content": [{"type": "text", "text": f"```json\n{inner}\n```"}]}
        self.assertEqual(len(review.parse_findings(node(), data)), 1)

    def test_drops_unknown_codes(self):
        """G 系の番号を返してきても受け取らない。名前空間を分けた意味が消える。"""
        data = api_response([{"code": "G014", "message": "節が無い"}])
        self.assertEqual(review.parse_findings(node(), data), [])

    def test_broken_json_is_discarded_without_raising(self):
        data = {"content": [{"type": "text", "text": "すみません、JSON ではありません"}]}
        self.assertEqual(review.parse_findings(node(), data), [])

    def test_empty_findings(self):
        self.assertEqual(review.parse_findings(node(), api_response([])), [])


class Prompt(unittest.TestCase):
    def test_includes_the_body_and_the_type(self):
        prompt = review.build_prompt(make_graph([node()]), node())
        self.assertIn("仮の本文", prompt)
        self.assertIn("type: domain", prompt)

    def test_carries_the_forbidden_terms_of_dependencies(self):
        """G013 が届かない揺れを見てもらうため、依存先の用語表を渡す。"""
        owner = node("DOM-02", body=(
            "## 用語\n\n"
            "| 用語 | 意味 | 使ってはいけない言い換え |\n"
            "| --- | --- | --- |\n"
            "| エントリー | 出る意思 | 参加（混ざる） |\n"
        ))
        child = node("UC-01", "usecase", "## 概要\nx\n")
        child.edges.append(
            Edge(src="UC-01", dst="DOM-02", kind="depends_on", origin="frontmatter")
        )
        prompt = review.build_prompt(make_graph([owner, child]), child)
        self.assertIn("参加", prompt)
        self.assertIn("エントリー", prompt)


class ReviewNode(unittest.TestCase):
    def test_uses_the_injected_transport_and_never_calls_the_network(self):
        seen = {}

        def fake(payload, api_key):
            seen["payload"] = payload
            seen["key"] = api_key
            return api_response([{"code": "A003", "message": "揺れ"}])

        n = node()
        found = review.review_node(
            make_graph([n]), n, api_key="dummy", model="test-model", transport=fake
        )
        self.assertEqual(len(found), 1)
        self.assertEqual(seen["key"], "dummy")
        self.assertEqual(seen["payload"]["model"], "test-model")
        self.assertIn("A001", seen["payload"]["system"])


class SelectNodes(unittest.TestCase):
    def test_limit_caps_the_number_sent(self):
        nodes = [node(f"DOM-{i:02}") for i in range(1, 6)]
        self.assertEqual(len(review.select_nodes(make_graph(nodes), limit=2)), 2)

    def test_zero_means_everything(self):
        nodes = [node(f"DOM-{i:02}") for i in range(1, 6)]
        self.assertEqual(len(review.select_nodes(make_graph(nodes), limit=0)), 5)

    def test_index_nodes_are_skipped(self):
        nodes = [node("IDX-ROOT", "index"), node("DOM-01")]
        picked = review.select_nodes(make_graph(nodes), limit=0)
        self.assertEqual([n.id for n in picked], ["DOM-01"])


class WithoutAnApiKey(unittest.TestCase):
    def test_exits_zero_and_says_so(self):
        """キーが無いのはグラフの問題ではない。失敗にしない。"""
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["review"])
        self.assertEqual(code, 0)
        self.assertIn(review.API_KEY_ENV, out.getvalue())

    def setUp(self):
        self._saved = review.os.environ.pop(review.API_KEY_ENV, None)

    def tearDown(self):
        if self._saved is not None:
            review.os.environ[review.API_KEY_ENV] = self._saved


if __name__ == "__main__":
    unittest.main()
