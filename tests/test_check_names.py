"""ブランチ名とコミットの1行目の検査（`.github/scripts/check_names.py`）のテスト。

**書き手が選べないものを、落とさないこと**が大事な性質である。`claude/`のブランチ名と、
取り込みのPRに入る上流のコミットで落ちると、決まりを守っても通せないPRができる。
"""

from __future__ import annotations

import importlib.util
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.graph import schema

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_names.py"
TYPES = schema.COMMIT_TYPES


def load_script():
    spec = importlib.util.spec_from_file_location("check_names", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SCRIPT.exists(), "check_names.pyを消したリポジトリでは飛ばす")
class Subject(unittest.TestCase):
    def setUp(self):
        self.names = load_script()

    def test_accepted(self):
        for subject in (
            "feat(WLD-13): 武器と取り締まりの決まりを作る（#40）",
            "fix: 1.36.14 サンプルを配るテンプレートではreset-samplesを回さない、と手順に書く（#117）",
            "docs: 用語表の誤字を直す",
            "chore(ADR-0089): 依存を上げる",
        ):
            with self.subTest(subject=subject):
                self.assertIsNone(self.names.check_subject(subject, TYPES))

    def test_rejected(self):
        for subject in (
            "サンプルを配るテンプレートではreset-samplesを回さない",  # いまの書き方
            "feature: 種類の綴りが違う",
            "feat(1.36.14): 版は括弧に入れない",
            "feat:空白が無い",
            "Feat: 大文字で始まる",
            "テンプレートの1.36.14を取り込む",
        ):
            with self.subTest(subject=subject):
                self.assertIsNotNone(self.names.check_subject(subject, TYPES))

    def test_extra_types(self):
        self.assertIsNotNone(self.names.check_subject("episode(EP-03): 第3話を書く", TYPES))
        self.assertIsNone(self.names.check_subject("episode(EP-03): 第3話を書く", TYPES + ("episode",)))


@unittest.skipUnless(SCRIPT.exists(), "check_names.pyを消したリポジトリでは飛ばす")
class Title(unittest.TestCase):
    def setUp(self):
        self.names = load_script()

    def test_template_requires_a_version(self):
        repo = self.names.TEMPLATE_REPOSITORY
        self.assertIsNone(self.names.check_title("fix: 1.36.14 手順に書く（#117）", TYPES, repo))
        self.assertIsNotNone(self.names.check_title("fix: 手順に書く（#117）", TYPES, repo))

    def test_derived_does_not(self):
        self.assertIsNone(self.names.check_title("fix: 手順に書く（#117）", TYPES, "setopic/noir-sf"))


@unittest.skipUnless(SCRIPT.exists(), "check_names.pyを消したリポジトリでは飛ばす")
class Branch(unittest.TestCase):
    def setUp(self):
        self.names = load_script()

    def test_accepted(self):
        for branch in (
            "feat/121-branch-commit-rules",
            "fix/g013-old-names",
            "chore/template-1.37.0",
            "claude/confident-wescoff-08c4e3",
            "claude/何でもよい",
        ):
            with self.subTest(branch=branch):
                self.assertIsNone(self.names.check_branch(branch, TYPES))

    def test_rejected(self):
        for branch in (
            "branch-commit-rules",  # 種類が無い
            "121-branch-commit-rules",
            "feature/121-rules",
            "feat/121",  # 内容が無い
            "feat/121-Branch-Rules",
            "feat/121_branch_rules",
        ):
            with self.subTest(branch=branch):
                self.assertIsNotNone(self.names.check_branch(branch, TYPES))

    def test_template_import_skips_commits(self):
        self.assertTrue(self.names.skips_commits("chore/template-1.37.0"))
        self.assertFalse(self.names.skips_commits("chore/update-deps"))
        self.assertFalse(self.names.skips_commits("chore/template-latest"))


@unittest.skipUnless(SCRIPT.exists(), "check_names.pyを消したリポジトリでは飛ばす")
class Run(unittest.TestCase):
    def setUp(self):
        self.names = load_script()

    def run_quietly(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.names.run(*args)
        return code, out.getvalue()

    def test_passes(self):
        code, _ = self.run_quietly(
            "feat/121-branch-commit-rules",
            "feat: 1.37.0 ブランチ名とコミットの1行目の決まりを足す（#121）",
            ["feat(META-07): ブランチ名の決まりを書く（#121）"],
            TYPES,
            self.names.TEMPLATE_REPOSITORY,
        )
        self.assertEqual(code, 0)

    def test_reports_every_problem(self):
        code, out = self.run_quietly("rules", "決まりを足す", ["決まりを書く"], TYPES)
        self.assertEqual(code, 1)
        self.assertIn("ブランチ名 rules", out)
        self.assertIn("PRの題 決まりを足す", out)
        self.assertIn("コミット 決まりを書く", out)


class GraphToml(unittest.TestCase):
    """`graph.toml`の`[commit]`の表。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.addCleanup(schema.reset)

    def configure(self, text: str) -> None:
        (self.tmp / "graph.toml").write_text(text, encoding="utf-8", newline="\n")
        schema.configure(self.tmp)

    def test_without_graph_toml_only_the_standard_types(self):
        schema.configure(self.tmp)
        self.assertEqual(schema.COMMIT_TYPES, ("feat", "fix", "docs", "refactor", "test", "ci", "chore"))

    def test_extra_types_are_added(self):
        self.configure('[commit]\nextra_types = ["episode"]\n')
        self.assertEqual(schema.COMMIT_TYPES[-1], "episode")
        self.assertIn("feat", schema.COMMIT_TYPES)

    def test_reset_restores_the_standard_types(self):
        self.configure('[commit]\nextra_types = ["episode"]\n')
        schema.reset()
        self.assertNotIn("episode", schema.COMMIT_TYPES)

    def test_wrong_tables_are_refused(self):
        for text in (
            "[commit]\nextra_type = [\"episode\"]\n",  # 綴りの誤り
            "[commit]\nextra_types = \"episode\"\n",
            "[commit]\nextra_types = [\"Episode\"]\n",
            "[commit]\nextra_types = [\"feat\"]\n",
            "[commit]\nextra_types = [\"episode\", \"episode\"]\n",
            "commit = 1\n",
        ):
            with self.subTest(text=text):
                with self.assertRaises(schema.ConfigError):
                    self.configure(text)

    def test_node_types_are_unchanged(self):
        before = dict(schema.NODE_TYPES)
        self.configure('[commit]\nextra_types = ["episode"]\n')
        self.assertEqual(dict(schema.NODE_TYPES), before)


if __name__ == "__main__":
    unittest.main()
