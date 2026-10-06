"""PRの参照の検査（`.github/scripts/check_refs.py`）のテスト。

**文の途中の「なし」で、照合を飛ばさないこと**が、最も大事な性質である。
部分一致で見ていた頃は、「問題なし」「更新なし」「みなし」でも照合が飛び、
派生のPR 30件のうち10件が照合されていなかった（意図したものは1件）。
"""

from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "check_refs.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_refs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SCRIPT.exists(), "check_refs.pyを消したリポジトリでは飛ばす")
class DeclaresNone(unittest.TestCase):
    def setUp(self):
        self.refs = load_script()

    def test_a_line_that_starts_with_none_is_a_declaration(self):
        for text in (
            "なし",
            "ノード: なし（検証ツールのしきい値）",
            "## 対応するノード\n\nなし\n",
            "なし。依存の更新だけ",
            "N/A",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.refs.declares_none(text))

    def test_none_in_the_middle_of_a_sentence_is_not(self):
        """実際に、照合を飛ばしていた書き方。"""
        for text in (
            "- `check --strict`: 184 ノード、問題なし",
            "更新なし（すべて最新）",
            "報告が来なければ表明とみなし、確定する",
            "| py あり / なし | 2 通り |",
        ):
            with self.subTest(text=text):
                self.assertFalse(self.refs.declares_none(text))

    def test_the_template_guidance_in_a_comment_is_not(self):
        text = "<!-- 文書に対応が無い変更は\nなし と書く -->\nUC-01 を直した"
        self.assertFalse(self.refs.declares_none(text))


@unittest.skipUnless(SCRIPT.exists(), "check_refs.pyを消したリポジトリでは飛ばす")
class Check(unittest.TestCase):
    def setUp(self):
        self.refs = load_script()

    def run_check(self, text, known=frozenset({"UC-01", "ADR-0001"})):
        with redirect_stdout(io.StringIO()):
            return self.refs.check(text, set(known))

    def test_ids_in_the_title_are_read(self):
        self.assertEqual(self.run_check("予約を直す。UC-01 / ADR-0001\n本文"), 0)

    def test_a_missing_id_fails_even_if_the_body_says_no_problem(self):
        """「問題なし」を貼っても、書き間違えたidは見逃さない。"""
        self.assertEqual(self.run_check("予約を直す。UC-99\n- check: 問題なし"), 1)

    def test_no_id_and_no_declaration_fails(self):
        self.assertEqual(self.run_check("設定を直す\n本文"), 1)

    def test_a_declaration_passes_without_ids(self):
        self.assertEqual(self.run_check("依存を上げる\nノード: なし"), 0)


@unittest.skipUnless(SCRIPT.exists(), "check_refs.pyを消したリポジトリでは飛ばす")
class DeclaredPart(unittest.TestCase):
    """「対応するノード」の節があれば、題とその節だけを照合する。"""

    def setUp(self):
        self.refs = load_script()

    def run_check(self, title, body, known=frozenset({"UC-01", "ADR-0001"})):
        with redirect_stdout(io.StringIO()):
            return self.refs.check(self.refs.declared_part(title, body), set(known))

    def test_an_example_id_outside_the_section_is_not_read(self):
        body = (
            "idは`EP-001`のように3桁で振る\n\n## 対応するノード\n\nUC-01\n\n"
            "## 確かめたこと\n\n- EP-002も作れる\n"
        )
        self.assertEqual(self.run_check("予約を直す", body), 0)

    def test_ids_in_code_spans_inside_the_section_are_read(self):
        body = "## 対応するノード\n\n`UC-01`、`UC-99`\n"
        self.assertEqual(self.run_check("予約を直す", body), 1)

    def test_none_inside_the_section(self):
        body = "例: UC-99\n\n## 対応するノード\n\nなし（依存の更新）\n"
        self.assertEqual(self.run_check("依存を上げる", body), 0)

    def test_the_template_guidance_is_not_read(self):
        body = "## 対応するノード\n\n<!-- idを書く（DOM-07 / CON-08） -->\nUC-01\n"
        self.assertEqual(self.run_check("予約を直す", body), 0)

    def test_without_the_section_the_whole_body_is_read(self):
        self.assertEqual(self.run_check("予約を直す", "本文でUC-99を直した"), 1)


if __name__ == "__main__":
    unittest.main()
