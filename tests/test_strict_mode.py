"""strict モードのテスト。

**警告とエラーで終了コードの扱いが違う**ことを固定する。
ここが崩れると CI が黙って通るようになる。

グラフはこの場で組み立てる。**リポジトリの docs/ を読まない。**
テンプレートのサンプルノードは派生プロジェクトで消されているので、
それに依存すると派生側でだけ落ちるテストになる。
"""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.graph import cli

INDEX = """---
id: IDX-ROOT
type: index
title: テスト用の目次
status: stable
tags: [index]
---

# テスト用の目次

- [DOM-01 予約](./20-domain/dom-01-booking.md)
- [UC-01 予約を確定する](./30-usecases/uc-01-confirm-booking.md)
"""

DOMAIN = """---
id: DOM-01
type: domain
title: 予約
status: stable
tags: []
depends_on: []
related: []
---

# 予約

## 定義

席を押さえた記録。

## 不変条件

- [ ] 同じ席に 2 つの確定した予約は存在しない

## 用語

| 用語 | 意味 | 使ってはいけない言い換え |
| --- | --- | --- |
| 予約 | 席を押さえた記録 | 申込（別の概念と混ざる） |
"""

USECASE = """---
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

## 概要

仮予約を確定にする。

## 事前条件

- [ ] 対象の[[DOM-01]]が「仮予約」で存在する
"""


def build_docs(root: Path) -> None:
    docs = root / "docs"
    (docs / "20-domain").mkdir(parents=True)
    (docs / "30-usecases").mkdir(parents=True)
    (docs / "index.md").write_text(INDEX, encoding="utf-8")
    (docs / "20-domain" / "dom-01-booking.md").write_text(DOMAIN, encoding="utf-8")
    (docs / "30-usecases" / "uc-01-confirm-booking.md").write_text(
        USECASE, encoding="utf-8"
    )


def run_check(root: Path, *extra: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--root", str(root), "check", "--no-history", *extra])
    return code, out.getvalue()


class StrictMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        build_docs(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_clean_graph_passes_both_ways(self):
        self.assertEqual(run_check(self.tmp), (0, run_check(self.tmp)[1]))
        self.assertEqual(run_check(self.tmp, "--strict")[0], 0)

    def test_a_warning_only_fails_under_strict(self):
        """G014 を 1 件起こして、通常と strict の差を見る。"""
        target = self.tmp / "docs" / "20-domain" / "dom-01-booking.md"
        body = target.read_text(encoding="utf-8")
        target.write_text(body.replace("## 用語", "## 語彙"), encoding="utf-8")

        code, output = run_check(self.tmp)
        self.assertEqual(code, 0, "警告だけなら check は通る")
        self.assertIn("G014", output)

        code, _ = run_check(self.tmp, "--strict")
        self.assertEqual(code, 1, "--strict では警告も失敗になる")

    def test_an_error_fails_even_without_strict(self):
        """リンク切れ（G004）は警告ではなくエラー。"""
        target = self.tmp / "docs" / "30-usecases" / "uc-01-confirm-booking.md"
        body = target.read_text(encoding="utf-8")
        target.write_text(body.replace("[[DOM-01]]", "[[DOM-99]]"), encoding="utf-8")

        code, output = run_check(self.tmp)
        self.assertEqual(code, 1, "エラーは strict でなくても失敗する")
        self.assertIn("G004", output)


if __name__ == "__main__":
    unittest.main()
