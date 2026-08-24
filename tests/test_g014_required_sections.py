"""G014（テンプレートの必須の節）のテスト。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.model import Edge, Node
from tools.graph.rules import (
    required_sections,
    rule_g014_required_sections,
    sections,
)

from .helpers import make_graph


def node(node_id: str, node_type: str, body: str, *, refines: str = "") -> Node:
    edges = []
    if refines:
        edges.append(Edge(src=node_id, dst=refines, kind="refines", origin="frontmatter"))
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
        edges=edges,
    )


class SectionExtraction(unittest.TestCase):
    def test_reads_level_two_headings_in_order(self):
        body = "# 題\n\n## 定義\n本文\n\n## 用語\n本文\n"
        self.assertEqual(sections(body), ["定義", "用語"])

    def test_ignores_level_one_and_three(self):
        body = "# 定義\n### 用語\n## 属性\n"
        self.assertEqual(sections(body), ["属性"])

    def test_ignores_headings_inside_code_fences(self):
        """雛形の説明にはコードブロックの中に `## ` が出てくる。"""
        body = "## 定義\n\n```markdown\n## 用語\n```\n"
        self.assertEqual(sections(body), ["定義"])

    def test_trailing_spaces_do_not_break_matching(self):
        self.assertEqual(sections("##   定義   \n"), ["定義"])


class RequiredSectionSelection(unittest.TestCase):
    def test_plain_node_uses_the_type_default(self):
        n = node("DOM-01", "domain", "")
        self.assertEqual(required_sections(n), schema.REQUIRED_SECTIONS["domain"])

    def test_refines_child_uses_the_relaxed_set(self):
        """親から切り出した子には、親が持つ節を求めない。"""
        n = node("DOM-05", "domain", "", refines="DOM-01")
        self.assertEqual(
            required_sections(n), schema.REQUIRED_SECTIONS_REFINED["domain"]
        )
        self.assertNotIn("定義", required_sections(n))

    def test_type_without_a_definition_is_not_checked(self):
        n = node("CON-01", "contract", "")
        self.assertEqual(required_sections(n), ())


class Rule(unittest.TestCase):
    def test_passes_when_every_required_section_is_present(self):
        body = "## 定義\nx\n## 不変条件\nx\n## 用語\nx\n"
        issues = rule_g014_required_sections(make_graph([node("DOM-01", "domain", body)]))
        self.assertEqual(issues, [])

    def test_reports_the_missing_sections(self):
        body = "## 定義\nx\n"
        issues = rule_g014_required_sections(make_graph([node("DOM-01", "domain", body)]))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G014")
        self.assertEqual(issues[0].severity, "warn")
        self.assertIn("不変条件", issues[0].message)
        self.assertIn("用語", issues[0].message)
        self.assertNotIn("定義", issues[0].message)

    def test_a_section_written_as_none_still_passes(self):
        """中身までは見ない。「なし」と書いてあれば通る。"""
        body = "## 概要\nx\n## 事前条件\n\n- [ ] なし\n"
        issues = rule_g014_required_sections(make_graph([node("UC-01", "usecase", body)]))
        self.assertEqual(issues, [])

    def test_refines_child_passes_without_the_parent_sections(self):
        body = "## 不変条件\nx\n## 用語\nx\n"
        n = node("DOM-05", "domain", body, refines="DOM-01")
        self.assertEqual(rule_g014_required_sections(make_graph([n])), [])

    def test_contract_is_not_checked(self):
        n = node("CON-01", "contract", "## なにか\nx\n")
        self.assertEqual(rule_g014_required_sections(make_graph([n])), [])

    def test_extra_sections_are_allowed(self):
        """ノードが節を足すのは正常。多い分には何も言わない。"""
        body = "## 定義\nx\n## 不変条件\nx\n## 用語\nx\n## 独自の節\nx\n"
        n = node("DOM-01", "domain", body)
        self.assertEqual(rule_g014_required_sections(make_graph([n])), [])


if __name__ == "__main__":
    unittest.main()
