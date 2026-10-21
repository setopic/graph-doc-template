"""規約の文書（meta）の自動生成ブロックに、逆引きを書かないことのテスト。

`meta`はテンプレートが配る共通ファイルである。逆引きを書くと、派生や上の層の
ノードしだいで中身が変わり、取り込みのたびに競合する（#129）。

グラフはこの場で組み立てる。**リポジトリのdocs/を読まない**（派生ではサンプルが消える）。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph.loader import load
from tools.graph.sync import sync

META_01 = "docs/00-meta/graph-rules.md"
META_02 = "docs/00-meta/node-types.md"
ADR_01 = "docs/50-adr/adr-0001-graph-driven-docs.md"

FILES = {
    "docs/index.md": """---
id: IDX-ROOT
type: index
title: ルート
status: stable
tags: [index]
---

# ルート

- [META-01 グラフの規約](./00-meta/graph-rules.md)
- [META-02 ノード種別と層](./00-meta/node-types.md)
- [ADR-0001 設計文書をグラフとして管理する](./50-adr/adr-0001-graph-driven-docs.md)
""",
    META_01: """---
id: META-01
type: meta
title: グラフの規約
status: stable
tags: [meta]
related:
  - META-02
---

# グラフの規約
""",
    META_02: """---
id: META-02
type: meta
title: ノード種別と層
status: stable
tags: [meta]
---

# ノード種別と層
""",
    ADR_01: """---
id: ADR-0001
type: adr
title: 設計文書をグラフとして管理する
status: stable
tags: []
decides:
  - META-01
related: []
---

# 設計文書をグラフとして管理する
""",
}


class MetaBacklinks(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for rel, text in FILES.items():
            path = self.tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def text(self, rel: str) -> str:
        return (self.tmp / rel).read_text(encoding="utf-8")

    def test_meta_lists_its_own_links_only(self):
        sync(load(self.tmp))
        text = self.text(META_01)
        self.assertIn("- [META-02 ノード種別と層](./node-types.md)", text)
        self.assertNotIn("このノードを参照しているノード", text)
        self.assertNotIn("ADR-0001", text)

    def test_other_nodes_do_not_change_a_meta_file(self):
        """派生や上の層がノードを足しても、共通ファイルは変わらない。"""
        sync(load(self.tmp))
        before = self.text(META_01)
        (self.tmp / ADR_01).unlink()
        self.assertNotIn(META_01, sync(load(self.tmp)))
        self.assertEqual(self.text(META_01), before)

    def test_meta_without_links_does_not_ask_for_links(self):
        """META-02はMETA-01から参照されているので、孤立していると書かない。"""
        sync(load(self.tmp))
        text = self.text(META_02)
        self.assertNotIn("まだリンクが無い", text)
        self.assertIn("規約の文書なので", text)

    def test_other_types_keep_backlinks(self):
        sync(load(self.tmp))
        self.assertNotIn("このノードを参照しているノード", self.text(ADR_01))
        self.rewrite_related(META_01)
        sync(load(self.tmp))
        self.assertIn("(related) [META-01 グラフの規約]", self.text(ADR_01))

    def rewrite_related(self, rel: str) -> None:
        path = self.tmp / ADR_01
        text = path.read_text(encoding="utf-8").replace("related: []", "related:\n  - META-01")
        path.write_text(text, encoding="utf-8")
        # 相互に書く決まり（G010）に合わせて、META-01の側にも書く
        path = self.tmp / rel
        text = path.read_text(encoding="utf-8").replace("  - META-02\n", "  - META-02\n  - ADR-0001\n")
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
