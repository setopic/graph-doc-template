"""PRが指している文書ノードが、実在するかを確かめる。

実装のコミットは、すでにノードのidを書いている（tournamentで95%、
medieval-idleで100%）。慣習として成立しているものを、機械が確かめるだけにする。

`なし`と書けば通す。文書に対応が無い変更（依存の更新、設定の修正）は、必ずある。
**「なし」と読むのは、行の頭に書いたものだけである**（`なし`か`ノード: なし`で始まる行）。
以前は、題と本文のどこかに「なし」を含めば照合を飛ばしていたので、「問題なし」「更新なし」
「みなし」でも飛んでいた。派生のPR 30件のうち10件が飛び、意図したものは1件だった
（setopic/graph-project-template#5）。

**本文に「対応するノード」の節があれば、題とその節だけを読む。** 節の外には、idの振り方の
例のように、ノードを指していないidが書かれることがある。全体を読んでいた頃は、例に書いた
まだ無いidで落ちた（setopic/novel-template#4、#82）。コードスパンの中を読まない、という直し方は
採らなかった。派生のPR 99件のうち2件は、idをすべてコードスパンの中に書いていた。
節が無い本文（雛形を使っていないPR）は、これまでどおり全体を読む。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.graph import schema  # noqa: E402
from tools.graph.loader import load  # noqa: E402

ID = re.compile(r"\b(?:[A-Z]{2,5}-\d{2,4})\b")
# 行の頭の「なし」だけを読む。後ろに続いてよいのは、空白・括弧・句読点・行末
NONE_LINE = re.compile(
    r"^\s*(?:ノード\s*[:：]\s*)?(?:なし|none|n/a)(?=[\s（(。、]|$)",
    re.IGNORECASE | re.MULTILINE,
)
# PRの雛形の記入案内（「`なし`と書く」）を、宣言として読まない
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# PRの雛形（.github/pull_request_template.md）の節。次の`## `の見出しまでを読む
SECTION = re.compile(r"^##\s*対応するノード\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)


def declared_part(title: str, body: str) -> str:
    """照合する範囲。「対応するノード」の節があれば、題とその節だけにする。"""
    match = SECTION.search(COMMENT.sub("", body))
    return title + "\n" + (match.group(1) if match else body)


def declares_none(text: str) -> bool:
    """「対応するノードが無い」と書いてあるか。"""
    return bool(NONE_LINE.search(COMMENT.sub("", text)))


def check(text: str, known: set[str]) -> int:
    """題と本文をつないだ`text`を確かめ、終了コードを返す。"""
    if declares_none(text):
        print("「なし」と書かれているので、確かめない")
        return 0

    found = sorted(set(ID.findall(text)))
    if not found:
        print("対応するノードが書かれていない。")
        print("idを書くか、対応が無いなら、行の頭に「なし」と書く。")
        return 1

    missing = [i for i in found if i not in known]
    print("参照:", " ".join(found))
    if missing:
        print("実在しないノード:", " ".join(missing))
        return 1

    print("すべて実在する")
    return 0


def main() -> int:
    # 題も見る。コミットの1行目と同じ形（「何をしたか。ADR-0089 / UC-48」）で、idを書く慣習がある
    text = declared_part(os.environ.get("PR_TITLE", ""), os.environ.get("PR_BODY", ""))
    root = Path(__file__).resolve().parents[2]
    schema.configure(root)  # ほかのコマンドと同じく、graph.tomlの種別で読む
    graph = load(root)
    return check(text, set(graph.nodes))


if __name__ == "__main__":
    raise SystemExit(main())
