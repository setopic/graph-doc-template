"""upgradeが、テンプレートの層ごとにバージョンを比べるときのテスト（setopic/graph-doc-template#125）。

下の層（graph-doc-template）のバージョンだけを比べると、上の層（graph-project-template）だけの
変更を「取り込むものは無い」と誤って伝える。上の層は`tools/graph/layers/<層の名前>.toml`に
バージョンと変更履歴の場所を書き、`upgrade`は層ごとに比べる。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.graph import upgrade

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}

LAYER_PATH = "tools/graph/layers/graph-project-template.toml"
PROJECT_REPOSITORY = "https://github.com/setopic/graph-project-template.git"


def run(cwd: Path, *args: str) -> None:
    subprocess.run(list(args), cwd=cwd, check=True, capture_output=True, env=ENV)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def layer_toml(version: str) -> str:
    return (
        'name = "graph-project-template"\n'
        'label = "project"\n'
        'below = "graph-doc-template"\n'
        f'version = "{version}"\n'
        'changelog = "PROJECT_TEMPLATE_CHANGELOG.md"\n'
        f'repository = "{PROJECT_REPOSITORY}"\n'
    )


def changelog(*versions: str) -> str:
    return "# 変更履歴\n\n" + "".join(f"## {v} — 2026-10-21\n\n{v}の変更\n\n" for v in versions)


@unittest.skipUnless(shutil.which("git"), "gitが無い")
class LayerTest(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.upstream = base / "upstream"
        self.derived = base / "derived"
        run(base, "git", "init", "-q", "-b", "main", str(self.upstream))

    def commit_upstream(self, files: dict[str, str]) -> None:
        for path, text in files.items():
            write(self.upstream / path, text)
        run(self.upstream, "git", "add", ".")
        run(self.upstream, "git", "commit", "-q", "-m", "up")

    def clone(self) -> None:
        run(self.upstream.parent, "git", "clone", "-q", "-o", "template", str(self.upstream), str(self.derived))

    def fetch(self) -> None:
        run(self.derived, "git", "fetch", "-q", "template")

    def by_name(self) -> dict[str, dict]:
        return {layer["name"]: layer for layer in upgrade.compare(self.derived)}

    def two_layers(self, base: str, project: str) -> dict[str, str]:
        return {
            upgrade.VERSION_PATH: f'TEMPLATE_VERSION = "{base}"\n',
            upgrade.CHANGELOG_PATH: changelog(base),
            LAYER_PATH: layer_toml(project),
            "PROJECT_TEMPLATE_CHANGELOG.md": changelog("0.1.0", "0.2.0"),
        }

    def test_upper_layer_only_change_is_behind(self) -> None:
        """上の層だけが上がっても、遅れていると知らせ、その層の変更履歴を出す。"""
        self.commit_upstream(self.two_layers("1.0.0", "0.1.0"))
        self.clone()
        self.commit_upstream({LAYER_PATH: layer_toml("0.2.0")})
        self.fetch()

        layers = self.by_name()
        self.assertFalse(layers["graph-doc-template"]["behind"])
        self.assertTrue(layers["graph-project-template"]["behind"])
        self.assertEqual(
            [v for v, _ in layers["graph-project-template"]["entries"]], ["0.2.0"]
        )
        self.assertEqual(upgrade.inspect_label(self.derived), "project-0.2.0")

    def test_label_lists_every_behind_layer(self) -> None:
        """両方の層が上がったら、下の層から順に並べる。"""
        self.commit_upstream(self.two_layers("1.0.0", "0.1.0"))
        self.clone()
        self.commit_upstream(self.two_layers("1.1.0", "0.2.0"))
        self.fetch()
        self.assertEqual(upgrade.inspect_label(self.derived), "1.1.0-project-0.2.0")

    def test_base_layer_only_keeps_plain_version(self) -> None:
        """下の層だけなら、これまでどおりバージョンだけにする。"""
        self.commit_upstream(self.two_layers("1.0.0", "0.1.0"))
        self.clone()
        self.commit_upstream({upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.1"\n'})
        self.fetch()
        self.assertEqual(upgrade.inspect_label(self.derived), "1.0.1")

    def test_new_layer_counts_as_behind(self) -> None:
        """上の層の宣言をはじめて取り込むときも、遅れていると知らせる。"""
        self.commit_upstream({upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.0"\n'})
        self.clone()
        self.commit_upstream({LAYER_PATH: layer_toml("0.2.0")})
        self.fetch()

        layer = self.by_name()["graph-project-template"]
        self.assertTrue(layer["behind"])
        self.assertIsNone(layer["local"])
        self.assertEqual(layer["entries"], [])

    def test_local_only_layer_is_ignored(self) -> None:
        """層のテンプレート本体では、自分の層は比べない。templateは1つ下の層を指す。"""
        self.commit_upstream({upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.0"\n'})
        self.clone()
        write(self.derived / LAYER_PATH, layer_toml("0.1.0"))
        self.assertEqual(list(self.by_name()), ["graph-doc-template"])
        self.assertEqual(upgrade.inspect_label(self.derived), "")

    def test_missing_remote_points_to_top_layer(self) -> None:
        """リモートが無いときは、いちばん上の層のURLを案内する。"""
        self.commit_upstream(self.two_layers("1.0.0", "0.1.0"))
        self.clone()
        run(self.derived, "git", "remote", "remove", "template")
        with self.assertRaises(upgrade.UpgradeError) as ctx:
            upgrade.inspect_label(self.derived)
        self.assertIn(PROJECT_REPOSITORY, str(ctx.exception))


class ReadLayersTest(unittest.TestCase):
    def test_order_follows_below(self) -> None:
        files = {
            upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.0"\n',
            f"{upgrade.LAYERS_DIR}/a.toml": layer_toml("0.1.0")
            .replace("graph-project-template", "top")
            .replace('below = "graph-doc-template"', 'below = "middle"')
            .replace('label = "project"', 'label = "top"'),
            f"{upgrade.LAYERS_DIR}/b.toml": layer_toml("0.1.0").replace(
                "graph-project-template", "middle"
            ),
        }
        layers = upgrade.read_layers(files.get, ["a.toml", "b.toml"])
        self.assertEqual([layer.name for layer in layers], ["graph-doc-template", "middle", "top"])

    def test_bad_label_is_rejected(self) -> None:
        files = {
            upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.0"\n',
            LAYER_PATH: layer_toml("0.1.0").replace('label = "project"', 'label = "Project_1"'),
        }
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.read_layers(files.get, ["graph-project-template.toml"])

    def test_missing_key_is_rejected(self) -> None:
        files = {
            upgrade.VERSION_PATH: 'TEMPLATE_VERSION = "1.0.0"\n',
            LAYER_PATH: 'name = "graph-project-template"\n',
        }
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.read_layers(files.get, ["graph-project-template.toml"])


if __name__ == "__main__":
    unittest.main()
