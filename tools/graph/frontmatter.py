"""YAML フロントマターの最小パーサ。

テンプレートを外部依存ゼロで動かすため、YAML のサブセットだけを扱う。
未対応の記法は黙って無視せず FrontmatterError にする（壊れたグラフを
「読めているつもり」で通さないため）。

対応する記法::

    ---
    id: UC-01
    title: "引用符つきでもよい"
    tags: [core, shift]
    depends_on:
      - DOM-01
      - DOM-02
    related:
    ---

対応しない記法: ネストしたマップ、複数行文字列（| や >）、行末の # コメント、
アンカー／エイリアス。これらが必要になったら PyYAML に差し替える。
"""

from __future__ import annotations


class FrontmatterError(ValueError):
    """フロントマターが読めなかったことを表す。"""


DELIMITER = "---"

_TRUE = {"true", "yes"}
_FALSE = {"false", "no"}


def split(text: str) -> tuple[dict, str]:
    """`(フロントマターの dict, 本文)` を返す。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        raise FrontmatterError("先頭行が '---' ではありません（フロントマターが必要です）")

    for i in range(1, len(lines)):
        if lines[i].strip() == DELIMITER:
            return _parse_block(lines[1:i]), "\n".join(lines[i + 1 :])

    raise FrontmatterError("フロントマターを閉じる '---' が見つかりません")


def _parse_block(lines: list[str]) -> dict:
    data: dict = {}
    current_key: str | None = None

    for offset, raw in enumerate(lines):
        lineno = offset + 2  # 1 行目は開始デリミタ
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        # ブロックリストの項目
        if stripped.startswith("- "):
            if current_key is None:
                raise FrontmatterError(f"{lineno} 行目: 対応するキーのないリスト項目です")
            if not isinstance(data.get(current_key), list):
                raise FrontmatterError(
                    f"{lineno} 行目: キー {current_key!r} は値を持っているためリストにできません"
                )
            data[current_key].append(_scalar(stripped[2:], lineno))
            continue

        if line[0] in " \t":
            raise FrontmatterError(f"{lineno} 行目: ネストしたマップは未対応です")

        if ":" not in line:
            raise FrontmatterError(f"{lineno} 行目: 'key: value' の形ではありません -> {line!r}")

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not key:
            raise FrontmatterError(f"{lineno} 行目: キーが空です")
        if key in data:
            raise FrontmatterError(f"{lineno} 行目: キー {key!r} が重複しています")

        if value == "":
            # 値なし = 空リスト、または直後にブロックリストが続く
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
        raise FrontmatterError(f"{lineno} 行目: 空の値です")

    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]

    lowered = token.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False

    return token


def as_list(value: object) -> list[str]:
    """フロントマターの値を文字列リストに正規化する。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []
