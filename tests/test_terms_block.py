"""用語の一覧（sync がドメインの目次に作る）のテスト。

**写しにならないこと**が最も大事な性質である。元の表が変われば作り直され、
`sync --check` が古いままを見つける。目次の案内文には触らない。

グラフはこの場で組み立てる。**リポジトリの docs/ を読まない**（派生ではサンプルが消える）。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.loader import load
from tools.graph.sync import sync

IDX_DOM = "docs/20-domain/index.md"
DOM_01 = "docs/20-domain/dom-01-booking.md"

FILES = {
    "docs/index.md": """---
id: IDX-ROOT
type: index
title: ルート
status: stable
tags: [index]
---

# ルート

- [IDX-DOM ドメイン](./20-domain/index.md)
""",
    IDX_DOM: """---
id: IDX-DOM
type: index
title: ドメイン
status: stable
tags: [index]
---

# ドメイン

案内文はそのまま残る。

## ノード一覧

<!-- graph:children:start -->
<!-- graph:children:end -->
""",
    DOM_01: """---
id: DOM-01
type: domain
title: 予約
status: stable
tags: []
depends_on: []
related: []
---

# 予約

## 用語

| 用語 | 意味 | 旧称 |
| --- | --- | --- |
| 予約 | 席を押さえた記録（[UC-01](../30-usecases/uc-01-confirm-booking.md)） | — |
""",
    "docs/20-domain/dom-02-room.md": """---
id: DOM-02
type: domain
title: 部屋
status: stable
tags: []
depends_on: []
related: []
---

# 部屋

## 用語

| 用語 | 意味 | 旧称 |
| --- | --- | --- |
|  |  |  |
""",
    "docs/30-usecases/uc-01-confirm-booking.md": """---
id: UC-01
type: usecase
title: 予約を確定する
status: stable
tags: []
depends_on:
  - DOM-01
related: []
---

# 予約を確定する
""",
}


class TermsBlock(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for rel, text in FILES.items():
            path = self.tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def run_sync(self, **kwargs) -> list[str]:
        return sync(load(self.tmp), **kwargs)

    def text(self, rel: str) -> str:
        return (self.tmp / rel).read_text(encoding="utf-8")

    def rewrite(self, rel: str, old: str, new: str) -> None:
        path = self.tmp / rel
        path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    def test_appends_the_list_to_the_domain_index(self):
        self.assertIn(IDX_DOM, self.run_sync())
        text = self.text(IDX_DOM)
        self.assertIn("### [DOM-01 予約](./dom-01-booking.md)", text)
        self.assertIn("| 予約 | 席を押さえた記録", text)
        self.assertIn("案内文はそのまま残る。", text)
        self.assertTrue(text.rstrip().endswith(schema.TERMS_END), "無ければ末尾に足す")

    def test_a_second_sync_changes_nothing(self):
        self.run_sync()
        self.assertEqual(self.run_sync(), [])

    def test_a_changed_table_is_found_by_check_and_rebuilt_by_sync(self):
        self.run_sync()
        self.rewrite(DOM_01, "席を押さえた記録", "資源を押さえた記録")

        self.assertEqual(self.run_sync(dry_run=True), [IDX_DOM], "sync --check が古いままを見つける")
        self.assertIn("席を押さえた記録", self.text(IDX_DOM), "dry_run は書き込まない")

        self.run_sync()
        text = self.text(IDX_DOM)
        self.assertIn("資源を押さえた記録", text)
        self.assertNotIn("席を押さえた記録", text)
        self.assertEqual(text.count(schema.TERMS_START), 1, "入れ替えであって追記ではない")

    def test_nodes_without_terms_are_left_out(self):
        """雛形の空行しかない表は載せない。"""
        self.run_sync()
        self.assertNotIn("### [DOM-02", self.text(IDX_DOM))

    def test_an_emptied_list_keeps_its_markers(self):
        self.run_sync()
        self.rewrite(DOM_01, "| 予約 | 席を押さえた記録（[UC-01](../30-usecases/uc-01-confirm-booking.md)） | — |", "|  |  |  |")
        self.run_sync()
        text = self.text(IDX_DOM)
        self.assertIn(schema.TERMS_START, text)
        self.assertIn("まだありません", text)

    def test_links_in_the_list_are_not_edges_of_the_index(self):
        """一覧は写しなので、中のリンクで目次がユースケースを指していることにしない。"""
        self.run_sync()
        self.assertIn("uc-01-confirm-booking.md", self.text(IDX_DOM))
        targets = {edge.dst for edge in load(self.tmp).nodes["IDX-DOM"].edges}
        self.assertNotIn("UC-01", targets)

    def test_other_indexes_are_left_alone(self):
        before = self.text("docs/index.md")
        self.run_sync()
        self.assertEqual(self.text("docs/index.md"), before)


if __name__ == "__main__":
    unittest.main()
