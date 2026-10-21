"""G021（自動生成ブロックより後ろに本文がある）のテスト。

自動ブロックは「関連ドキュメント（自動生成 / 手で編集しない）」という**文書の締め**
である。その下に本文が続くとは読む人は思わない。しかもCLAUDE.mdが
「この塊を手で編集するな」と書いているので、**下の本文を直したい人は
「触るな」と書かれた塊を越えて行くことになる。**

**`sync`は自分では直せない。** ブロックが既にあればその場で入れ替えるだけで、
後ろに回った本文は動かさない。だから一度こうなると黙って残り続ける。

実際に`META-01`で84行が落ちていて、**共通ファイルなので7リポジトリすべてが
同じ状態だった**（1.14.2で直した）。いまは全リポジトリ0件なので、
このルールは**再発防止**として入っている。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.graph import schema
from tools.graph.loader import load
from tools.graph.model import ERROR
from tools.graph.rules import (
    content_after_auto_block,
    rule_g021_content_after_auto_block,
)

BLOCK = (
    f"{schema.AUTO_BLOCK_START}\n"
    "\n"
    "## 関連ドキュメント（自動生成 / 手で編集しない）\n"
    "\n"
    "- [DOM-01](../20-domain/dom-01-booking.md)\n"
    "\n"
    f"{schema.AUTO_BLOCK_END}\n"
)


class ContentAfterAutoBlock(unittest.TestCase):
    """判定そのもの。"""

    def test_block_at_the_end_is_clean(self) -> None:
        self.assertIsNone(content_after_auto_block(f"# 題\n\n本文。\n\n---\n\n{BLOCK}"))

    def test_no_block_at_all_is_clean(self) -> None:
        """`sync`を一度も回していない文書。**何も言わない。**"""
        self.assertIsNone(content_after_auto_block("# 題\n\n本文。\n"))

    def test_trailing_whitespace_is_clean(self) -> None:
        """改行や空白だけなら本文ではない。"""
        self.assertIsNone(content_after_auto_block(f"# 題\n\n{BLOCK}\n\n   \n\t\n"))

    def test_prose_after_block_is_flagged(self) -> None:
        """**これが実際に起きた形。**"""
        text = f"# 題\n\n本文。\n\n{BLOCK}\n## G018: 図の大きさ\n\n続き。\n"
        found = content_after_auto_block(text)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found[1], "## G018: 図の大きさ")

    def test_reports_the_first_non_blank_line(self) -> None:
        """空行を挟んでいても、本文が始まる行を指す。"""
        text = f"{BLOCK}\n\n\n取り残された本文。\n"
        found = content_after_auto_block(text)
        assert found is not None
        lineno, line = found
        self.assertEqual(line, "取り残された本文。")
        self.assertEqual(text.split("\n")[lineno - 1], "取り残された本文。")

    def test_children_marker_is_not_examined(self) -> None:
        """**目次の一覧ブロックは文書の途中に置くのが正しい。**

        一覧の後ろに「使い方」を書くのが目次の形なので、
        ここを見ると目次が丸ごと落ちる。
        """
        text = (
            "# 目次\n\n"
            f"{schema.CHILDREN_START}\n- [UC-01](./uc-01.md)\n{schema.CHILDREN_END}\n"
            "\n## 使い方\n\nここは正しい。\n"
        )
        self.assertIsNone(content_after_auto_block(text))

    def test_last_block_wins(self) -> None:
        """ブロックが2つある文書は既に壊れているが、**最後の1つ**を基準にする。

        間に挟まった本文まで数えると、直す場所が分からない指摘になる。
        """
        text = f"{BLOCK}\n間の本文。\n\n{BLOCK}"
        self.assertIsNone(content_after_auto_block(text))


class Rule(unittest.TestCase):
    """ノードを読んで出るところまで。"""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = self.tmp / "docs"
        (self.docs / "20-domain").mkdir(parents=True)
        (self.docs / "index.md").write_text(
            "---\nid: IDX-ROOT\ntype: index\ntitle: 目次\nstatus: stable\n---\n\n"
            "# 目次\n\n- [DOM-01](./20-domain/dom-01-booking.md)\n",
            encoding="utf-8",
            newline="\n",
        )

    def write_domain(self, tail: str) -> None:
        (self.docs / "20-domain/dom-01-booking.md").write_text(
            "---\nid: DOM-01\ntype: domain\ntitle: 予約\nstatus: stable\n---\n\n"
            "# 予約\n\n## 定義\n\n席を押さえた記録。\n\n---\n\n" + BLOCK + tail,
            encoding="utf-8",
            newline="\n",
        )

    def test_clean_tree_is_silent(self) -> None:
        self.write_domain("")
        self.assertEqual(rule_g021_content_after_auto_block(load(self.tmp)), [])

    def test_errors_not_warns(self) -> None:
        """**承知のうえで放置してよい場合が無い。** 読む人に届いていない本文がある。"""
        self.write_domain("\n## 不変条件\n\n- [ ] 同じ席に 2 つの確定した予約は無い\n")
        issues = rule_g021_content_after_auto_block(load(self.tmp))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "G021")
        self.assertEqual(issues[0].severity, ERROR)
        self.assertEqual(issues[0].location, "docs/20-domain/dom-01-booking.md")
        self.assertIn("## 不変条件", issues[0].message)

    def test_body_is_still_stripped_for_other_rules(self) -> None:
        """**`node.body`では判定できないことを固定する。**

        `strip_auto_block`を通した後の本文はブロックの前後が繋がるので、
        後ろに回った本文が「文書の途中」に見えてしまう。生テキストを読むこと。
        """
        self.write_domain("\n取り残された本文。\n")
        graph = load(self.tmp)
        self.assertNotIn(schema.AUTO_BLOCK_END, graph.nodes["DOM-01"].body)
        self.assertEqual(len(rule_g021_content_after_auto_block(graph)), 1)


if __name__ == "__main__":
    unittest.main()
