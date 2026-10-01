"""gitの差分から、この変更で動いたノードを得る。

**なぜ差分に絞るのか。** 依存先の最終更新が自分より新しいものを単純に挙げると、
中心的なノード（大会・チームなど）の依存元に、いつも警告が出続ける。
4リポジトリ212ノードで測ると、**22%が常に警告に当たった。**
中心的な語彙は頻繁に触られるので、これは文書が古びているのではなく、いつもの状態である。

見たいのは古びた文書ではなく、取りこぼしである。つまり、いま依存先を書き換えたのに、
依存している側を見ていない状態である。これは差分の窓の中でしか意味を持たない。
窓を閉じれば（コミットすれば）警告は消えるので、消えない警告が積み上がらない。

`graph:auto`ブロックだけの変化は、変更として数えない。
`sync`が生成しているもので、依存元が追従する余地が無いからである。

gitが無いかリポジトリでない場合は、`None`を返す。呼び出し側は、これを見て検査を飛ばす。
"""

from __future__ import annotations

from pathlib import Path

from .git import run as _run
from .loader import strip_auto_block


def changed_paths(root: Path, since: str | None = None) -> set[str] | None:
    """変更されたファイルの、リポジトリからの相対パス。取れなければNoneを返す。

    `since`が無ければ、作業ツリーとHEADを比べる（コミットする前に役立たせるため）。
    `since`があれば、その参照との分岐点からHEADまでを見て、作業ツリーも含める。
    """
    if _run(root, ["rev-parse", "--is-inside-work-tree"]) is None:
        return None

    paths: set[str] = set()

    # 作業ツリー（未コミット・未追跡）は、窓が何であっても常に含める
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
    """`status --porcelain -z`を解釈する。改名は`R  new\0old\0`の2項になる。"""
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
        # 改名・複製では、新しい名前の次に元の名前が続く
        if code[0] in ("R", "C"):
            skip_next = True
    return paths


def _prose_changed(root: Path, base: str, rel: str) -> bool:
    """`graph:auto`を除いた本文が、`base`から変わっているか。

    読めない側（新規ファイル・削除済みのファイル）は、変更として扱う。

    **作業ツリー側も、`git show`と同じく`errors="replace"`で読む。**
    画像などテキストでないファイルを厳格に読むと、`UnicodeDecodeError`でcheckごと落ちる
    （setopic/graph-doc-template#13）。両側を同じ読み方に揃えれば、中身が変わったかは比較で分かる。
    """
    old = _run(root, ["show", f"{base}:{rel}"])
    if old is None:
        return True

    path = root / rel
    try:
        new = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True

    return strip_auto_block(old).strip() != strip_auto_block(new).strip()
