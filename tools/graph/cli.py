"""グラフを操作するCLI。

    python -m tools.graph check          リンク切れ・孤立・循環・層の逆流を検証する
    python -m tools.graph render         Mermaid・SVG・JSON・DOTの形式で書き出す
    python -m tools.graph sync           各文書の末尾の関連リンクを作り直す
    python -m tools.graph new            雛形から新しいノードを作る（--fromでまとめて作る）
    python -m tools.graph rename         idを変え、すべての参照を追随させる
    python -m tools.graph reset-samples  サンプルノードをまとめて取り除く
    python -m tools.graph stats          ノード数・エッジ数と、構造の見直しの候補を出す
    python -m tools.graph path           2つのノードを結ぶ前提の経路を出す
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import changes, cleanup, history, review, structure
from . import render as render_mod
from .linkify import linkify as linkify_docs
from . import rules, schema
from . import svg as svg_mod
from . import upgrade as upgrade_mod
from .loader import load
from .model import ERROR, WARN
from .rename import RenameError
from .rename import rename as rename_node
from .scaffold import TEMPLATE_DIR, ScaffoldError, create, create_many, parse_batch
from .sync import sync as sync_graph
from .version import TEMPLATE_VERSION


def _repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    # tools/graph/cli.py -> リポジトリの根
    return Path(__file__).resolve().parents[2]


def cmd_check(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    # 履歴が取れないときは、G011を飛ばす（誤検知するより、検知しないほうを選ぶ）
    file_dates = {} if args.no_history else history.last_commit_dates(root)

    # 変更が取れないときは、G015・G017を飛ばす。gitが無くてもcheckは動く
    changed_ids: set[str] = set()
    touched: set[str] = set()
    if not args.no_history:
        touched = changes.changed_paths(root, args.since) or set()
        changed_ids = {n.id for n in graph.nodes.values() if n.rel in touched}

    issues = rules.check_all(
        graph, history=file_dates, changed=changed_ids, changed_files=touched
    )

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
            print(f"OK: {len(graph.nodes)}ノード、問題なし")
        else:
            print("")
            print(f"ノード{len(graph.nodes)} / エラー{len(errors)} / 警告{len(warns)}")
            codes = sorted({i.code for i in issues})
            for code in codes:
                print(f"  {code}: {rules.rule_summary(code)}")

    if errors:
        return 1
    if warns and args.strict:
        return 1
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    focus: set[str] | None = None
    omitted = None

    if args.budget is not None and (args.format != "json" or not args.focus):
        print("エラー: --budgetは、--format jsonと--focusを付けたときだけ使える", file=sys.stderr)
        return 1
    if args.aggregate and args.format not in ("mermaid", "svg"):
        print("エラー: --aggregateは、--format mermaidかsvgのときだけ使える", file=sys.stderr)
        return 1
    if args.aggregate and args.focus:
        print(
            "エラー: --aggregateと--focusは、同時に使えない"
            "（集約すると個別のノードが消えるので、絞る意味が無くなる）",
            file=sys.stderr,
        )
        return 1

    if args.reduce and (args.aggregate or args.format == "json"):
        print(
            "エラー: --reduceは、--aggregateとも--format jsonとも同時に使えない"
            "（線の本数や、depends_onに書いた前提が実態とずれる）",
            file=sys.stderr,
        )
        return 1

    types: set[str] | None = None
    if args.type:
        if args.aggregate or args.focus:
            print(
                "エラー: --typeは、--aggregateとも--focusとも同時に使えない"
                "（どれも図に描くノードを選ぶので、組み合わせると意味が決まらない）",
                file=sys.stderr,
            )
            return 1
        types = {t.strip() for t in args.type.split(",") if t.strip()}
        unknown = sorted(t for t in types if t not in schema.NODE_TYPES)
        if unknown:
            print(
                f"エラー: 存在しない種別: {', '.join(unknown)}"
                f"（使えるのは{', '.join(schema.NODE_TYPES)}）",
                file=sys.stderr,
            )
            return 1

    if args.hide_edges:
        hidden = {k.strip() for k in args.hide_edges.split(",") if k.strip()}
        known = (*schema.frontmatter_edge_kinds(), schema.BODY_EDGE_KIND)
        unknown = sorted(k for k in hidden if k not in known)
        if unknown:
            print(
                f"エラー: 存在しない線の種類: {', '.join(unknown)}"
                f"（使えるのは{', '.join(known)}）",
                file=sys.stderr,
            )
            return 1
        # 先に線を外す。--focusも--aggregateも、残った線だけを見る
        graph = graph.without_kinds(hidden)

    if args.focus:
        focus = {i.strip() for i in args.focus.split(",") if i.strip()}
        unknown = sorted(i for i in focus if i not in graph.nodes)
        if unknown:
            print(f"エラー: 存在しないノード: {', '.join(unknown)}", file=sys.stderr)
            return 1
        distance = graph.hops(
            sorted(focus), depth=args.depth, include_mentions=args.include_mentions
        )
        selected = set(distance)
        if args.budget is not None:
            selected, omitted = _fit_budget(graph, distance, args.budget)
        graph = graph.subgraph(selected, include_mentions=args.include_mentions)
        print(
            f"{', '.join(sorted(focus))}から{args.depth}ホップ以内: "
            f"{len(distance)}ノード",
            file=sys.stderr,
        )
        if omitted:
            print(f"予算{args.budget}字に収まらず、名前だけを出したノード: {len(omitted)}", file=sys.stderr)

    if types and args.format not in ("mermaid", "svg"):
        # jsonとdotには箱を描かない。その種別のノードと、その間の線だけを出す
        graph = graph.subgraph(
            {n.id for n in graph.nodes.values() if n.type in types},
            include_mentions=args.include_mentions,
        )

    reduced = 0
    if args.reduce:
        # 個別に描くノードの間の線だけを見る。--typeの箱を通る経路では省かない
        among = {n.id for n in graph.nodes.values() if n.type in types} if types else None
        graph, reduced = graph.without_implied("depends_on", among)
        print(f"ほかのdepends_onを辿れば分かる依存を、図から{reduced}本省いた", file=sys.stderr)

    if args.format == "mermaid" and types:
        output = render_mod.to_mermaid_types(
            graph, types, include_mentions=args.include_mentions
        )
    elif args.format == "mermaid" and args.aggregate:
        output = render_mod.to_mermaid_aggregate(
            graph, include_mentions=args.include_mentions
        )
    elif args.format == "mermaid":
        output = render_mod.to_mermaid(
            graph, include_mentions=args.include_mentions, focus=focus
        )
    elif args.format == "svg":
        try:
            css = svg_mod.load_theme(root)
        except OSError as exc:
            print(f"エラー: テーマのCSSが読めない: {exc}", file=sys.stderr)
            return 1
        output = svg_mod.to_svg(
            graph,
            css=css,
            include_mentions=args.include_mentions,
            focus=focus,
            types=types,
            aggregate=args.aggregate,
            animate=schema.RENDER_ANIMATE,
            period=schema.RENDER_PERIOD,
        )
    elif args.format == "json":
        output = render_mod.to_json(
            graph, include_mentions=args.include_mentions, omitted=omitted
        )
    else:
        output = render_mod.to_dot(graph, include_mentions=args.include_mentions)

    if args.reduce:
        output = render_mod.note_reduced(output, args.format, reduced)

    if args.into:
        if args.format not in ("mermaid", "svg"):
            print("エラー: --intoは、--format mermaidかsvgのときだけ使える", file=sys.stderr)
            return 1

        into_path = Path(args.into)
        if not into_path.is_absolute():
            into_path = root / into_path

        svg_stale = False
        if args.format == "svg":
            # SVGはファイルに書き、READMEにはその画像への参照を書き込む
            svg_path = Path(args.out or f"{schema.DOCS_DIR}/graph.svg")
            if not svg_path.is_absolute():
                svg_path = root / svg_path
            old = svg_path.read_bytes() if svg_path.is_file() else None
            new = output.encode("utf-8")
            svg_stale = old != new
            if svg_stale and not args.check:
                svg_path.parent.mkdir(parents=True, exist_ok=True)
                svg_path.write_bytes(new)
            try:
                ref = Path(os.path.relpath(svg_path, into_path.parent)).as_posix()
            except ValueError:
                print("エラー: SVGの書き出し先が、READMEと別のドライブにある", file=sys.stderr)
                return 1
            inject_args = {"diagram": ref, "image": True}
        else:
            inject_args = {"diagram": output}

        try:
            changed = render_mod.inject(into_path, dry_run=args.check, **inject_args)
        except render_mod.InjectError as exc:
            print(f"エラー: {exc}", file=sys.stderr)
            return 1
        changed = changed or svg_stale

        rel = into_path.relative_to(root).as_posix()
        if args.format == "svg":
            rel = f"{rel}・{svg_path.relative_to(root).as_posix()}"
        if not changed:
            print(f"更新なし（最新）: {rel}")
            return 0
        if args.check:
            print(f"図が古くなっている: {rel}")
            return 1
        print(f"図を更新した: {rel}")
        return 0

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8", newline="\n")
        print(f"書き出した: {out_path.relative_to(root).as_posix()}")
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
        print("\n読み込みのエラーがあるので、syncを中止した")
        return 1

    dry_run = args.dry_run or args.check
    changed = sync_graph(graph, dry_run=dry_run)
    if not changed:
        print("更新なし（すべて最新）")
        return 0

    verb = "更新予定" if dry_run else "更新"
    for rel in changed:
        print(f"{verb}: {rel}")
    print(f"\n{len(changed)}件")
    return 1 if args.check else 0


def cmd_linkify(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    blocking = [i for i in graph.load_issues if i.severity == ERROR]
    if blocking:
        for issue in blocking:
            print(issue.format())
        print("読み込みのエラーがあるので、linkifyを中止した")
        return 1

    dry_run = args.dry_run or args.check
    changed = linkify_docs(graph, root, root / schema.DOCS_DIR, dry_run=dry_run)
    if not changed:
        print("更新なし（すべて最新）")
        return 0

    verb = "更新予定" if dry_run else "更新"
    for rel in changed:
        print(f"{verb}: {rel}")
    print(f"{len(changed)}件")
    return 1 if args.check else 0


def cmd_new(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)

    if args.from_file:
        return _new_from_file(root, Path(args.from_file))

    missing = [n for n in ("type", "id", "title") if not getattr(args, n)]
    if missing:
        print(
            f"エラー: --{' --'.join(missing)}が必要である（または、--fromでまとめて指定する）",
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

    print(f"作成した: {path.relative_to(root).as_posix()}")
    print("フロントマターのdepends_onとrelatedを埋めてから、checkを回す")
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
        print(f"作成した: {created_path.relative_to(root).as_posix()}")
    for message in errors:
        print(f"エラー: {message}", file=sys.stderr)

    print(f"\n作成{len(created)}件 / 失敗{len(errors)}件")
    if created:
        print("フロントマターのdepends_onとrelatedを埋めてから、checkを回す")
    return 1 if errors else 0


def cmd_reset_samples(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    result = cleanup.remove(root, graph, args.tag, dry_run=not args.yes)

    targets = result["targets"]
    if not targets:
        print(f"tagsに{args.tag!r}を持つノードは無い")
        return 0

    verb = "削除した" if args.yes else "削除の対象"
    for node in targets:
        print(f"{verb}: {node.rel}  ({node.id} {node.title})")

    for rel in result["index_updated"]:
        print(f"一覧から外した: {rel}")

    if result["referenced_by"]:
        print("\n次のノードから参照されている。削除した後に、checkで確かめる。")
        for target_id, sources in sorted(result["referenced_by"].items()):
            print(f"  {target_id} <- {', '.join(sources)}")

    if not args.yes:
        print(f"\n{len(targets)}件。実際に削除するには、--yesを付ける")
        return 0

    print(f"\n{len(targets)}件を削除した。checkを回して、残った参照を直す")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)

    if not args.new_id and not args.new_slug:
        print("エラー: --toか--slugの、どちらかが要る", file=sys.stderr)
        return 1

    try:
        result = rename_node(
            root,
            graph,
            args.old_id,
            args.new_id or args.old_id,
            dry_run=args.dry_run,
            new_path_override=Path(args.path) if args.path else None,
            new_slug=args.new_slug,
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

    print(f"\n{len(result['edited'])}ファイル")
    if args.dry_run:
        print("--dry-runなので、書き込んでいない")
    else:
        print("syncを回してから、checkで確かめる")
    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)

    try:
        if args.label:
            # make updateが、マージのメッセージに入れるバージョンを読む。fetchはmake updateが済ませる
            print(upgrade_mod.inspect_label(root))
            return 0
        result = upgrade_mod.inspect(root)
    except upgrade_mod.UpgradeError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1

    for layer in result["layers"]:
        print(f"{layer['name']}")
        print(f"  ローカル:     {layer['local'] or '（まだ取り込んでいない）'}")
        print(f"  テンプレート: {layer['remote']}")
    print("")

    if result["ahead"]:
        print("ローカルのほうが新しいバージョンである。テンプレート本体で実行していないかを確かめる。")
        return 0

    if not result["behind"]:
        print("最新である。取り込むものは無い。")
        return 0

    if result["breaking"]:
        print("破壊的な変更を含む。マージしただけでは動かなくなる。")
        print("下の移行手順を読んでから取り込む。")
        print("")

    print(f"取り込みのバージョン: {result['label']}")
    print("")

    for layer in result["layers"]:
        for version, body in layer["entries"]:
            print(f"--- {layer['name']} {version} ---")
            print(body if body else "（記載なし）")
            print("")

    if result["files"]:
        print(f"変更されるファイル（{len(result['files'])}件）")
        for rel in result["files"][:20]:
            print(f"  {rel}")
        if len(result["files"]) > 20:
            print(f"  ... ほか{len(result['files']) - 20}件")
        print("")

    print(f"取り込む手順は、{schema.DOCS_DIR}/00-meta/template-upgrade.md（META-08）にある。")
    print("このコマンドは、何も書き込んでいない。")
    return 0


def _fit_budget(graph, distance: dict[str, int], budget: int):
    """近いノードから順に、本文の文字数の合計が`budget`に収まるところまで残す。

    焦点のノードは、予算を超えても残す。同じホップの中では、収まるものを残す。
    あるホップで1つでも外したら、それより遠いノードはすべて外す。
    近いノードを外したまま遠いノードを読むと、前提を飛ばして読むことになる。
    """
    order = sorted(distance, key=lambda node_id: (distance[node_id], node_id))
    kept: set[str] = set()
    omitted = []
    total = 0
    cut_after: int | None = None
    for node_id in order:
        hop = distance[node_id]
        size = len(graph.nodes[node_id].body)
        if hop > 0 and (
            (cut_after is not None and hop > cut_after) or total + size > budget
        ):
            omitted.append(graph.nodes[node_id])
            if cut_after is None:
                cut_after = hop
            continue
        kept.add(node_id)
        total += size
    return kept, omitted


def cmd_stats(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    sys.stdout.write(render_mod.summary(graph))
    sys.stdout.write(structure.report(graph))
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    root = _repo_root(args.root)
    graph = load(root)
    unknown = [i for i in (args.src, args.dst) if i not in graph.nodes]
    if unknown:
        print(f"エラー: 存在しないノード: {', '.join(unknown)}", file=sys.stderr)
        return 1

    steps = structure.shortest_path(graph, args.src, args.dst)
    if steps is None:
        # 逆向きなら繋がっていることがある。向きを取り違えただけかを知らせる
        steps = structure.shortest_path(graph, args.dst, args.src)
        if steps is None:
            print(f"{args.src}と{args.dst}は、depends_on・refinesで繋がっていない")
            return 1
        print(f"{args.src}から{args.dst}への経路は無い。逆向き（{args.dst}が{args.src}を前提にしている）なら、次のとおり繋がっている")

    for kind, node_id in steps:
        node = graph.nodes[node_id]
        prefix = f"  {kind} → " if kind else ""
        print(f"{prefix}{node_id} {node.title}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """本文の質を、AIに見てもらう。**終了コードは常に0である。**

    指摘は再現しないので、失敗として扱わない。CIからも呼ばない。
    """
    api_key = review.api_key_from_env()
    if api_key is None:
        print(f"{review.API_KEY_ENV}が設定されていないので、レビューを行わない。")
        print("これはグラフの問題ではない。checkは影響を受けない。")
        return 0

    root = _repo_root(args.root)
    graph = load(root)

    if args.focus:
        node = graph.nodes.get(args.focus)
        if node is None:
            print(f"ノードが見つからない: {args.focus}")
            return 0
        targets = [node]
    else:
        targets = review.select_nodes(graph, limit=args.limit)

    if not targets:
        print("レビューの対象が無い。")
        return 0

    # 何も言わずに通信しない。何件送るかを先に出す
    print(
        f"{len(targets)}ノードを{args.model}に送る"
        f"（{review.API_URL}と通信する）"
    )

    findings: list[review.Finding] = []
    usage: dict[str, int] = {}

    def counted(payload: dict, key: str) -> dict:
        data = review.call_api(payload, key)
        review.add_usage(usage, data)
        return data

    for node in targets:
        try:
            found = review.review_node(
                graph, node, api_key=api_key, model=args.model, transport=counted
            )
        except review.ReviewError as error:
            print(f"  {node.id}: {error}")
            continue
        findings.extend(found)
        if args.format != "json":
            mark = f"{len(found)}件" if found else "指摘なし"
            print(f"  {node.id} {node.title}: {mark}")

    if args.format == "json":
        print(
            json.dumps(
                {
                    "reviewed": len(targets),
                    "usage": usage,
                    "findings": [f.to_dict() for f in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"使ったトークン: {review.format_usage(usage)}")

    if findings:
        print("")
        for finding in findings:
            print("  " + finding.format())
        print("")
        codes = sorted({f.code for f in findings})
        print(f"指摘{len(findings)}件")
        for code in codes:
            print(f"  {code}: {review.FINDING_CODES[code]}")
        print("")
        print("これは助言であって、検査ではない。従う義務は無い。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.graph", description=__doc__)
    parser.add_argument(
        "--version",
        action="version",
        version=f"graph-doc-template {TEMPLATE_VERSION}",
        help="テンプレートのバージョンを表示する（変更履歴はTEMPLATE_CHANGELOG.md）",
    )
    parser.add_argument("--root", help="リポジトリの根（既定はこのファイルの場所から推定する）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="グラフを検証する")
    p_check.add_argument("--strict", action="store_true", help="警告も失敗として扱う")
    p_check.add_argument("--format", choices=("text", "json"), default="text")
    p_check.add_argument(
        "--no-history",
        action="store_true",
        help="gitを見ない（G011の放置の検出と、G015の追従漏れを飛ばす）",
    )
    p_check.add_argument(
        "--since",
        metavar="REF",
        help="G015で見る変更の窓。この参照との分岐点からHEADまで"
        "（省略したときは、未コミットの変更だけ）",
    )
    p_check.set_defaults(func=cmd_check)

    p_render = sub.add_parser("render", help="グラフを書き出す")
    p_render.add_argument(
        "--format", choices=("mermaid", "svg", "json", "dot"), default="mermaid"
    )
    p_render.add_argument(
        "--out",
        help="出力先（省略したときは標準出力）。--format svgと--intoを一緒に使うときは、"
        "SVGの書き出し先（省略したときはdocs/graph.svg）",
    )
    p_render.add_argument(
        "--into",
        metavar="PATH",
        help="Markdownのマーカーの中に図を書き込む（mermaidとsvg。README用）。"
        "svgでは、SVGをファイルに書き、マーカーの中にはその画像への参照を書く",
    )
    p_render.add_argument(
        "--check",
        action="store_true",
        help="--intoと一緒に使う。書き込まず、図が古ければ終了コード1（CI用）",
    )
    p_render.add_argument(
        "--focus",
        metavar="ID[,ID...]",
        help="指定したノードの近傍だけを描く（向きは無視して、両方向に辿る）",
    )
    p_render.add_argument(
        "--depth",
        type=int,
        default=1,
        metavar="N",
        help="--focusから何ホップまで含めるか（既定は1）",
    )
    p_render.add_argument(
        "--include-mentions",
        action="store_true",
        help="本文の[[ID]]から生まれるリンクも含める",
    )
    p_render.add_argument(
        "--aggregate",
        action="store_true",
        help="型ごとに1つの箱へまとめる（ノードが増えても図が大きくならない。G018を避ける）。"
        "mermaidとsvgで使える",
    )
    p_render.add_argument(
        "--hide-edges",
        metavar="KIND[,KIND...]",
        help="挙げた種類の線を描かない（例: decides,supersedes）。"
        "その線しか持たないノードは、図から外れる",
    )
    p_render.add_argument(
        "--type",
        metavar="TYPE[,TYPE...]",
        help="挙げた種別のノードだけを描く（例: domain）。"
        "mermaidでは、ほかの種別を型ごとの箱にまとめる",
    )
    p_render.add_argument(
        "--reduce",
        action="store_true",
        help="ほかのdepends_onを辿れば分かる依存を、図から省く（A→B→CがあるときのA→C）。"
        "検査とフロントマターは変えない",
    )
    p_render.add_argument(
        "--budget",
        type=int,
        metavar="CHARS",
        help="--format jsonと--focusと一緒に使う。本文の文字数の合計がこれに収まるまで、"
        "近いノードから残す。外したノードはomittedに名前だけを出す",
    )
    p_render.set_defaults(func=cmd_render)

    p_path = sub.add_parser(
        "path",
        help="2つのノードを結ぶ前提の経路を出す（depends_on・refinesを辿る）",
    )
    p_path.add_argument("src", metavar="FROM", help="依存している側のid（例: UC-01）")
    p_path.add_argument("dst", metavar="TO", help="前提の側のid（例: ARCH-01）")
    p_path.set_defaults(func=cmd_path)

    p_sync = sub.add_parser("sync", help="関連ドキュメントのブロックを作り直す")
    p_sync.add_argument("--dry-run", action="store_true", help="書き込まずに、差分だけを表示する")
    p_sync.add_argument(
        "--check",
        action="store_true",
        help="書き込まず、更新が必要なら終了コード1（CI用）",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_linkify = sub.add_parser(
        "linkify",
        help="本文の[[ID]]を相対リンクに直す（GitHub上でも辿れるようにする）",
    )
    p_linkify.add_argument("--dry-run", action="store_true", help="書き込まずに、差分だけを表示する")
    p_linkify.add_argument(
        "--check",
        action="store_true",
        help="書き換えが必要なら終了コード1（CI用）",
    )
    p_linkify.set_defaults(func=cmd_linkify)

    p_new = sub.add_parser("new", help="新しいノードを作る")
    # 使える値はgraph.tomlで変わるので、choicesでは絞らない。知らない値はcreateが断る
    p_new.add_argument("--type", help="ノード種別（例: usecase）")
    p_new.add_argument("--id", help="例: UC-02")
    p_new.add_argument("--title")
    p_new.add_argument("--slug", help="ファイル名に使う英数字。省略したときはtitleから作る")
    p_new.add_argument("--status", default="draft", choices=schema.STATUSES)
    p_new.add_argument(
        "--template",
        # 設定を読む前に作る文字列なので、docs_dirの値は使えない
        help=f"使う雛形の名前（文書のフォルダの{TEMPLATE_DIR}/<名前>.md。フォルダの既定はdocs/）。"
        "省略したときは、graph.tomlの種別のtemplateに書いた雛形か、typeと同じ名前の雛形",
    )
    p_new.add_argument(
        "--from",
        dest="from_file",
        metavar="PATH",
        help="1行に1ノードを書いたファイルから、まとめて作る（`type | id | title | slug`の形式）",
    )
    p_new.set_defaults(func=cmd_new)

    p_reset = sub.add_parser(
        "reset-samples",
        help="サンプルノードをまとめて取り除く（テンプレートを複製した直後に使う）",
    )
    p_reset.add_argument(
        "--tag",
        default=cleanup.DEFAULT_TAG,
        help=f"削除の対象とするtagsの値（既定は{cleanup.DEFAULT_TAG}）",
    )
    p_reset.add_argument(
        "--yes",
        action="store_true",
        help="実際に削除する。付けない場合は、対象を表示するだけ",
    )
    p_reset.set_defaults(func=cmd_reset_samples)

    p_rename = sub.add_parser(
        "rename",
        help="ノードのidやファイル名を変え、すべての参照を追随させる",
    )
    p_rename.add_argument("--from", dest="old_id", required=True, metavar="ID", help="例: API-01")
    p_rename.add_argument(
        "--to", dest="new_id", metavar="ID", help="新しいid（例: CON-01）。省略すると据え置く"
    )
    p_rename.add_argument(
        "--slug",
        dest="new_slug",
        metavar="SLUG",
        help="ファイル名の後半だけを変える（例: view）。idは変わらない",
    )
    p_rename.add_argument(
        "--path",
        metavar="PATH",
        help="移動先を明示する（種別からディレクトリが決まらないindexなどで使う）",
    )
    p_rename.add_argument(
        "--dry-run", action="store_true", help="書き込まずに、変更の内容だけを表示する"
    )
    p_rename.set_defaults(func=cmd_rename)

    p_upgrade = sub.add_parser(
        "upgrade",
        help="テンプレートとの差を調べる（読み取りのみ。取り込みは手で行う）",
    )
    p_upgrade.add_argument(
        "--label",
        action="store_true",
        help="取り込みのバージョン（ブランチ名とマージのメッセージに入れるもの）だけを出す。fetchはしない",
    )
    p_upgrade.set_defaults(func=cmd_upgrade)

    p_review = sub.add_parser(
        "review",
        help="本文の質をAIに見てもらう（任意・通信あり・CIでは回さない）",
    )
    p_review.add_argument("--focus", help="このノードだけを見る")
    p_review.add_argument(
        "--limit",
        type=int,
        default=review.DEFAULT_LIMIT,
        help=f"送るノード数の上限（既定は{review.DEFAULT_LIMIT}。0なら全件）",
    )
    p_review.add_argument(
        "--model", default=review.DEFAULT_MODEL, help="使うモデル"
    )
    p_review.add_argument("--format", choices=("text", "json"), default="text")
    p_review.set_defaults(func=cmd_review)

    p_stats = sub.add_parser("stats", help="集計と、構造の見直しの候補を表示する")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def _make_stdio_safe() -> None:
    """出力の途中で落ちないようにする。

    `check`の警告は、文書の本文をそのまま引用する（`G013`など）。本文には、
    Windowsの既定のコードページ（cp932など）で表現できない文字が、混ざることがある。
    そのままprintすると、UnicodeEncodeErrorで途中まで出したまま止まり、
    **グラフは正しいのに、終了コードが1になる。** 本当の検証の失敗と区別が付かない。

    そこで、UTF-8に切り替える。ファイルの書き出しは元からUTF-8なので、
    これで入出力の扱いが揃う。`errors="replace"`は、表現できない文字が
    残った場合（サロゲートを含むパスなど）に備えたものである。
    """
    for stream in (sys.stdout, sys.stderr):
        # pythonwではNone、テストではStringIOに差し替わっていることがある
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
    try:
        schema.configure(_repo_root(args.root))
    except schema.ConfigError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return args.func(args)
