"""ノードの id を変更し、全参照を追随させる。

id を手で変えると、フロントマターのエッジ・本文の `[[ID]]`・目次の一覧・
相対リンクのどれかを必ず取りこぼす。層を組み替えたとき（`schema.py` の
接頭辞やディレクトリを変えたとき）に必要になるので、機械的に行えるようにする。

新しい id の接頭辞が別の種別を指す場合は、`type` の書き換えとファイルの
移動もあわせて行う。`API-01` を `CON-01` にする、といった層の改称がこれにあたる。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import schema
from .frontmatter import set_scalar
from .model import Graph

MD_LINK_RE = re.compile(r"(\]\()([^)\s]+\.md)(\))")

# 書き換えてはいけない区間。loader が「リンクとして数えない場所」と同じ範囲。
# 規約や雛形に載せた**使い方の例**まで書き換えると、意味をなさない記述になる。
PROTECTED_RE = re.compile(r"```.*?```|`[^`\n]*`|<!--.*?-->", re.DOTALL)


def _apply_outside_protected(text: str, transform) -> str:
    """コードブロック・コードスパン・HTML コメントの外側にだけ `transform` を適用する。"""
    parts: list[str] = []
    last = 0

    for match in PROTECTED_RE.finditer(text):
        parts.append(transform(text[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()

    parts.append(transform(text[last:]))
    return "".join(parts)


class RenameError(RuntimeError):
    pass


def _token_re(node_id: str) -> re.Pattern:
    """id を「単語として」置き換えるための正規表現。

    `API-01` が `API-010` の一部にマッチしないよう、前後に英数字とハイフンが
    来ないことを条件にする。
    """
    return re.compile(
        r"(?<![A-Za-z0-9-])" + re.escape(node_id) + r"(?![A-Za-z0-9-])"
    )


def _scan_targets(root: Path, docs: Path) -> list[Path]:
    """書き換え対象のファイル一覧。

    グラフは `docs/` だが、リポジトリ直下の README.md や CLAUDE.md も
    docs の中へリンクしている。ここを見落とすと、グラフの検証は通るのに
    表紙のリンクだけ切れる。
    """
    paths: dict[Path, None] = {}
    for path in sorted(docs.rglob("*.md")):
        paths[path] = None
    for path in sorted(root.glob("*.md")):
        paths.setdefault(path, None)
    return list(paths)


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _target_path(
    node_path: Path,
    docs: Path,
    old_id: str,
    new_id: str,
    new_type: str,
    new_slug: str | None = None,
) -> Path:
    spec = schema.NODE_TYPES[new_type]
    directory = node_path.parent if spec["dir"] is None else docs / spec["dir"]

    if new_slug is not None:
        return directory / f"{new_id.lower()}-{new_slug}.md"

    stem = node_path.stem
    if stem.startswith(old_id.lower()):
        stem = new_id.lower() + stem[len(old_id.lower()) :]

    return directory / f"{stem}.md"


def _relative(target: Path, from_dir: Path) -> str:
    rel = Path(os.path.relpath(target, from_dir)).as_posix()
    return rel if rel.startswith(".") else "./" + rel


def _replace_type(text: str, new_type: str) -> str:
    """フロントマター内の `type:` だけを書き換える。"""
    return set_scalar(text, "type", new_type)


def rename(
    root: Path,
    graph: Graph,
    old_id: str,
    new_id: str,
    *,
    dry_run: bool = False,
    new_path_override: Path | None = None,
    new_slug: str | None = None,
) -> dict:
    """`new_path_override` は移動先を明示したいときに使う。

    種別 `index` のようにディレクトリが決まっていないノードを別の場所へ
    移すときに要る。リンクの張り替えは自動配置のときと同じように行う。

    `new_slug` はファイル名の後半だけを変えたいときに使う。**id は据え置ける。**
    文書の題を変えるとファイル名が実態とずれるが、id を変える理由は無い
    という場面がある。
    """
    node = graph.nodes.get(old_id)
    if node is None:
        raise RenameError(f"ノード {old_id!r} が見つかりません")
    if new_id != old_id and new_id in graph.nodes:
        raise RenameError(f"id {new_id!r} はすでに使われています")
    if old_id == new_id and new_slug is None:
        raise RenameError("変更前と変更後の id が同じです（--slug で名前だけ変えられます）")
    if new_slug is not None and not SLUG_RE.match(new_slug):
        raise RenameError(
            f"slug {new_slug!r} は英小文字・数字・ハイフンだけで書いてください"
        )

    new_prefix = new_id.split("-")[0]
    new_type = schema.type_of_prefix(new_prefix)
    if new_type is None:
        known = ", ".join(sorted(spec["prefix"] for spec in schema.NODE_TYPES.values()))
        raise RenameError(
            f"接頭辞 {new_prefix!r} に対応する種別がありません（既知: {known}）"
        )

    docs = root / schema.DOCS_DIR
    old_path = node.path

    if new_path_override is not None:
        new_path = new_path_override
        if not new_path.is_absolute():
            new_path = root / new_path
        try:
            new_path.resolve().relative_to(docs.resolve())
        except ValueError:
            raise RenameError(
                f"移動先は {schema.DOCS_DIR}/ の中である必要があります: {new_path}"
            ) from None
    else:
        new_path = _target_path(old_path, docs, old_id, new_id, new_type, new_slug)

    moved = new_path != old_path

    if moved and new_path.exists():
        raise RenameError(f"移動先がすでに存在します: {new_path.relative_to(root).as_posix()}")

    token = _token_re(old_id)
    edited: list[str] = []

    for path in _scan_targets(root, docs):
        original = path.read_text(encoding="utf-8")
        updated = _apply_outside_protected(original, lambda s: token.sub(new_id, s))

        if path == old_path:
            if node.type != new_type:
                updated = _replace_type(updated, new_type)
            if moved:
                updated = _apply_outside_protected(
                    updated, lambda s: _rebase_own_links(s, old_path, new_path)
                )
        elif moved:
            parent = path.parent
            updated = _apply_outside_protected(
                updated, lambda s: _retarget_links(s, parent, old_path, new_path)
            )

        if updated != original:
            edited.append(path.relative_to(root).as_posix())
            if not dry_run:
                path.write_text(updated, encoding="utf-8", newline="\n")

    if moved and not dry_run:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.replace(new_path)

    return {
        "old_id": old_id,
        "new_id": new_id,
        "old_type": node.type,
        "new_type": new_type,
        "old_path": old_path.relative_to(root).as_posix(),
        "new_path": new_path.relative_to(root).as_posix(),
        "moved": moved,
        "edited": edited,
    }


def _retarget_links(text: str, from_dir: Path, old_path: Path, new_path: Path) -> str:
    """他ファイルから、移動したファイルへのリンクを張り替える。"""

    def repl(match: re.Match) -> str:
        href = match.group(2)
        if "://" in href:
            return match.group(0)
        resolved = (from_dir / href).resolve()
        if resolved != old_path.resolve():
            return match.group(0)
        return match.group(1) + _relative(new_path, from_dir) + match.group(3)

    return MD_LINK_RE.sub(repl, text)


def _rebase_own_links(text: str, old_path: Path, new_path: Path) -> str:
    """移動するファイル自身が持つ相対リンクを、新しい位置から見た形に直す。"""
    old_dir = old_path.parent
    new_dir = new_path.parent

    def repl(match: re.Match) -> str:
        href = match.group(2)
        if "://" in href:
            return match.group(0)
        resolved = (old_dir / href).resolve()
        if not resolved.exists():
            return match.group(0)
        return match.group(1) + _relative(resolved, new_dir) + match.group(3)

    return MD_LINK_RE.sub(repl, text)
