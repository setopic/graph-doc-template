"""YAMLのフロントマターを読む、最小限のパーサ。

テンプレートを外部依存なしで動かすために、YAMLのサブセットだけを扱う。
対応していない記法は、何も言わずに無視せず、FrontmatterErrorにする（誤ったグラフを
読めたつもりで通さないため）。

対応する記法は、次のとおりである。

    ---
    id: UC-01
    title: "引用符つきでもよい"
    tags: [core, shift]
    depends_on:
      - DOM-01
      - DOM-02
    related:
    ---

対応しない記法は、ネストしたマップ、複数行の文字列（|や>）、行末の#コメント、
アンカーとエイリアスである。これらが必要になったら、PyYAMLに差し替える。
"""

from __future__ import annotations


class FrontmatterError(ValueError):
    """フロントマターが読めなかったことを表す。"""


DELIMITER = "---"

_TRUE = {"true", "yes"}
_FALSE = {"false", "no"}


def split(text: str) -> tuple[dict, str]:
    """`(フロントマターのdict, 本文)`を返す。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontmatterError("先頭の行が'---'ではない（フロントマターが必要である）")

    for i in range(1, len(lines)):
        if lines[i].strip() == DELIMITER:
            return _parse_block(lines[1:i]), "\n".join(lines[i + 1 :])

    raise FrontmatterError("フロントマターを閉じる'---'が見つからない")


def _parse_block(lines: list[str]) -> dict:
    data: dict = {}
    current_key: str | None = None

    for offset, raw in enumerate(lines):
        lineno = offset + 2  # 1行目は開始のデリミタ
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # ブロックリストの項目
        if stripped.startswith("- "):
            if current_key is None:
                raise FrontmatterError(f"{lineno}行目: 対応するキーの無いリスト項目である")
            if not isinstance(data.get(current_key), list):
                raise FrontmatterError(
                    f"{lineno}行目: キー{current_key!r}は値を持っているので、リストにできない"
                )
            data[current_key].append(_scalar(stripped[2:], lineno))
            continue

        if line[0] in " \t":
            raise FrontmatterError(f"{lineno}行目: ネストしたマップには対応していない")

        if ":" not in line:
            raise FrontmatterError(f"{lineno}行目: 'key: value'の形ではない -> {line!r}")

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not key:
            raise FrontmatterError(f"{lineno}行目: キーが空である")
        if key in data:
            raise FrontmatterError(f"{lineno}行目: キー{key!r}が重複している")

        if value == "":
            # 値が無いのは、空のリストか、直後にブロックリストが続く場合
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [_scalar(x, lineno) for x in inner.split(",") if x.strip()] if inner else []
        else:
            data[key] = _scalar(value, lineno)

        current_key = key

    return data


def _scalar(token: str, lineno: int) -> object:
    token = token.strip()
    if not token:
        raise FrontmatterError(f"{lineno}行目: 値が空である")

    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]

    lowered = token.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False

    return token


def set_scalar(text: str, key: str, value: str) -> str:
    """フロントマターの中の`key:`を書き換える。本文には触れない。

    見つからなければ、何もしない。フロントマターが無い文書に
    キーを足す用途には使わない。
    """
    import re

    parts = text.split("---", 2)
    if len(parts) < 3:
        return text

    head, replaced = re.subn(
        rf"^{re.escape(key)}:.*$",
        f"{key}: {value}",
        parts[1],
        count=1,
        flags=re.MULTILINE,
    )
    if not replaced:
        return text

    return parts[0] + "---" + head + "---" + parts[2]


def as_list(value: object) -> list[str]:
    """フロントマターの値を、文字列のリストに揃える。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []
