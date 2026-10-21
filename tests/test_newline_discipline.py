"""書き出しの改行と文字コードが揃っているかを機械で見る。

**Windowsで`write_text(text, encoding="utf-8")`はLFをCRLFに変換して書く。**
`.gitattributes`の`text=auto eol=lf`がコミット時に正規化するため
`git status`はきれいなままで、作業ツリーだけがCRLFに化ける。
**壊れていることが表に出ないので、目視では見つからない。**

実際に`linkify`の書き出し1箇所だけがこの指定を落としていて、
他の8箇所は手で気を付けて書かれていた。手で気を付ける方式は、
**書き出しを足すたびに同じ確率で失敗する。** だから機械で見る。

`open()`も同じで、テキストモードで書くなら`newline`と`encoding`が要る。
バイナリ（`"b"`）は変換が起きないので対象外。
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools" / "graph"


def _callee(func: ast.expr) -> str:
    """`a.b.write_text(...)`の`write_text`、`open(...)`の`open`を返す。"""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _literal(node: ast.expr | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _mode(call: ast.Call) -> str:
    """`open`のモード。位置引数の2つ目か`mode=`。省略時は読み取り。"""
    if len(call.args) >= 2:
        found = _literal(call.args[1])
        if isinstance(found, str):
            return found
    found = _literal(_keyword(call, "mode"))
    return found if isinstance(found, str) else "r"


def _text_writes(tree: ast.AST) -> list[tuple[ast.Call, str]]:
    """テキストとして書き出している呼び出しを拾う。"""
    found: list[tuple[ast.Call, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node.func)
        if name == "write_text":
            found.append((node, "write_text"))
        elif name == "open":
            mode = _mode(node)
            if "b" in mode:
                continue  # バイナリは変換が起きない
            if any(flag in mode for flag in "wax"):
                found.append((node, "open"))
    return found


class NewlineDisciplineTest(unittest.TestCase):
    def _offenders(self, keyword: str, expected: object) -> list[str]:
        bad: list[str] = []
        for path in sorted(TOOLS_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for call, kind in _text_writes(tree):
                if _literal(_keyword(call, keyword)) != expected:
                    bad.append(f"{path.name}:{call.lineno} ({kind})")
        return bad

    def test_every_text_write_pins_lf(self) -> None:
        """改行を渡していない書き出しがあれば落とす。

        既定に任せるとWindowsだけCRLFになる。**プラットフォームで
        結果が変わる書き出しを残さない。**
        """
        bad = self._offenders("newline", "\n")
        self.assertEqual(
            bad,
            [],
            "テキストの書き出しにはnewline=\"\\n\"が要る。"
            f" 指定の無い箇所: {bad}",
        )

    def test_every_text_write_pins_utf8(self) -> None:
        """文字コードも同じ理由で明示する。既定はWindowsでcp932になる。"""
        bad = self._offenders("encoding", "utf-8")
        self.assertEqual(
            bad,
            [],
            'テキストの書き出しにはencoding="utf-8"が要る。'
            f" 指定の無い箇所: {bad}",
        )

    def test_scan_actually_finds_the_writes(self) -> None:
        """検査が空振りしていないことを確かめる。

        走査が0件でも上の2つは通ってしまう。**「見つからない」と
        「問題が無い」を取り違えない**ための保険。
        """
        total = sum(
            len(_text_writes(ast.parse(path.read_text(encoding="utf-8"))))
            for path in TOOLS_DIR.glob("*.py")
        )
        self.assertGreater(total, 5, "書き出しを1つも拾えていない。走査が壊れている")

    def test_detects_a_missing_newline(self) -> None:
        """検査そのものが違反を見つけられることを確かめる。"""
        tree = ast.parse('p.write_text(s, encoding="utf-8")')
        call, _ = _text_writes(tree)[0]
        self.assertIsNone(_keyword(call, "newline"))

    def test_binary_write_is_not_required_to_pin_newline(self) -> None:
        """バイナリは対象外。変換が起きないので指定する意味が無い。"""
        tree = ast.parse('open(p, "wb")')
        self.assertEqual(_text_writes(tree), [])


if __name__ == "__main__":
    unittest.main()
