"""graph.toml（プロジェクトごとのノード種別）のテスト。

**graph.tomlが無いリポジトリで、何も変わらないこと**が最も大事な性質である。
派生のほとんどはこのファイルを置かないので、そこが崩れると全派生の検証が変わる。

グラフはこの場で組み立てる。**リポジトリの docs/ を読まない。**
"""

from __future__ import annotations

import copy
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.graph import cli, schema
from tools.graph.loader import load
from tools.graph.rules import rule_g022_duplicate_terms
from tools.graph.sync import sync

CONFIG = """
[node_types.world]
prefix = "WLD"
dir = "10-world"
layer = 10
label = "世界観"
terms = true

[node_types.character]
prefix = "CHR"
dir = "20-characters"
layer = 20
label = "人物"
terms = true
required_sections = ["人物像", "用語"]

[node_types.episode]
prefix = "EP"
dir = "40-episodes"
layer = 40
label = "各話"

[node_types.decision]
prefix = "DEC"
dir = "50-decisions"
layer = 90
label = "決定"
exempt_layer = true
immutable = true
"""

FILES = {
    "docs/index.md": """---
id: IDX-ROOT
type: index
title: 目次
status: stable
tags: [index]
---

# 目次

- [IDX-CHR 人物](./20-characters/index.md)
- [EP-01 第1話](./40-episodes/ep-01-first.md)
""",
    "docs/20-characters/index.md": """---
id: IDX-CHR
type: index
title: 人物
status: stable
tags: [index]
---

# 人物

<!-- graph:children:start -->
- [CHR-01 アン](./chr-01-anne.md)
- [CHR-02 ベン](./chr-02-ben.md)
<!-- graph:children:end -->
""",
    "docs/20-characters/chr-01-anne.md": """---
id: CHR-01
type: character
title: アン
status: stable
tags: []
---

# アン

## 人物像

主人公。

## 用語

| 用語 | 意味 | 旧称 |
| --- | --- | --- |
| アン | 主人公の名前 | アンナ |
""",
    "docs/20-characters/chr-02-ben.md": """---
id: CHR-02
type: character
title: ベン
status: stable
tags: []
---

# ベン

## 人物像

アンの兄。

## 用語

| 用語 | 意味 | 旧称 |
| --- | --- | --- |
| ベン | アンの兄 | — |
""",
    "docs/40-episodes/ep-01-first.md": """---
id: EP-01
type: episode
title: 第1話
status: stable
tags: []
depends_on:
  - CHR-01
  - CHR-02
---

# 第1話

アンナが目を覚ました。
""",
}


def run_cli(root: Path, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = cli.main(["--root", str(root), *args])
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # ほかのテストは既定の語彙を前提にしているので、必ず戻す
        self.addCleanup(schema.reset)

    def write(self, rel: str, text: str) -> None:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def text(self, rel: str) -> str:
        return (self.tmp / rel).read_text(encoding="utf-8")


class WithoutConfig(Base):
    def test_defaults_are_kept(self):
        before = copy.deepcopy(schema.NODE_TYPES)
        schema.configure(self.tmp)
        self.assertEqual(schema.NODE_TYPES, before)
        self.assertEqual(schema.TERM_TYPES, ("domain",))
        self.assertEqual(schema.IMMUTABLE_RECORD_TYPES, ("adr",))

    def test_configure_after_a_config_returns_to_defaults(self):
        before = copy.deepcopy(schema.NODE_TYPES)
        other = self.tmp / "other"
        other.mkdir()
        (other / schema.CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
        schema.configure(other)
        schema.configure(self.tmp)
        self.assertEqual(schema.NODE_TYPES, before)


class WithConfig(Base):
    def setUp(self) -> None:
        super().setUp()
        self.write(schema.CONFIG_FILE, CONFIG)
        for rel, text in FILES.items():
            self.write(rel, text)

    def test_the_config_replaces_the_template_types(self):
        schema.configure(self.tmp)
        self.assertEqual(
            set(schema.NODE_TYPES), {"index", "meta", "world", "character", "episode", "decision"}
        )
        self.assertEqual(schema.REQUIRED_SECTIONS["character"], ("人物像", "用語"))
        self.assertEqual(schema.REQUIRED_SECTIONS["episode"], ())
        self.assertEqual(schema.TERM_TYPES, ("world", "character"))
        self.assertEqual(schema.IMMUTABLE_RECORD_TYPES, ("decision",))

    def test_check_passes_and_uses_the_new_types(self):
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.assertIn("G013", output, "依存先の人物の旧称を、各話の本文から見つける")

    def test_a_template_type_is_unknown(self):
        self.write(
            "docs/40-episodes/ep-01-first.md",
            FILES["docs/40-episodes/ep-01-first.md"].replace("type: episode", "type: usecase"),
        )
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("未知のtype", output)

    def test_layers_follow_the_config(self):
        """人物（20）が各話（40）に依存したら、層の逆流になる。"""
        self.write(
            "docs/20-characters/chr-02-ben.md",
            FILES["docs/20-characters/chr-02-ben.md"].replace(
                "tags: []\n", "tags: []\ndepends_on:\n  - EP-01\n"
            ),
        )
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("G007", output)

    def test_sync_builds_the_terms_list_in_the_character_index(self):
        code, output = run_cli(self.tmp, "sync")
        self.assertEqual(code, 0, output)
        text = self.text("docs/20-characters/index.md")
        self.assertIn(schema.TERMS_START, text)
        self.assertIn("各人物ノードの「用語」表を集めたものである。", text)
        self.assertIn("### [CHR-01 アン](./chr-01-anne.md)", text)

    def test_duplicate_terms_are_found_in_term_types(self):
        self.write(
            "docs/20-characters/chr-02-ben.md",
            FILES["docs/20-characters/chr-02-ben.md"].replace("| ベン | アンの兄", "| アン | 別人"),
        )
        schema.configure(self.tmp)
        issues = rule_g022_duplicate_terms(load(self.tmp))
        self.assertEqual([i.code for i in issues], ["G022"])

    def test_new_creates_a_node_of_a_new_type(self):
        self.write(
            "docs/00-meta/templates/episode.md",
            "---\nid: {{ID}}\ntype: {{TYPE}}\ntitle: {{TITLE}}\nstatus: {{STATUS}}\ntags: []\n---\n\n# {{TITLE}}\n",
        )
        self.write(
            "docs/40-episodes/index.md",
            "---\nid: IDX-EP\ntype: index\ntitle: 各話\nstatus: stable\ntags: [index]\n---\n\n"
            "# 各話\n\n<!-- graph:children:start -->\n<!-- graph:children:end -->\n",
        )
        code, output = run_cli(
            self.tmp, "new", "--type", "episode", "--id", "EP-02", "--title", "第2話", "--slug", "second"
        )
        self.assertEqual(code, 0, output)
        self.assertTrue((self.tmp / "docs/40-episodes/ep-02-second.md").is_file())


class BrokenConfig(Base):
    def assert_rejected(self, config: str, message: str) -> None:
        self.write(schema.CONFIG_FILE, config)
        with self.assertRaises(schema.ConfigError) as caught:
            schema.configure(self.tmp)
        self.assertIn(message, str(caught.exception))

    def test_builtin_types_cannot_be_redefined(self):
        self.assert_rejected(
            '[node_types.index]\nprefix = "IX"\ndir = "x"\nlayer = 0\nlabel = "x"\n', "書き換えられない"
        )

    def test_prefixes_must_not_overlap(self):
        self.assert_rejected(
            '[node_types.a]\nprefix = "AA"\ndir = "a"\nlayer = 1\nlabel = "a"\n'
            '[node_types.b]\nprefix = "AA"\ndir = "b"\nlayer = 2\nlabel = "b"\n',
            "重なっている",
        )

    def test_unknown_keys_are_rejected(self):
        """綴りを間違えたキーを黙って無視すると、効いたつもりで効かない。"""
        self.assert_rejected(
            '[node_types.a]\nprefix = "AA"\ndir = "a"\nlayer = 1\nlabel = "a"\nterm = true\n',
            "知らないキー",
        )

    def test_layer_must_be_an_integer(self):
        self.assert_rejected(
            '[node_types.a]\nprefix = "AA"\ndir = "a"\nlayer = "1"\nlabel = "a"\n', "layerは整数"
        )

    def test_the_cli_reports_and_fails(self):
        self.write(schema.CONFIG_FILE, "[node_types\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("graph.tomlが読めない", output)


if __name__ == "__main__":
    unittest.main()
