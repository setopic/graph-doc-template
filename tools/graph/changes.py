"""git の差分から「この変更で動いたノード」を得る。

**なぜ差分に絞るのか。** 「依存先の最終更新が自分より新しい」を素朴に見ると、
中心的なノード（大会・チームなど）の依存元が常に警告に出続ける。
4 リポジトリ 212 ノードで測ると **22% が恒常的に引っかかった。**
中心語彙は頻繁に触られるので、これは腐敗ではなく定常状態である。

見たいのは腐敗ではなく**取りこぼし**、つまり「いま依存先を書き換えたのに、
依存している側を見ていない」である。これは差分の窓の中でしか意味を持たない。
窓を閉じれば（コミットすれば）消えるので、**消えない警告が積み上がらない。**

`graph:auto` ブロックだけの変化は**変更として数えない。**
`sync` が生成しているもので、依存元が追従する余地が無い。

git が無い・リポジトリでない場合は `None` を返す。検査を飛ばす合図。
"""

from __future__ import annotations

from pathlib import Path

from .git import run as _run
from .loader import strip_auto_block


def changed_paths(root: Path, since: str | None = None) -> set[str] | None:
    """変更されたファイルのリポジトリ相対パス。取れなければ None。

    `since` が無ければ作業ツリーと HEAD を比べる（コミット前に効かせるため）。
    `since` があればその参照との**分岐点**から HEAD まで、作業ツリーも含める。
    """
    if _run(root, ["rev-parse", "--is-inside-work-tree"]) is None:
        return None

    paths: set[str] = set()

    # 作業ツリー（未コミット・未追跡）は窓が何であっても常に含める
    status = _run(root, ["status", "--porcelain", "-z"])
    if status is None:
        return None
    paths.update(_parse_status(status))

    if since:
        committed = _run(root, ["diff", "--name-only", f"{since}...HEAD"])
        if committed is None:
            return None
        paths.update(p.strip() for p in committed.splitlines() if p.strip())

    base = since or "HEAD"
    return {p for p in paths if _prose_changed(root, base, p)}


def _parse_status(status: str) -> list[str]:
    """`status --porcelain -z` を解く。改名は `R  new\0old\0` の 2 項になる。"""
    fields = [f for f in status.split("\x00") if f]
    paths: list[str] = []
    skip_next = False
    for field in fields:
        if skip_next:
            skip_next = False
            continue
        if len(field) < 4:
            continue
        code, path = field[:2], field[3:]
        paths.append(path)
        # 改名・複製は「新しい名前」の次に「元の名前」が続く
        if code[0] in ("R", "C"):
            skip_next = True
    return paths


def _prose_changed(root: Path, base: str, rel: str) -> bool:
    """`graph:auto` を除いた本文が `base` から変わっているか。

    読めない側（新規ファイル・削除済み）は変更として扱う。
    """
    old = _run(root, ["show", f"{base}:{rel}"])
    if old is None:
        return True

    path = root / rel
    try:
        new = path.read_text(encoding="utf-8")
    except OSError:
        return True

    return strip_auto_block(old).strip() != strip_auto_block(new).strip()
