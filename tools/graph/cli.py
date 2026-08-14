"""グラフ操作の CLI。

    python -m tools.graph check          リンク切れ・孤立・循環・層の逆流を検証
    python -m tools.graph render         Mermaid / JSON / DOT を書き出す
    python -m tools.graph sync           各文書末尾の関連リンクを再生成
    python -m tools.graph new            雛形から新しいノードを起こす（--from で一括）
    python -m tools.graph rename         id を変更し、全参照を追随させる
    python -m tools.graph reset-samples  サンプルノードを一括で取り除く
    python -m tools.graph stats          ノード数・エッジ数の集計
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cleanup, history
from . import render as render_mod
from . import rules, schema
from . import upgrade as upgrade_mod
from .loader import load
from .model import ERROR, WARN
from .rename import RenameError
from .rename import rename as rename_node
from .scaffold import ScaffoldError, create, create_many, parse_batch
from .sync import sync as sync_graph
from .version import TEMPLATE_VERSION


def _repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    # tools/graph/cli.py -> リポジトリルート
    return Path(__file__).resolve().parents[2]


def cmd_check(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    # 履歴が取れないときは G011 を飛ばす（誤検知より無検知）
    file_dates = {} if args.no_history else history.last_commit_dates(root)
    issues = rules.check_all(graph, history=file_dates)

    errors = [i for i in issues if i.severity == ERROR]
    warns = [i for i in issues if i.severity == WARN]

    if args.format == "json":
        print(
            json.dumps(
                {
                    "nodes": len(graph.nodes),
                    "errors": len(errors),
                    "warnings": len(warns),
                    "issues": [i.to_dict() for i in issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in issues:
            print(issue.format())
        if not issues:
            print(f"OK: {len(graph.nodes)} ノード、問題なし")
        else:
            print("")
            print(f"ノード {len(graph.nodes)} / エラー {len(errors)} / 警告 {len(warns)}")
            codes = sorted({i.code for i in issues})
            for code in codes:
                print(f"  {code}: {rules.RULE_INDEX.get(code, '')}")

    if errors:
        return 1
    if warns and args.strict:
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    focus: set[str] | None = None

    if args.focus:
        focus = {i.strip() for i in args.focus.split(",") if i.strip()}
        unknown = sorted(i for i in focus if i not in graph.nodes)
        if unknown:
            print(f"エラー: 存在しないノードです: {', '.join(unknown)}", file=sys.stderr)
            return 1
        graph = graph.neighborhood(
            sorted(focus),
            depth=args.depth,
            include_mentions=args.include_mentions,
        )
        print(
            f"{', '.join(sorted(focus))} から {args.depth} ホップ以内: "
            f"{len(graph.nodes)} ノード",
            file=sys.stderr,
        )

    if args.format == "mermaid":
        output = render_mod.to_mermaid(
            graph, include_mentions=args.include_mentions, focus=focus
        )
    elif args.format == "json":
        output = render_mod.to_json(graph, include_mentions=args.include_mentions)
    else:
        output = render_mod.to_dot(graph, include_mentions=args.include_mentions)

    if args.into:
        if args.format != "mermaid":
            print("エラー: --into は --format mermaid のときだけ使えます", file=sys.stderr)
            return 1

        into_path = Path(args.into)
        if not into_path.is_absolute():
            into_path = root / into_path

        try:
            changed = render_mod.inject(into_path, output, dry_run=args.check)
        except render_mod.InjectError as exc:
            print(f"エラー: {exc}", file=sys.stderr)
            return 1

        rel = into_path.relative_to(root).as_posix()
        if not changed:
            print(f"更新なし（最新）: {rel}")
            return 0
        if args.check:
            print(f"図が古くなっています: {rel}")
            return 1
        print(f"図を更新しました: {rel}")
        return 0

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8", newline="\n")
        print(f"書き出しました: {out_path.relative_to(root).as_posix()}")
    else:
        sys.stdout.write(output)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    blocking = [i for i in graph.load_issues if i.severity == ERROR]
    if blocking:
        for issue in blocking:
            print(issue.format())
        print("\n読み込みエラーがあるため sync を中止しました")
        return 1

    dry_run = args.dry_run or args.check
    changed = sync_graph(graph, dry_run=dry_run)
    if not changed:
        print("更新なし（すべて最新）")
        return 0

    verb = "更新予定" if dry_run else "更新"
    for rel in changed:
        print(f"{verb}: {rel}")
    print(f"\n{len(changed)} 件")
    return 1 if args.check else 0


def cmd_new(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)

    if args.from_file:
        return _new_from_file(root, Path(args.from_file))

    missing = [n for n in ("type", "id", "title") if not getattr(args, n)]
    if missing:
        print(
            f"エラー: --{' --'.join(missing)} が必要です（または --from でまとめて指定）",
            file=sys.stderr,
        )
        return 1

    try:
        path = create(
            root,
            node_type=args.type,
            node_id=args.id,
            title=args.title,
            slug=args.slug,
            status=args.status,
            template=args.template,
        )
    except ScaffoldError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    print(f"作成しました: {path.relative_to(root).as_posix()}")
    print("フロントマターの depends_on / related を埋めてから check を回してください")
    return 0


def _new_from_file(root: Path, path: Path) -> int:
    if not path.is_absolute():
        path = root / path

    try:
        entries = parse_batch(path)
    except ScaffoldError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    created, errors = create_many(root, entries)

    for created_path in created:
        print(f"作成しました: {created_path.relative_to(root).as_posix()}")
    for message in errors:
        print(f"エラー: {message}", file=sys.stderr)

    print(f"\n作成 {len(created)} 件 / 失敗 {len(errors)} 件")
    if created:
        print("フロントマターの depends_on / related を埋めてから check を回してください")
    return 1 if errors else 0


def cmd_reset_samples(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    result = cleanup.remove(root, graph, args.tag, dry_run=not args.yes)

    targets = result["targets"]
    if not targets:
        print(f"tags に {args.tag!r} を持つノードはありません")
        return 0

    verb = "削除しました" if args.yes else "削除対象"
    for node in targets:
        print(f"{verb}: {node.rel}  ({node.id} {node.title})")

    for rel in result["index_updated"]:
        print(f"一覧から除外: {rel}")

    if result["referenced_by"]:
        print("\n以下から参照されています。削除後に check で確認してください:")
        for target_id, sources in sorted(result["referenced_by"].items()):
            print(f"  {target_id} <- {', '.join(sources)}")

    if not args.yes:
        print(f"\n{len(targets)} 件。実際に削除するには --yes を付けてください")
        return 0

    print(f"\n{len(targets)} 件を削除しました。check を回して残った参照を直してください")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    try:
        result = rename_node(
            root,
            graph,
            args.old_id,
            args.new_id,
            dry_run=args.dry_run,
            new_path_override=Path(args.path) if args.path else None,
        )
    except RenameError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    verb = "変更予定" if args.dry_run else "変更"
    print(f"{verb}: {result['old_id']} -> {result['new_id']}")

    if result["old_type"] != result["new_type"]:
        print(f"  type: {result['old_type']} -> {result['new_type']}")
    if result["moved"]:
        print(f"  file: {result['old_path']} -> {result['new_path']}")

    for rel in result["edited"]:
        print(f"  更新: {rel}")

    print(f"\n{len(result['edited'])} ファイル")
    if args.dry_run:
        print("--dry-run のため書き込んでいません")
    else:
        print("sync を回してから check を確認してください")
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)

    try:
        result = upgrade_mod.inspect(root)
    except upgrade_mod.UpgradeError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    print(f"ローカル:     {result['local']}")
    print(f"テンプレート: {result['remote']}")
    print("")

    if result["ahead"]:
        print("ローカルの方が新しい版です。テンプレート本体で実行していませんか。")
        return 0

    if not result["behind"]:
        print("最新です。取り込むものはありません。")
        return 0

    if result["breaking"]:
        print("**破壊的変更を含みます。マージしただけでは壊れます。**")
        print("下の移行手順を読んでから取り込んでください。")
        print("")

    for version, body in result["entries"]:
        print(f"--- {version} ---")
        print(body if body else "（記載なし）")
        print("")

    if result["files"]:
        print(f"変更されるファイル（{len(result['files'])} 件）:")
        for rel in result["files"][:20]:
            print(f"  {rel}")
        if len(result["files"]) > 20:
            print(f"  ... 他 {len(result['files']) - 20} 件")
        print("")

    print("取り込む手順は README の「テンプレートの更新を取り込む」にあります。")
    print("このコマンドは何も書き込んでいません。")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    sys.stdout.write(render_mod.summary(graph))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.graph", description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version=f"graph-doc-template {TEMPLATE_VERSION}",
        help="テンプレートの版を表示する（変更履歴は TEMPLATE_CHANGELOG.md）",
    )
    parser.add_argument("--root", help="リポジトリルート（既定: このファイルから推定）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="グラフを検証する")
    p_check.add_argument("--strict", action="store_true", help="警告も失敗として扱う")
    p_check.add_argument("--format", choices=("text", "json"), default="text")
    p_check.add_argument(
        "--no-history",
        action="store_true",
        help="git 履歴を見ない（G011 の放置検出を飛ばす）",
    )
    p_check.set_defaults(func=cmd_check)

    p_render = sub.add_parser("render", help="グラフを書き出す")
    p_render.add_argument("--format", choices=("mermaid", "json", "dot"), default="mermaid")
    p_render.add_argument("--out", help="出力先（省略時は標準出力）")
    p_render.add_argument(
        "--into",
        metavar="PATH",
        help="Markdown のマーカー内に図を書き込む（mermaid 限定。README 用）",
    )
    p_render.add_argument(
        "--check",
        action="store_true",
        help="--into と併用し、書き込まずに古ければ終了コード 1（CI 用）",
    )
    p_render.add_argument(
        "--focus",
        metavar="ID[,ID...]",
        help="指定ノードの近傍だけを描く（向きは無視して両方向に辿る）",
    )
    p_render.add_argument(
        "--depth",
        type=int,
        default=1,
        metavar="N",
        help="--focus から何ホップまで含めるか（既定: 1）",
    )
    p_render.add_argument(
        "--include-mentions",
        action="store_true",
        help="本文中の [[ID]] 由来のリンクも含める",
    )
    p_render.set_defaults(func=cmd_render)

    p_sync = sub.add_parser("sync", help="関連ドキュメントのブロックを再生成する")
    p_sync.add_argument("--dry-run", action="store_true", help="書き込まずに差分だけ表示")
    p_sync.add_argument(
        "--check",
        action="store_true",
        help="書き込まず、更新が必要なら終了コード 1（CI 用）",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_new = sub.add_parser("new", help="新しいノードを作る")
    p_new.add_argument("--type", choices=tuple(schema.NODE_TYPES))
    p_new.add_argument("--id", help="例: UC-02")
    p_new.add_argument("--title")
    p_new.add_argument("--slug", help="ファイル名に使う英数字。省略時は title から生成")
    p_new.add_argument("--status", default="draft", choices=schema.STATUSES)
    p_new.add_argument(
        "--template",
        help="使う雛形の名前（docs/00-meta/templates/<名前>.md）。省略時は type と同名",
    )
    p_new.add_argument(
        "--from",
        dest="from_file",
        metavar="PATH",
        help="1 行 1 ノードのファイルからまとめて作る（`type | id | title | slug` 形式）",
    )
    p_new.set_defaults(func=cmd_new)

    p_reset = sub.add_parser(
        "reset-samples",
        help="サンプルノードを一括で取り除く（テンプレート複製直後に使う）",
    )
    p_reset.add_argument(
        "--tag",
        default=cleanup.DEFAULT_TAG,
        help=f"削除対象とする tags の値（既定: {cleanup.DEFAULT_TAG}）",
    )
    p_reset.add_argument(
        "--yes",
        action="store_true",
        help="実際に削除する。付けない場合は対象を表示するだけ",
    )
    p_reset.set_defaults(func=cmd_reset_samples)

    p_rename = sub.add_parser(
        "rename",
        help="ノードの id を変更し、全参照を追随させる",
    )
    p_rename.add_argument("--from", dest="old_id", required=True, metavar="ID", help="例: API-01")
    p_rename.add_argument("--to", dest="new_id", required=True, metavar="ID", help="例: CON-01")
    p_rename.add_argument(
        "--path",
        metavar="PATH",
        help="移動先を明示する（種別からディレクトリが決まらない index などで使う）",
    )
    p_rename.add_argument(
        "--dry-run", action="store_true", help="書き込まずに変更内容だけ表示する"
    )
    p_rename.set_defaults(func=cmd_rename)

    p_upgrade = sub.add_parser(
        "upgrade",
        help="テンプレートとの差を調べる（読み取りのみ。取り込みは手動）",
    )
    p_upgrade.set_defaults(func=cmd_upgrade)

    p_stats = sub.add_parser("stats", help="集計を表示する")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def _make_stdio_safe() -> None:
    """印字で落ちないようにする。

    `check` の警告は文書の本文をそのまま引用する（`G013` など）。本文には
    Windows の既定コードページ（cp932 など）で表現できない文字が混ざりうる。
    そのまま print すると UnicodeEncodeError で途中まで出したまま止まり、
    **グラフは正しいのに終了コード 1 になる**。本物の検証失敗と区別が付かない。

    そこで UTF-8 に切り替える。ファイルの書き出しは元から UTF-8 なので、
    これで入出力の扱いが揃う。`errors="replace"` は表現できない文字が
    残った場合（サロゲートを含むパスなど）の保険。
    """
    for stream in (sys.stdout, sys.stderr):
        # pythonw では None、テストでは StringIO に差し替わっていることがある
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, LookupError):
            pass


def main(argv: list[str] | None = None) -> int:
    _make_stdio_safe()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
