"""graph.toml（プロジェクトごとのノード種別）のテスト。

**graph.tomlが無いリポジトリで、何も変わらないこと**が最も大事な性質である。
派生のほとんどはこのファイルを置かないので、そこが崩れると全派生の検証が変わる。

グラフはこの場で組み立てる。**リポジトリのdocs/を読まない。**
"""

from __future__ import annotations

import copy
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.graph import cli, schema, upgrade
from tools.graph.loader import load
from tools.graph.model import Edge, Node
from tools.graph.rules import (
    required_sections,
    rule_g012_hub_nodes,
    rule_g022_duplicate_terms,
    term_rows,
)
from tools.graph.sync import sync

from tests.helpers import make_graph

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


EPISODE_INDEX = (
    "---\nid: IDX-EP\ntype: index\ntitle: 各話\nstatus: stable\ntags: [index]\n---\n\n"
    "# 各話\n\n<!-- graph:children:start -->\n<!-- graph:children:end -->\n"
)


def episode_template(marker: str) -> str:
    return (
        "---\nid: {{ID}}\ntype: {{TYPE}}\ntitle: {{TITLE}}\nstatus: {{STATUS}}\ntags: []\n---\n\n"
        f"# {{{{TITLE}}}}\n\n## {marker}\n"
    )


def with_template(path: str) -> str:
    """CONFIGの各話の種別に、templateを足す。"""
    return CONFIG.replace('label = "各話"\n', f'label = "各話"\ntemplate = "{path}"\n')


class TypeTemplate(Base):
    """種別の`template`に書いた雛形を、`new --type`が使うこと。"""

    def setUp(self) -> None:
        super().setUp()
        self.write(schema.CONFIG_FILE, with_template("templates/episode.md"))
        for rel, text in FILES.items():
            self.write(rel, text)
        self.write("templates/episode.md", episode_template("層の雛形"))
        self.write("docs/40-episodes/index.md", EPISODE_INDEX)

    def new(self, *extra: str) -> tuple[int, str]:
        return run_cli(
            self.tmp, "new", "--type", "episode", "--id", "EP-02", "--title", "第2話", "--slug", "second", *extra
        )

    def test_the_config_sets_the_path(self):
        schema.configure(self.tmp)
        self.assertEqual(schema.TYPE_TEMPLATES, {"episode": "templates/episode.md"})

    def test_configure_without_the_key_returns_to_none(self):
        schema.configure(self.tmp)
        self.write(schema.CONFIG_FILE, CONFIG)
        schema.configure(self.tmp)
        self.assertEqual(schema.TYPE_TEMPLATES, {})

    def test_new_uses_the_template_of_the_type(self):
        self.write("docs/00-meta/templates/episode.md", episode_template("共通の雛形"))
        code, output = self.new()
        self.assertEqual(code, 0, output)
        self.assertIn("## 層の雛形", self.text("docs/40-episodes/ep-02-second.md"))

    def test_the_template_option_is_preferred(self):
        self.write("docs/00-meta/templates/short.md", episode_template("短い雛形"))
        code, output = self.new("--template", "short")
        self.assertEqual(code, 0, output)
        self.assertIn("## 短い雛形", self.text("docs/40-episodes/ep-02-second.md"))

    def test_types_without_the_key_use_the_shared_dir(self):
        self.write("docs/00-meta/templates/character.md", episode_template("共通の雛形"))
        code, output = run_cli(
            self.tmp, "new", "--type", "character", "--id", "CHR-03", "--title", "カイ", "--slug", "kai"
        )
        self.assertEqual(code, 0, output)
        self.assertIn("## 共通の雛形", self.text("docs/20-characters/chr-03-kai.md"))

    def test_a_missing_template_points_to_the_key_and_the_option(self):
        code, output = run_cli(
            self.tmp, "new", "--type", "character", "--id", "CHR-03", "--title", "カイ", "--slug", "kai"
        )
        self.assertEqual(code, 1)
        self.assertIn("雛形が無い: docs/00-meta/templates/character.md", output)
        self.assertIn("[node_types.character]にtemplate", output)
        self.assertIn("--template", output)

    def test_a_template_in_the_docs_dir_is_not_a_node(self):
        """雛形のidは{{ID}}のままなので、ノードとして読むとcheckが落ちる。"""
        self.write(schema.CONFIG_FILE, with_template("docs/40-episodes/template.md"))
        self.write("docs/40-episodes/template.md", episode_template("層の雛形"))
        (self.tmp / "docs/40-episodes/index.md").unlink()
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.write("docs/40-episodes/index.md", EPISODE_INDEX)
        code, output = self.new()
        self.assertEqual(code, 0, output)
        self.assertIn("## 層の雛形", self.text("docs/40-episodes/ep-02-second.md"))

    def test_the_path_is_counted_from_the_repository_root(self):
        """docs_dirを変えても、templateは書き直さない。"""
        self.write(schema.CONFIG_FILE, 'docs_dir = "design"\n' + with_template("templates/episode.md"))
        for rel, text in FILES.items():
            self.write("design/" + rel.removeprefix("docs/"), text)
        self.write("design/40-episodes/index.md", EPISODE_INDEX)
        code, output = self.new()
        self.assertEqual(code, 0, output)
        self.assertIn("## 層の雛形", self.text("design/40-episodes/ep-02-second.md"))


class HubExempt(Base):
    """`hub_exempt = true`の種別からの依存を、G012が数えないこと。"""

    CONFIG = """
[node_types.character]
prefix = "CHR"
dir = "20-characters"
layer = 20
label = "人物"

[node_types.episode]
prefix = "EP"
dir = "40-episodes"
layer = 40
label = "各話"
{flag}
"""

    def g012(self, flag: str) -> list[str]:
        self.write(schema.CONFIG_FILE, self.CONFIG.format(flag=flag))
        schema.configure(self.tmp)
        nodes = [Node("CHR-01", "character", "主人公", "stable", [], self.tmp / "c.md", "c.md", {}, "")]
        # 派生はMAX_INCOMING_DEPENDENCIESを上げてよいので、件数は上限から決める。
        for n in range(1, schema.MAX_INCOMING_DEPENDENCIES + 2):
            node_id = f"EP-{n:03d}"
            nodes.append(
                Node(node_id, "episode", node_id, "stable", [], self.tmp / f"{n}.md", f"{n}.md", {}, "",
                     [Edge(node_id, "CHR-01", "depends_on", "frontmatter")])
            )
        return [issue.code for issue in rule_g012_hub_nodes(make_graph(nodes))]

    def test_dependencies_from_exempt_types_are_not_counted(self):
        self.assertEqual(self.g012("hub_exempt = true"), [])

    def test_other_types_are_still_counted(self):
        self.assertEqual(self.g012(""), ["G012"])

    def test_default_types_have_no_exempt_types(self):
        schema.configure(self.tmp)
        self.assertEqual(schema.HUB_EXEMPT_TYPES, ())


class Thresholds(Base):
    """[thresholds]で、schema.pyを書き換えずにしきい値を変えられること。

    既定の値（8と90）は決めつけない。schema.pyを書き換えたままの派生でも通るようにする。
    """

    def g012(self, dependents: int) -> list[str]:
        nodes = [Node("DOM-01", "domain", "中心", "stable", [], self.tmp / "d.md", "d.md", {}, "")]
        for n in range(1, dependents + 1):
            node_id = f"UC-{n:02d}"
            nodes.append(
                Node(node_id, "usecase", node_id, "stable", [], self.tmp / f"{n}.md", f"{n}.md", {}, "",
                     [Edge(node_id, "DOM-01", "depends_on", "frontmatter")])
            )
        return [issue.code for issue in rule_g012_hub_nodes(make_graph(nodes))]


    def test_thresholds_change_the_g012_limit(self):
        self.write(schema.CONFIG_FILE, "[thresholds]\nmax_incoming_dependencies = 12\n")
        schema.configure(self.tmp)
        self.assertEqual(self.g012(12), [])
        self.assertEqual(self.g012(13), ["G012"])

    def test_thresholds_alone_keep_the_template_types(self):
        """[thresholds]だけを書いても、種別は差し替わらない。"""
        before = copy.deepcopy(schema.NODE_TYPES)
        self.write(schema.CONFIG_FILE, "[thresholds]\nstale_after_days = 30\n")
        schema.configure(self.tmp)
        self.assertEqual(schema.STALE_AFTER_DAYS, 30)
        self.assertEqual(schema.MAX_INCOMING_DEPENDENCIES, schema._DEFAULTS["MAX_INCOMING_DEPENDENCIES"])
        self.assertEqual(schema.NODE_TYPES, before)

    def test_configure_without_the_table_returns_to_defaults(self):
        self.write(schema.CONFIG_FILE, "[thresholds]\nmax_incoming_dependencies = 21\nstale_after_days = 30\n")
        schema.configure(self.tmp)
        (self.tmp / schema.CONFIG_FILE).unlink()
        schema.configure(self.tmp)
        self.assertEqual(schema.MAX_INCOMING_DEPENDENCIES, schema._DEFAULTS["MAX_INCOMING_DEPENDENCIES"])
        self.assertEqual(schema.STALE_AFTER_DAYS, schema._DEFAULTS["STALE_AFTER_DAYS"])


class TermTable(Base):
    """[terms]で、schema.pyを書き換えずに用語表の見出しと列名を変えられること。"""

    BODY = (
        "## Terms\n\n"
        "| Term | Meaning | Former names |\n"
        "| --- | --- | --- |\n"
        "| 予約 | 席を押さえること | 仮押さえ |\n"
    )

    def configure_english(self) -> None:
        self.write(
            schema.CONFIG_FILE,
            '[terms]\nsection_heading = "Terms"\nterm_column = "Term"\n'
            'meaning_column = "Meaning"\nold_name_column = "Former names"\n',
        )
        schema.configure(self.tmp)

    def test_terms_change_the_heading_and_columns(self):
        self.configure_english()
        rows = term_rows(self.BODY)
        self.assertEqual([row[schema.TERM_COLUMN] for row in rows], ["予約"])
        self.assertEqual(rows[0][schema.TERM_MEANING_COLUMN], "席を押さえること")
        self.assertEqual(schema.TERM_OLD_NAME_COLUMNS[0], "Former names")

    def test_the_old_column_name_is_still_read(self):
        """1.19までの列名は、列名を差し替えても読み続ける。"""
        self.configure_english()
        self.assertIn(schema.TERM_FORBIDDEN_COLUMN, schema.TERM_OLD_NAME_COLUMNS)

    def test_the_default_heading_is_no_longer_read(self):
        self.configure_english()
        self.assertEqual(term_rows("## 用語\n\n| 用語 | 意味 |\n| --- | --- |\n| 予約 | 席 |\n"), [])

    def test_terms_alone_keep_the_template_types(self):
        before = copy.deepcopy(schema.NODE_TYPES)
        self.configure_english()
        self.assertEqual(schema.NODE_TYPES, before)

    def test_configure_without_the_table_returns_to_defaults(self):
        self.configure_english()
        (self.tmp / schema.CONFIG_FILE).unlink()
        schema.configure(self.tmp)
        self.assertEqual(schema.TERM_SECTION_HEADING, schema._DEFAULTS["TERM_SECTION_HEADING"])
        self.assertEqual(schema.TERM_COLUMN, schema._DEFAULTS["TERM_COLUMN"])
        self.assertEqual(
            schema.TERM_OLD_NAME_COLUMNS,
            (schema._DEFAULTS["TERM_OLD_NAME_COLUMN"], schema.TERM_FORBIDDEN_COLUMN),
        )


class DefaultRequiredSections(Base):
    """[required_sections]で、既定の種別のまま必須の節を変えられること。"""

    def node(self, node_type: str, *, refines: bool = False) -> Node:
        edges = [Edge("DOM-02", "DOM-01", "refines", "frontmatter")] if refines else []
        return Node("DOM-02", node_type, "x", "stable", [], self.tmp / "x.md", "x.md", {}, "", edges)

    def test_required_sections_replace_only_the_written_types(self):
        before = dict(schema.REQUIRED_SECTIONS)
        self.write(schema.CONFIG_FILE, '[required_sections]\ndomain = ["定義", "用語"]\nusecase = []\n')
        schema.configure(self.tmp)
        self.assertEqual(required_sections(self.node("domain")), ("定義", "用語"))
        self.assertEqual(required_sections(self.node("usecase")), ())
        self.assertEqual(schema.REQUIRED_SECTIONS["adr"], before["adr"])

    def test_required_sections_refined(self):
        self.write(schema.CONFIG_FILE, '[required_sections_refined]\ndomain = ["用語"]\n')
        schema.configure(self.tmp)
        self.assertEqual(required_sections(self.node("domain", refines=True)), ("用語",))

    def test_configure_without_the_table_returns_to_defaults(self):
        before = dict(schema.REQUIRED_SECTIONS)
        self.write(schema.CONFIG_FILE, "[required_sections]\ndomain = []\n")
        schema.configure(self.tmp)
        (self.tmp / schema.CONFIG_FILE).unlink()
        schema.configure(self.tmp)
        self.assertEqual(schema.REQUIRED_SECTIONS, before)


class DocsDir(Base):
    """docs_dirで、検証する文書のフォルダを変える。

    implemented_byのパスは、文書のフォルダではなく、リポジトリの根から数える。
    """

    def setUp(self) -> None:
        super().setUp()
        self.write(schema.CONFIG_FILE, 'docs_dir = "design"\n' + CONFIG)
        for rel, text in FILES.items():
            self.write("design/" + rel.removeprefix("docs/"), text)

    def test_the_config_changes_the_docs_dir(self):
        schema.configure(self.tmp)
        self.assertEqual(schema.DOCS_DIR, "design")
        rels = {node.rel for node in load(self.tmp).nodes.values()}
        self.assertIn("design/20-characters/chr-01-anne.md", rels)

    def test_configure_without_the_key_returns_to_docs(self):
        schema.configure(self.tmp)
        (self.tmp / schema.CONFIG_FILE).unlink()
        schema.configure(self.tmp)
        self.assertEqual(schema.DOCS_DIR, "docs")

    def test_check_reads_only_the_configured_dir(self):
        """docs/に壊れた文書があっても、検証するのはdesign/だけである。"""
        self.write("docs/broken.md", "フロントマターが無い\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)

    def test_a_missing_dir_is_reported_by_its_name(self):
        shutil.rmtree(self.tmp / "design")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("design/が見つからない", output)
        self.assertIn("G000: design/の構造が不正", output)
        self.assertNotIn("docs/", output)

    def test_upgrade_points_to_the_steps_in_the_docs_dir(self):
        result = {
            "layers": [{"name": "graph-doc-template", "local": "1.0.0", "remote": "1.1.0", "entries": []}],
            "ahead": False,
            "behind": True,
            "breaking": False,
            "label": "graph-doc-template 1.1.0",
            "files": [],
        }
        with mock.patch.object(upgrade, "inspect", return_value=result):
            code, output = run_cli(self.tmp, "upgrade")
        self.assertEqual(code, 0, output)
        self.assertIn("design/00-meta/template-upgrade.md", output)
        self.assertNotIn("docs/", output)

    def test_new_help_does_not_name_docs_as_the_only_place(self):
        """--helpは設定を読む前に作るので、docs/は既定として書く。"""
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            cli.main(["new", "--help"])
        help_text = " ".join(out.getvalue().split())
        self.assertNotIn("docs/00-meta", help_text)
        self.assertIn("既定はdocs/", help_text)

    def test_the_type_dir_is_under_the_docs_dir(self):
        (self.tmp / "design/40-episodes/ep-01-first.md").rename(self.tmp / "design/ep-01-first.md")
        self.write("design/index.md", self.text("design/index.md").replace("./40-episodes/", "./"))
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("design/40-episodes/に置く", output)

    def test_implemented_by_is_counted_from_the_repository_root(self):
        self.write("src/episode.gd", "extends Node\n")
        path = "design/40-episodes/ep-01-first.md"
        self.write(
            path, self.text(path).replace("depends_on:", "implemented_by:\n  - src/episode.gd\ndepends_on:")
        )
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.assertNotIn("G016", output)

    def test_new_creates_the_node_in_the_docs_dir(self):
        self.write(
            "design/00-meta/templates/episode.md",
            "---\nid: {{ID}}\ntype: {{TYPE}}\ntitle: {{TITLE}}\nstatus: {{STATUS}}\ntags: []\n---\n\n# {{TITLE}}\n",
        )
        self.write(
            "design/40-episodes/index.md",
            "---\nid: IDX-EP\ntype: index\ntitle: 各話\nstatus: stable\ntags: [index]\n---\n\n"
            "# 各話\n\n<!-- graph:children:start -->\n<!-- graph:children:end -->\n",
        )
        code, output = run_cli(
            self.tmp, "new", "--type", "episode", "--id", "EP-02", "--title", "第2話", "--slug", "second"
        )
        self.assertEqual(code, 0, output)
        self.assertTrue((self.tmp / "design/40-episodes/ep-02-second.md").is_file())
        self.assertFalse((self.tmp / "docs").exists())

    def test_a_nested_dir_can_be_used(self):
        (self.tmp / "game").mkdir()
        (self.tmp / "design").rename(self.tmp / "game/design")
        self.write(schema.CONFIG_FILE, 'docs_dir = "game/design/"\n' + CONFIG)
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.assertEqual(schema.DOCS_DIR, "game/design")


class Exclude(Base):
    """excludeに書いたパスを、グラフに含めない。

    ほかの道具から取り込んだMarkdownは、フロントマターが無くてもノードではないので、
    G001で止めない。取り込んだファイルなので、linkifyなどで書き換えもしない。
    """

    def setUp(self) -> None:
        super().setUp()
        self.write(
            schema.CONFIG_FILE,
            'exclude = ["docs/vendor/", "docs/CLAUDE.md"]\n' + CONFIG,
        )
        for rel, text in FILES.items():
            self.write(rel, text)
        self.write("docs/vendor/godot/api.md", "フロントマターが無い\n")
        self.write("docs/CLAUDE.md", "フロントマターが無い。[[CHR-01]]を指す\n")

    def test_the_config_sets_the_paths(self):
        schema.configure(self.tmp)
        self.assertEqual(schema.EXCLUDE, ("docs/vendor", "docs/CLAUDE.md"))

    def test_configure_without_the_key_returns_to_none(self):
        schema.configure(self.tmp)
        (self.tmp / schema.CONFIG_FILE).unlink()
        schema.configure(self.tmp)
        self.assertEqual(schema.EXCLUDE, ())

    def test_check_skips_the_excluded_files(self):
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.assertNotIn("G001", output)

    def test_check_still_fails_without_the_key(self):
        """外さなければ、これまでどおりG001で止まる。"""
        self.write(schema.CONFIG_FILE, CONFIG)
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("docs/vendor/godot/api.md", output)
        self.assertIn("docs/CLAUDE.md", output)

    def test_paths_are_matched_by_segment(self):
        """docs/vendorは、docs/vendor2に当たらない。"""
        self.write("docs/vendor2/api.md", "フロントマターが無い\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("docs/vendor2/api.md", output)

    def test_the_template_dir_is_still_excluded(self):
        self.write("docs/00-meta/templates/x.md", "フロントマターが無い\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)

    def test_check_does_not_read_tables_in_the_excluded_files(self):
        self.write("docs/vendor/table.md", "| a |\n| --- |\n\n| b |\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)
        self.assertNotIn("G019", output)

    def test_linkify_does_not_rewrite_the_excluded_files(self):
        before = self.text("docs/CLAUDE.md")
        code, output = run_cli(self.tmp, "linkify")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.text("docs/CLAUDE.md"), before)

    def test_the_paths_follow_the_docs_dir(self):
        """docs_dirを変えたら、excludeもそのフォルダの下を書く。"""
        self.write(
            schema.CONFIG_FILE,
            'docs_dir = "design"\nexclude = ["design/registry"]\n' + CONFIG,
        )
        for rel, text in FILES.items():
            self.write("design/" + rel.removeprefix("docs/"), text)
        self.write("design/registry/notes.md", "フロントマターが無い\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 0, output)


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

    def test_thresholds_reject_unknown_keys(self):
        self.assert_rejected("[thresholds]\nmax_incoming_dependency = 12\n", "知らないキー")

    def test_thresholds_must_be_positive_integers(self):
        for value in ("0", '"12"', "true", "1.5"):
            with self.subTest(value=value):
                self.assert_rejected(
                    f"[thresholds]\nmax_incoming_dependencies = {value}\n", "1以上の整数"
                )

    def test_terms_reject_unknown_keys(self):
        self.assert_rejected('[terms]\nheading = "Terms"\n', "知らないキー")

    def test_terms_must_be_non_empty_strings(self):
        for value in ('""', "1", '"a | b"'):
            with self.subTest(value=value):
                self.assert_rejected(f"[terms]\nterm_column = {value}\n", "空でない文字列")

    def test_term_columns_must_not_overlap(self):
        self.assert_rejected('[terms]\nmeaning_column = "用語"\n', "列名が重なっている")

    def test_required_sections_reject_unknown_types(self):
        self.assert_rejected('[required_sections]\ncharacter = ["人物像"]\n', "知らない種別")

    def test_required_sections_must_be_arrays_of_headings(self):
        self.assert_rejected('[required_sections]\ndomain = "定義"\n', "見出しの文字列の配列")

    def test_required_sections_cannot_be_mixed_with_node_types(self):
        """種別を差し替えたら、必須の節は[node_types]の各種別に書く。"""
        self.assert_rejected(CONFIG + '\n[required_sections]\nworld = ["用語"]\n', "一緒には書けない")

    def test_docs_dir_must_stay_in_the_repository(self):
        """根の外の文書を、このリポジトリのグラフとして検証させない。"""
        for value in ('""', "1", '"/design"', '"../design"', '"design/../docs"', '"./design"', '"C:/design"'):
            with self.subTest(value=value):
                self.assert_rejected(f"docs_dir = {value}\n", "docs_dir")

    def test_exclude_must_be_paths_in_the_docs_dir(self):
        """根の外のパスと、文書のフォルダの外のパスを断る。"""
        for value in (
            '"docs/vendor"',
            "[1]",
            '[""]',
            '["/docs/vendor"]',
            '["docs/../vendor"]',
            '["C:/docs"]',
            '["vendor"]',
            '["docs"]',
        ):
            with self.subTest(value=value):
                self.assert_rejected(f"exclude = {value}\n", "exclude")

    def test_exclude_is_checked_against_the_changed_docs_dir(self):
        """docs_dirを変えたのにexcludeを直し忘れたら、何も外さないまま通さない。"""
        self.assert_rejected('docs_dir = "design"\nexclude = ["docs/vendor"]\n', "design/")

    def test_the_template_must_exist(self):
        """指した雛形が無ければ、newを待たずに、設定を読むときに止める。"""
        self.assert_rejected(
            '[node_types.a]\nprefix = "AA"\ndir = "a"\nlayer = 1\nlabel = "a"\ntemplate = "templates/a.md"\n',
            "templateに書いた雛形が無い: templates/a.md",
        )

    def test_the_template_must_stay_in_the_repository(self):
        self.write("templates/a.md", "雛形\n")
        for value in ('""', "1", '"/templates/a.md"', '"../templates/a.md"', '"C:/templates/a.md"'):
            with self.subTest(value=value):
                self.assert_rejected(
                    f'[node_types.a]\nprefix = "AA"\ndir = "a"\nlayer = 1\nlabel = "a"\ntemplate = {value}\n',
                    "template",
                )

    def test_the_cli_reports_and_fails(self):
        self.write(schema.CONFIG_FILE, "[node_types\n")
        code, output = run_cli(self.tmp, "check", "--no-history")
        self.assertEqual(code, 1)
        self.assertIn("graph.tomlが読めない", output)


if __name__ == "__main__":
    unittest.main()
