"""グラフの検証ルール。

ルールは 1 つの関数 = 1 つのコード。エラーメッセージに必ずコードを載せるので、
「G007 が出た」で規約のどの条項かをすぐ引ける。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import render, schema
from .frontmatter import as_list
from .loader import MDLINK_RE, WIKILINK_RE, strip_non_prose
from .model import ERROR, WARN, Graph, Issue, Node
from .rename import _scan_targets

# ルールコードと概要（レポートと docs/00-meta/graph-rules.md の対応表に使う）
RULE_INDEX: dict[str, str] = {
    "G000": "docs/ の構造が不正",
    "G001": "フロントマターが読めない / 必須キー不足",
    "G002": "id が重複している",
    "G003": "id 規約・type 語彙・配置ディレクトリの不一致",
    "G004": "リンク先が存在しない（リンク切れ）",
    "G005": "ルート目次から到達できない孤立ノード",
    "G006": "依存関係が循環している",
    "G007": "層の逆流（下位層が上位層に依存している）",
    "G008": "refines が異なる種別のノードを指している",
    "G009": "status の語彙違反 / 成熟度の不整合",
    "G010": "related が片側にしか書かれていない",
    "G011": "確定していないまま長期間放置されている",
    "G012": "参照されすぎている（分割を検討）",
    "G013": "依存先の用語表が使わない語（旧称）を使っている",
    "G014": "テンプレートの必須の節が無い",
    "G015": "依存先が変わったのに追従していない",
    "G016": "implemented_by の指し先が存在しない",
    "G017": "文書と実装のどちらか片方だけが変わった",
    "G018": "README の図が GitHub の描画上限に近い / 超えている",
    "G019": "Markdown の表が途中で切れている",
    "G020": "取り下げた決定を現在の根拠として引いている",
    "G021": "自動生成ブロックより後ろに本文がある",
    "G022": "同じ用語が複数のドメインノードで定義されている",
}


def check_all(
    graph: Graph,
    *,
    history: dict[str, date] | None = None,
    today: date | None = None,
    changed: set[str] | None = None,
    changed_files: set[str] | None = None,
) -> list[Issue]:
    """`history` は `{相対パス: 最終コミット日}`。無ければ G011 を飛ばす。

    `changed` は「この変更で動いたノードの id」。無ければ G015 を飛ばす。
    `changed_files` は同じ窓で動いたファイルすべて。無ければ G017 を飛ばす。
    """
    issues: list[Issue] = list(graph.load_issues)
    for rule in (
        rule_g003_identity,
        rule_g004_broken_links,
        rule_g005_orphans,
        rule_g006_cycles,
        rule_g007_layers,
        rule_g008_refines_type,
        rule_g009_status,
        rule_g010_related_symmetry,
        rule_g012_hub_nodes,
        rule_g013_term_consistency,
        rule_g014_required_sections,
        rule_g016_implementation_exists,
        rule_g018_diagram_size,
        rule_g019_broken_tables,
        rule_g020_deprecated_references,
        rule_g021_content_after_auto_block,
        rule_g022_duplicate_terms,
    ):
        issues.extend(rule(graph))

    if history:
        issues.extend(rule_g011_stale(graph, history, today or date.today()))

    if changed:
        issues.extend(rule_g015_unfollowed_changes(graph, changed))

    if changed_files:
        issues.extend(
            rule_g017_implementation_drift(graph, changed or set(), changed_files)
        )

    return sorted(issues, key=lambda i: (i.severity != ERROR, i.code, i.location))


# --------------------------------------------------------------------------
# G003: 同一性（id / type / 置き場所）
# --------------------------------------------------------------------------
def rule_g003_identity(graph: Graph) -> list[Issue]:
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        spec = schema.NODE_TYPES.get(node.type)
        if spec is None:
            issues.append(
                Issue(
                    "G003",
                    ERROR,
                    f"未知の type {node.type!r}（許可: {', '.join(schema.NODE_TYPES)}）",
                    node.rel,
                )
            )
            continue

        prefix = spec["prefix"]
        if not node.id.startswith(prefix + "-"):
            issues.append(
                Issue(
                    "G003",
                    ERROR,
                    f"type={node.type} の id は {prefix}- で始める必要があります（現在: {node.id}）",
                    node.rel,
                )
            )

        expected_dir = spec["dir"]
        if expected_dir is not None:
            rel_to_docs = node.rel[len(schema.DOCS_DIR) + 1 :]
            if not rel_to_docs.startswith(expected_dir + "/"):
                issues.append(
                    Issue(
                        "G003",
                        ERROR,
                        f"type={node.type} は {schema.DOCS_DIR}/{expected_dir}/ に置いてください",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# G004: リンク切れ
# --------------------------------------------------------------------------
def rule_g004_broken_links(graph: Graph) -> list[Issue]:
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        for edge in node.edges:
            if edge.resolved:
                continue
            where = "フロントマター" if edge.origin == "frontmatter" else "本文"
            issues.append(
                Issue(
                    "G004",
                    ERROR,
                    f"{where}の {edge.kind}: {edge.dst!r} に対応するノードがありません",
                    node.rel,
                )
            )
    return issues


# --------------------------------------------------------------------------
# G005: 孤立ノード
# --------------------------------------------------------------------------
def rule_g005_orphans(graph: Graph) -> list[Issue]:
    if schema.ROOT_NODE_ID not in graph.nodes:
        return [
            Issue(
                "G005",
                ERROR,
                f"ルート目次ノード {schema.ROOT_NODE_ID} が見つかりません",
                "graph",
            )
        ]

    reachable: set[str] = set()
    stack = [schema.ROOT_NODE_ID]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        node = graph.nodes.get(current)
        if node is None:
            continue
        for edge in node.edges:
            if edge.resolved and edge.dst not in reachable:
                stack.append(edge.dst)

    return [
        Issue(
            "G005",
            ERROR,
            f"{node.id} はルート目次から辿れません（どこかの index.md に載せてください）",
            node.rel,
        )
        for node in graph.sorted_nodes()
        if node.id not in reachable
    ]


# --------------------------------------------------------------------------
# G006: 循環依存
# --------------------------------------------------------------------------
def rule_g006_cycles(graph: Graph) -> list[Issue]:
    acyclic_kinds = {k for k, spec in schema.EDGE_KINDS.items() if spec["acyclic"]}
    adjacency: dict[str, list[str]] = {
        node.id: sorted(
            {e.dst for e in node.edges if e.resolved and e.kind in acyclic_kinds}
        )
        for node in graph.sorted_nodes()
    }

    issues: list[Issue] = []
    reported: set[frozenset[str]] = set()
    state: dict[str, int] = {}  # 0=未訪問 1=探索中 2=完了
    path: list[str] = []

    def visit(node_id: str) -> None:
        state[node_id] = 1
        path.append(node_id)
        for nxt in adjacency.get(node_id, []):
            if state.get(nxt, 0) == 0:
                visit(nxt)
            elif state.get(nxt) == 1:
                cycle = path[path.index(nxt) :] + [nxt]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    node = graph.nodes[nxt]
                    issues.append(
                        Issue(
                            "G006",
                            ERROR,
                            "依存が循環しています: " + " -> ".join(cycle),
                            node.rel,
                        )
                    )
        path.pop()
        state[node_id] = 2

    for node_id in adjacency:
        if state.get(node_id, 0) == 0:
            visit(node_id)

    return issues


# --------------------------------------------------------------------------
# G007: 層の逆流
# --------------------------------------------------------------------------
def rule_g007_layers(graph: Graph) -> list[Issue]:
    issues: list[Issue] = []
    layered_kinds = {k for k, spec in schema.EDGE_KINDS.items() if spec["layered"]}

    for node in graph.sorted_nodes():
        src_spec = schema.NODE_TYPES.get(node.type)
        if src_spec is None or src_spec["exempt_layer"]:
            continue

        for edge in node.edges:
            if edge.kind not in layered_kinds or not edge.resolved:
                continue
            target = graph.nodes[edge.dst]
            dst_spec = schema.NODE_TYPES.get(target.type)
            if dst_spec is None or dst_spec["exempt_layer"]:
                continue
            if dst_spec["layer"] > src_spec["layer"]:
                issues.append(
                    Issue(
                        "G007",
                        ERROR,
                        f"{node.id}({node.type}) が上位層の {target.id}({target.type}) に "
                        f"{edge.kind} しています。依存は抽象度の高い側へ向けてください",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# G008: refines の種別一致
# --------------------------------------------------------------------------
def rule_g008_refines_type(graph: Graph) -> list[Issue]:
    issues: list[Issue] = []
    same_type_kinds = {k for k, spec in schema.EDGE_KINDS.items() if spec["same_type"]}

    for node in graph.sorted_nodes():
        for edge in node.edges:
            if edge.kind not in same_type_kinds or not edge.resolved:
                continue
            target = graph.nodes[edge.dst]
            if target.type != node.type:
                issues.append(
                    Issue(
                        "G008",
                        ERROR,
                        f"{edge.kind} は同じ type 同士のみです"
                        f"（{node.id}:{node.type} -> {target.id}:{target.type}）",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# G009: status
# --------------------------------------------------------------------------
def rule_g009_status(graph: Graph) -> list[Issue]:
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        if node.status not in schema.STATUSES:
            issues.append(
                Issue(
                    "G009",
                    ERROR,
                    f"未知の status {node.status!r}（許可: {', '.join(schema.STATUSES)}）",
                    node.rel,
                )
            )
            continue

        if node.status != "stable":
            continue

        for edge in node.out_edges("depends_on"):
            if not edge.resolved:
                continue
            target = graph.nodes[edge.dst]
            if target.status in schema.UNSTABLE_STATUSES:
                issues.append(
                    Issue(
                        "G009",
                        WARN,
                        f"stable な {node.id} が {target.status} の {target.id} に依存しています",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# G011: 放置された未確定ノード
# --------------------------------------------------------------------------
def rule_g011_stale(graph: Graph, history: dict[str, date], today: date) -> list[Issue]:
    """`draft` / `review` のまま長く動きがないノードを警告する。

    「いつ draft になったか」ではなく「最後に触られたのはいつか」で見る。
    書きかけでも手が入り続けているなら問題ではなく、**止まっていることが問題**。
    """
    issues: list[Issue] = []

    for node in graph.sorted_nodes():
        if node.status not in schema.STALE_STATUSES:
            continue

        last = history.get(node.rel)
        if last is None:
            continue  # 未コミットのファイルなど。判断材料がないので飛ばす

        days = (today - last).days
        if days > schema.STALE_AFTER_DAYS:
            issues.append(
                Issue(
                    "G011",
                    WARN,
                    f"{node.status} のまま {days} 日間更新されていません"
                    f"（最終更新 {last.isoformat()}）。"
                    "確定させるか、不要なら削除してください",
                    node.rel,
                )
            )

    return issues


# --------------------------------------------------------------------------
# G012: 参照されすぎているノード
# --------------------------------------------------------------------------
def rule_g012_hub_nodes(graph: Graph) -> list[Issue]:
    """多くのノードから `depends_on` されているノードを警告する。

    参照が集まるノードは、複数の概念が混ざっていることが多い。
    変更したときの影響範囲が広く、追従の確認コストが跳ね上がる。
    """
    counts: dict[str, int] = {}
    for node in graph.sorted_nodes():
        for edge in node.out_edges("depends_on"):
            if edge.resolved:
                counts[edge.dst] = counts.get(edge.dst, 0) + 1

    limit = schema.MAX_INCOMING_DEPENDENCIES
    return [
        Issue(
            "G012",
            WARN,
            f"{count} ノードから depends_on されています（上限 {limit}）。"
            "概念が混ざっていないか点検し、必要なら分割してください",
            graph.nodes[node_id].rel,
        )
        for node_id, count in sorted(counts.items())
        if count > limit
    ]


# --------------------------------------------------------------------------
# G010: related の相互性
# --------------------------------------------------------------------------
def rule_g010_related_symmetry(graph: Graph) -> list[Issue]:
    symmetric_kinds = {k for k, spec in schema.EDGE_KINDS.items() if spec["symmetric"]}
    issues: list[Issue] = []

    for node in graph.sorted_nodes():
        for edge in node.edges:
            if edge.kind not in symmetric_kinds or not edge.resolved:
                continue
            target: Node = graph.nodes[edge.dst]
            back = {e.dst for e in target.out_edges(edge.kind)}
            if node.id not in back:
                issues.append(
                    Issue(
                        "G010",
                        WARN,
                        f"{target.id} 側の {edge.kind} に {node.id} がありません（相互リンク推奨）",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# 用語表（G013 / G022 / 用語の一覧 / review の A003 が読む）
# --------------------------------------------------------------------------
# 「## 用語」の節。次の同レベル見出しか文末まで。
_TERM_SECTION_RE = re.compile(
    rf"^##\s+{re.escape(schema.TERM_SECTION_HEADING)}\s*$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
# セル末尾の丸括弧。旧称になった経緯か、使ってよい条件が入っている
_TRAILING_NOTE_RE = re.compile(r"[（(]([^）)]*)[）)]\s*$")
_INNER_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
_SEPARATOR_RE = re.compile(r"[、,]")
_EMPHASIS_RE = re.compile(r"\*\*|__")
_SNIPPET_PAD = 20


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":", " "} for cell in cells)


def term_table_lines(body: str) -> list[str]:
    """「用語」の節にある最初の表を、行のまま返す。用語表でなければ空。

    **用語が空の行（雛形の空行）は落とす。** 見出しと区切りの行は残す。
    用語の一覧（`sync`）が、ノードの表をそのまま写すのに使う。
    """
    section = _TERM_SECTION_RE.search(body)
    if section is None:
        return []

    lines: list[str] = []
    for line in section.group(1).splitlines():
        if line.strip().startswith("|"):
            lines.append(line.strip())
        elif lines:
            break  # 最初の表が終わった

    if not lines:
        return []
    header = _cells(lines[0])
    if schema.TERM_COLUMN not in header:
        return []  # 見出しが違う表。用語表ではないので触らない
    term_at = header.index(schema.TERM_COLUMN)

    rest = lines[1:]
    separator = [line for line in rest[:1] if _is_separator(_cells(line))]
    rows = []
    for line in rest[len(separator) :]:
        cells = _cells(line)
        if _is_separator(cells) or term_at >= len(cells) or not cells[term_at]:
            continue
        rows.append(line)
    if not rows:
        return []
    return [lines[0], *separator, *rows]


def term_rows(body: str) -> list[dict[str, str]]:
    """「用語」表を、行ごとの `{列の見出し: セル}` にする。

    列は位置ではなく見出しで探す。列が増えても壊れないようにするため。
    """
    lines = term_table_lines(body)
    if not lines:
        return []
    header = _cells(lines[0])
    rows = []
    for line in lines[1:]:
        cells = _cells(line)
        if _is_separator(cells):
            continue
        rows.append({name: cells[i] if i < len(cells) else "" for i, name in enumerate(header)})
    return rows


def forbidden_terms(body: str) -> dict[str, tuple[str, str]]:
    """用語表から `{使わない語: (正しい用語, 注記)}` を作る。

    読むのは「旧称」列と、1.19 までの「使ってはいけない言い換え」列
    （`schema.TERM_OLD_NAME_COLUMNS`）。**古い列名も読み続ける。** 読まなくなると、
    取り込んだ派生で `G013` が黙って止まる。
    """
    found: dict[str, tuple[str, str]] = {}
    for row in term_rows(body):
        term = row.get(schema.TERM_COLUMN, "")
        for column in schema.TERM_OLD_NAME_COLUMNS:
            raw = row.get(column, "")
            if not term or not raw:
                continue

            # 末尾の括弧はセル全体にかかる注記として扱う。
            # 「スコア、点数（文字列だった頃の名前）」の注記は両方にかかっている
            note_match = _TRAILING_NOTE_RE.search(raw)
            note = note_match.group(1).strip() if note_match else ""
            listed = _TRAILING_NOTE_RE.sub("", raw)

            for chunk in _SEPARATOR_RE.split(listed):
                word = _INNER_PAREN_RE.sub("", chunk).strip()
                if len(word) < schema.TERM_MIN_LENGTH:
                    continue
                found.setdefault(word, (term, note))

    return found


def _prerequisites(graph: Graph, node_id: str) -> list[str]:
    """`depends_on` / `refines` を辿って到達できるノードを返す（間接も含む）。

    **直接の依存だけでは足りない。** 契約はユースケース経由でドメインに繋がるので、
    直接に絞ると「契約が語彙を破っている」場合を丸ごと見落とす。
    """
    kinds = {"depends_on", "refines"}
    seen: set[str] = set()
    stack = [node_id]
    while stack:
        node = graph.nodes.get(stack.pop())
        if node is None:
            continue
        for edge in node.edges:
            if edge.resolved and edge.kind in kinds and edge.dst not in seen:
                seen.add(edge.dst)
                stack.append(edge.dst)
    return sorted(seen)


def _snippet(text: str, index: int, word: str) -> str:
    start = max(0, index - _SNIPPET_PAD)
    end = index + len(word) + _SNIPPET_PAD
    body = " ".join(text[start:end].split())
    return f"{'…' if start else ''}{body}{'…' if end < len(text) else ''}"


def rule_g013_term_consistency(graph: Graph) -> list[Issue]:
    """依存先の用語表が「旧称」に挙げた語の使用を警告する。

    用語は**同じ意味なら同じ用語**で揃える。言い換えを並べて塞ぐことはしない
    （並べ尽くせず、文脈で意味が変わる語で断り書きが増え続けた。1.20.0）。
    ただし**改名で使わなくなった語は、文字列で確実に言える。** そこだけを機械で見る。

    **語の意味までは分からない。** 旧称が別の概念の名前として正しく使われている場合や、
    否定するために持ち出した場合も引っかかる。だから警告に留め、判断の材料
    （注記と前後の文）を出すところまでを仕事とする。
    """
    vocabulary = {
        node.id: terms
        for node in graph.sorted_nodes()
        if (terms := forbidden_terms(node.body))
    }
    if not vocabulary:
        return []

    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        # 用語表そのものは対象外。旧称を「挙げている」ことは「使っている」ことではない
        text = strip_non_prose(_TERM_SECTION_RE.sub(" ", node.body))

        for owner_id in _prerequisites(graph, node.id):
            for word, (term, note) in sorted(vocabulary.get(owner_id, {}).items()):
                count = text.count(word)
                if not count:
                    continue
                where = f"（{count} 箇所）" if count > 1 else ""
                reason = f"。{owner_id} の注記: {note}" if note else ""
                issues.append(
                    Issue(
                        "G013",
                        WARN,
                        f"{word!r} は {owner_id} の用語表が使わない語に挙げています"
                        f"{where}。{term!r} を使ってください{reason}"
                        f" / {_snippet(text, text.find(word), word)}",
                        node.rel,
                    )
                )
    return issues


# --------------------------------------------------------------------------
# G014: テンプレートの必須の節
# --------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def sections(body: str) -> list[str]:
    """本文の `## ` 見出しを順に返す。

    `node.body` は sync が生成するブロックを取り除いた後の本文なので、
    「関連ドキュメント（自動生成）」は数えない。
    コードブロックの中の `## ` も落とす（雛形の説明に現れる）。
    """
    return _HEADING_RE.findall(strip_non_prose(body))


def required_sections(node: Node) -> tuple[str, ...]:
    """そのノードに求める節。refines を持つなら親から切り出した側の定義を使う。"""
    if node.out_edges("refines"):
        refined = schema.REQUIRED_SECTIONS_REFINED.get(node.type)
        if refined is not None:
            return refined
    return schema.REQUIRED_SECTIONS.get(node.type, ())


def rule_g014_required_sections(graph: Graph) -> list[Issue]:
    """type ごとに決めた必須の節が本文にあるかを見る。

    **雛形の全節ではなく「これが無いと文書として成立しない」節だけ**を対象にする
    （schema.REQUIRED_SECTIONS）。全節を必須にすると、意図的に省いた節まで
    警告になり、「層を無理に埋めない」という方針と衝突する。

    節が空でないかまでは見ない。見出しがあることしか確かめられないので、
    **「なし」と書いてあれば通る。** それでよい。書く場所を用意させることが目的で、
    書かないと決めたことを明示させるのもこのルールの役目である。
    """
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        wanted = required_sections(node)
        if not wanted:
            continue
        have = set(sections(node.body))
        missing = [name for name in wanted if name not in have]
        if not missing:
            continue
        issues.append(
            Issue(
                "G014",
                WARN,
                f"{node.type} に必要な節がありません: "
                + " / ".join(repr(name) for name in missing)
                + "。書くことが無いなら「なし」と書く",
                node.rel,
            )
        )
    return issues


# --------------------------------------------------------------------------
# G015: 依存先が変わったのに追従していない
# --------------------------------------------------------------------------
def rule_g015_unfollowed_changes(graph: Graph, changed: set[str]) -> list[Issue]:
    """この変更で動いたノードの、依存元が動いていないことを知らせる。

    **グラフの状態ではなく、変更の状態を見る唯一のルールである。**
    窓（`check --since`、既定は作業ツリー）の外では何も出ない。

    「このノードを参照しているノード」は `sync` が一覧を作っているが、
    **見たかどうかは記録されない。** 規約の散文に置くと守られないので、
    変更した瞬間に一覧を突きつけるところまでを機械の仕事にする。

    **追従が要るとは限らない。** 依存先の変更が依存元に関係しないことは多い。
    見て「変えなくてよい」と判断したなら、そのまま進めてよい。
    """
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        if node.id in changed:
            continue
        moved = sorted(
            {
                edge.dst
                for edge in node.edges
                if edge.kind in ("depends_on", "refines")
                and edge.resolved
                and edge.dst in changed
            }
        )
        if not moved:
            continue
        issues.append(
            Issue(
                "G015",
                WARN,
                "依存先が変わりました: "
                + " / ".join(moved)
                + "。追従が要るか確かめてください（要らなければそのままでよい）",
                node.rel,
            )
        )
    return issues


# --------------------------------------------------------------------------
# G016 / G017: 実装との対応（implemented_by）
# --------------------------------------------------------------------------
def implemented_by(node: Node) -> list[str]:
    """そのノードが規定している実装のパス。宣言していなければ空。"""
    return as_list(node.meta.get(schema.IMPLEMENTED_BY_KEY))


def rule_g016_implementation_exists(graph: Graph) -> list[Issue]:
    """`implemented_by` の指し先がリポジトリに存在するかを見る。

    **本文の `[[ID]]` に対する G004 と同じ役割。** 指し先が消えても文書は
    そのまま読めてしまうので、機械が確かめないと静かに腐る。

    リポジトリルートが分からない場合（部分グラフを手で組んだときなど）は
    **何も言わない。** 確かめられないものを落とさない。
    """
    if graph.root is None:
        return []

    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        for target in implemented_by(node):
            if (graph.root / target).exists():
                continue
            issues.append(
                Issue(
                    "G016",
                    ERROR,
                    f"implemented_by の指し先がありません: {target!r}。"
                    "同じリポジトリの中のパスだけを指せます",
                    node.rel,
                )
            )
    return issues


def rule_g017_implementation_drift(
    graph: Graph, changed: set[str], changed_files: set[str]
) -> list[Issue]:
    """文書と実装のどちらか片方だけが変わったことを知らせる。

    **G015 を文書と実装の境界にまたがらせたもの。** 見ているのは同じく
    変更の窓の中だけで、両方が同じ窓に入っていれば何も言わない。

    **どちらの向きも出す。** 実装だけ動いたなら文書が遅れており、
    文書だけ動いたなら実装が遅れている。どちらが正しいかは機械には分からない。

    **追従が要るとは限らない。** 実装の内部を整理しただけなら文書は動かない。
    「見たか」を確かめるところまでが仕事である。
    """
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        targets = implemented_by(node)
        if not targets:
            continue

        moved = sorted(
            target
            for target in targets
            if any(f == target or f.startswith(target.rstrip("/") + "/")
                   for f in changed_files)
        )
        node_moved = node.id in changed

        if moved and not node_moved:
            issues.append(
                Issue(
                    "G017",
                    WARN,
                    "実装が変わりました: "
                    + " / ".join(moved)
                    + "。文書の追従が要るか確かめてください",
                    node.rel,
                )
            )
        elif node_moved and not moved:
            issues.append(
                Issue(
                    "G017",
                    WARN,
                    "この文書が変わりましたが、実装は動いていません: "
                    + " / ".join(targets)
                    + "。実装の追従が要るか確かめてください",
                    node.rel,
                )
            )
    return issues


# --------------------------------------------------------------------------
# G018: README の図が GitHub の描画上限に近い
# --------------------------------------------------------------------------
def rule_g018_diagram_size(graph: Graph) -> list[Issue]:
    """README に書き込まれた図が、GitHub の描画上限に収まっているか。

    **グラフからではなく、README に実際に入っている図を数える。**
    `--aggregate` や `--focus` で間引いているリポジトリでも正しく測れるし、
    GitHub が描こうとするのもその図そのものだから。

    上限を超えている場合はエラーにする。図が丸ごと描画されず、README が
    壊れた状態になっているため。近づいているだけなら警告に留める。
    """
    if graph.root is None:
        return []

    readme = graph.root / "README.md"
    count = render.count_edges_in_markdown(readme)
    if count is None or count < schema.MERMAID_WARN_EDGES:
        return []

    # ちょうど上限でも落ちる。GitHub の文言が
    # 「500 edges found, but the limit is 500」で、その時点で描画されていない。
    if count >= schema.MERMAID_MAX_EDGES:
        return [
            Issue(
                "G018",
                ERROR,
                f"README の図のエッジが {count} 本で、GitHub の上限 "
                f"{schema.MERMAID_MAX_EDGES} 本に達しています。"
                "GitHub 上では図が描画されません。"
                "Makefile の README_GRAPH_ARGS に --aggregate を足して"
                "型ごとにまとめてください",
                "README.md",
            )
        ]

    return [
        Issue(
            "G018",
            WARN,
            f"README の図のエッジが {count} 本で、GitHub の上限 "
            f"{schema.MERMAID_MAX_EDGES} 本に近づいています。"
            "超えると図が丸ごと描画されなくなります",
            "README.md",
        )
    ]


# --------------------------------------------------------------------------
# G019: Markdown の表が途中で切れている
# --------------------------------------------------------------------------
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _fenced_lines(lines: list[str]) -> list[bool]:
    """各行がコードブロックの中かどうか。**囲みの行そのものも中とみなす。**

    規約文書や雛形は「表の書き方」をコードブロックで例示する。
    そこを数えると、正しい文書が落ちる。
    """
    inside = False
    flags: list[bool] = []
    for line in lines:
        if FENCE_RE.match(line):
            inside = not inside
            flags.append(True)
            continue
        flags.append(inside)
    return flags


def find_broken_tables(text: str) -> list[tuple[int, str]]:
    """表から切り離された行を `(行番号, 行の中身)` で返す。

    Markdown の表は**ヘッダ行と区切り行（`| --- |`）で始まり、
    空行か本文で終わる。** 途中に段落や空行が入ると、そこから先の行は
    表ではなくただの文字列として描画される。

    判定は 2 つだけ。`|` で始まる行のうち、

    - 直前の行も `|` で始まる（＝表の続き）
    - 次の行が区切り行（＝正しい表の先頭）

    のどちらでもないものを切り離された行とみなす。
    """
    lines = text.split("\n")
    fenced = _fenced_lines(lines)
    broken: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if fenced[i] or not line.lstrip().startswith("|"):
            continue
        if i > 0 and not fenced[i - 1] and lines[i - 1].lstrip().startswith("|"):
            continue
        if i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
            continue
        broken.append((i + 1, line.strip()))

    return broken


def rule_g019_broken_tables(graph: Graph) -> list[Issue]:
    """表の途中に段落や空行が入って、描画が壊れていないか。

    **グラフの検査は通るのに、GitHub 上の表示だけが壊れる。**
    用語表を段落で分断した実例があり、`G013` のパーサは行ベースなので
    取り残された行も拾えていた。**機械は困らず、読む人だけが困る。**

    `docs/` の下だけでなく README や CONTRIBUTING も見る。実際に壊れていたのは
    README で、しかも `merge=ours` のせいで上流の修正が伝播していなかった。
    """
    if graph.root is None:
        return []

    issues: list[Issue] = []
    for path in _scan_targets(graph.root, graph.root / schema.DOCS_DIR):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue  # 読めないものは他のルールが指す

        rel = path.relative_to(graph.root).as_posix()
        for lineno, line in find_broken_tables(text):
            issues.append(
                Issue(
                    "G019",
                    ERROR,
                    f"{lineno} 行目の表の行が、表から切り離されています。"
                    "直前に段落か空行が入っているため、GitHub 上では"
                    f"ただの文字列として描画されます: {line[:60]}",
                    rel,
                )
            )

    return issues


# --------------------------------------------------------------------------
# G020: 取り下げた決定を現在の根拠として引いている
# --------------------------------------------------------------------------
PARAGRAPH_RE = re.compile(r"\n\s*\n")


def paragraphs(body: str) -> list[str]:
    """空行で区切った段落。**表は 1 つの段落にまとまる。**

    リンクとして数えない場所（コードブロック・コメント）は先に落とす。
    雛形の記入案内は HTML コメントの中にあり、そこに書いた例を数えると
    雛形そのものが落ちる。
    """
    return PARAGRAPH_RE.split(strip_non_prose(body))


def _referenced_ids(text: str, base: Path, by_path: dict[Path, Node]) -> set[str]:
    """その断片が指しているノードの id。解決できないリンクは無視する（G004 の仕事）。

    `base` は相対リンクを解決する起点。**ノードは自分のディレクトリ、
    README はリポジトリの根**を渡す。書き方の基準が違うだけで、判定は同じ。
    """
    found = {raw.strip() for raw in WIKILINK_RE.findall(text)}
    for href in MDLINK_RE.findall(text):
        if not href.endswith(".md") or "://" in href:
            continue
        linked = by_path.get((base / href).resolve())
        if linked is not None:
            found.add(linked.id)
    return found


def superseded_index(graph: Graph) -> dict[str, set[str]]:
    """`取り下げられた id -> それを置き換えたノードの id` の索引。

    **連鎖を辿る。** `A → B → C` と置き換わったとき、`A` の置き換え先は
    `B` と `C` の両方とする。**現在の決定（連鎖の先端）を指すのは、直接の
    置き換え先を指すより正しい。** 片方しか認めないと、正しく書いた文書が鳴る。

    `supersedes` は `G006` が循環を見ているが、**ここでは自前で番をする。**
    循環していても検査が止まらないほうがよい。
    """
    direct: dict[str, set[str]] = {}
    for node in graph.nodes.values():
        for target in as_list(node.meta.get("supersedes")):
            direct.setdefault(target, set()).add(node.id)

    index: dict[str, set[str]] = {}
    for start in direct:
        seen: set[str] = set()
        stack = list(direct[start])
        while stack:
            current = stack.pop()
            if current in seen or current == start:
                continue
            seen.add(current)
            stack.extend(direct.get(current, ()))
        index[start] = seen
    return index


def unacknowledged_citations(
    node: Node, graph: Graph, replaced_by: dict[str, set[str]]
) -> list[str]:
    """そのノードが**断りなく**引いている deprecated なノードの id。

    判定は段落ごとに行う。**同じ段落の中で置き換え先も指していれば、
    承知のうえで引いていると見なして黙る。**「以前は X と決めていた
    （[[ADR-0008]]。いまは [[ADR-0014]]）」は正しい書き方だからである。

    文書のどこかで指していれば足りる、にはしない。長い文書では別の話題で
    置き換え先に触れているだけで黙ってしまい、実データで本物を取りこぼした。

    **自分が連鎖上の置き換え先なら、何度でも引いてよい。** 置き換えた側が
    「あちらはこう決めていた」と書くのは仕事のうちで、直接の置き換え先でも、
    2 つ前の決定でも変わらない。
    """
    return _unacknowledged(node.body, node.path.parent, node.id, graph, replaced_by)


def _unacknowledged(
    body: str,
    base: Path,
    self_id: str | None,
    graph: Graph,
    replaced_by: dict[str, set[str]],
) -> list[str]:
    """`unacknowledged_citations` の本体。**ノードでない文章にも当てる。**

    `self_id` はその文章自身のノード id。README のようにノードでないものは
    `None` を渡す。**置き換えた側の免除が効かなくなるだけ**で、他は同じ。
    """
    by_path = {n.path.resolve(): n for n in graph.nodes.values()}
    unacknowledged: set[str] = set()

    for block in paragraphs(body):
        here = _referenced_ids(block, base, by_path)
        for target_id in here:
            target = graph.nodes.get(target_id)
            if target is None or target.status != "deprecated":
                continue
            successors = replaced_by.get(target_id, set())
            if self_id is not None and self_id in successors:
                continue  # 置き換えた側。指さないほうがおかしい
            if successors & here:
                continue  # その場で置き換え先も指している
            unacknowledged.add(target_id)

    return sorted(unacknowledged)


def rule_g020_deprecated_references(graph: Graph) -> list[Issue]:
    """本文が `deprecated` なノードを、現在の根拠として引いていないか。

    **問題は「参照していること」ではなく「現在の根拠として引いていること」。**
    実データでは、置き換え先の ADR がすでに決まっているのに古いほうを指した
    まま、という形がユースケース層と契約層に集中して残っていた。

    **歴史として引くのは正当なので、エラーにはできない。**
    「以前は X と書いていた（[[ADR-0008]]）」は正しい使い方である。
    `G009`〜`G015` と同じ警告にして、承知のうえで放置できる形にする。

    警告に添える直し方も**「置き換え先を指す」だけ**にする。「引き継がれた範囲を
    書く」は、書く場所が**置き換えた側の ADR の「決定」**であって、
    引いている側ではない。

    黙るのは 4 つ。

    - **確定した記録**（`schema.IMMUTABLE_RECORD_TYPES`。既定では `stable` な ADR）。
      **確定した ADR は書き換えない**ので、本文を直させる指摘は成立しない。
      確定前（`draft` / `review`）はまだ決めている途中なので対象に残す
    - 自分が連鎖上の置き換え先である指し先（**置き換えた側は指さないとおかしい**）
    - `index` ノード（一覧は取り下げたものも並べる。それが仕事である）
    - 自分も `deprecated`

    加えて、**同じ段落の中で置き換え先も指していれば黙る。**

    **残るのは実質、現在の設計を述べる層である。** そこは「いまどうなっているか」
    だけを書く場所なので、古い決定を指していたら**生きている決定に差し替える。**
    経緯を書き足すのではなく、取り下げた ADR への参照ごと消えるのが正しい。

    `G009` と重ならない。あちらは `stable` なノードの `depends_on` だけを見る。
    こちらは status を問わず**本文のリンク**を見るので、実データの残りは
    ほとんどこちらでしか出ない。
    """
    replaced_by = superseded_index(graph)
    issues: list[Issue] = []

    for node in graph.sorted_nodes():
        if node.type == "index" or node.status == "deprecated":
            continue
        if schema.is_immutable_record(node.type, node.status):
            continue
        stale = unacknowledged_citations(node, graph, replaced_by)
        if stale:
            issues.append(_g020_issue(stale, replaced_by, node.rel))

    issues.extend(_readme_citations(graph, replaced_by))
    return issues


def _g020_issue(
    stale: list[str], replaced_by: dict[str, set[str]], location: str
) -> Issue:
    named = []
    for target_id in stale:
        successors = sorted(replaced_by.get(target_id, set()))
        if successors:
            named.append(f"{target_id}（置き換え先: {' / '.join(successors)}）")
        else:
            named.append(f"{target_id}（置き換え先なし）")

    return Issue(
        "G020",
        WARN,
        "取り下げた決定を、断りなく引いています: "
        + " / ".join(named)
        + "。生きている決定に差し替えてください"
        "（歴史として引いているならそのままでよい）",
        location,
    )


def _readme_citations(
    graph: Graph, replaced_by: dict[str, set[str]]
) -> list[Issue]:
    """README も決定を引く。**ノードではないので、ここで見ないと誰も見ない。**

    実測で、7 リポジトリのうち 3 つの README が取り下げ済みの ADR を現在の
    根拠として引いていた。1 つは**移った先の事実を古いまま述べていた**
    （「3 つの Bot を同居」。置き換えた決定の題は「台数を問わない」）。
    **README はノードより読まれるのに、検査はノードより薄かった。**

    **見るのは README.md だけ。** `CONTRIBUTING.md` と `CLAUDE.md` は実測で
    0 件で、`CLAUDE.md` は派生が共有しているため、テンプレート側の 1 件が
    全派生で鳴る。

    リンクの基準はリポジトリの根。README はそう書くためである。
    """
    if graph.root is None:
        return []
    readme = graph.root / "README.md"
    if not readme.is_file():
        return []
    try:
        body = readme.read_text(encoding="utf-8")
    except OSError:
        return []          # 読めないことを G020 の仕事にしない

    stale = _unacknowledged(body, graph.root, None, graph, replaced_by)
    return [_g020_issue(stale, replaced_by, "README.md")] if stale else []


# --------------------------------------------------------------------------
# G021: 自動生成ブロックより後ろに本文がある
# --------------------------------------------------------------------------
def content_after_auto_block(text: str) -> tuple[int, str] | None:
    """自動生成ブロックより後ろに残った本文を `(行番号, 最初の行)` で返す。

    **ファイルの生テキストを渡す。** `node.body` は `strip_auto_block` を
    通した後なので、ブロックの前後が繋がってしまい判定にならない。

    目印は `graph:auto:end` **だけ**を見る。目次の `graph:children:end` は
    文書の途中に置かれるのが正しい（一覧の後ろに使い方を書く）。

    ブロックが 2 つある文書は既に壊れているが、**最後の 1 つ**を基準にする。
    間に挟まった本文まで数えると、直す場所が分からない指摘になる。
    """
    index = text.rfind(schema.AUTO_BLOCK_END)
    if index == -1:
        return None

    tail = text[index + len(schema.AUTO_BLOCK_END) :]
    if not tail.strip():
        return None

    before = text[: index + len(schema.AUTO_BLOCK_END)].count("\n")
    for offset, line in enumerate(tail.split("\n")):
        if line.strip():
            return before + offset + 1, line.strip()
    return None


def rule_g021_content_after_auto_block(graph: Graph) -> list[Issue]:
    """`sync` が書くブロックより後ろに本文が残っていないか。

    自動ブロックは「関連ドキュメント（自動生成 / 手で編集しない）」という
    **文書の締め**である。**その下に本文が続くとは読む人は思わない。**

    しかも CLAUDE.md が「この塊を手で編集するな」と書いているので、
    **下の本文を直したい人は「触るな」と書かれた塊を越えて行くことになる。**

    `sync` は自分では直せない。ブロックが既にあれば**その場で入れ替える**だけで、
    後ろに回った本文は動かさない。だから一度こうなると、黙って残り続ける。

    **実際に `META-01` で 85 行（文書の 12%）が落ちていた。**
    共有ファイルなので 7 リポジトリすべてが同じ状態だった。1.14.2 で直した。

    **警告ではなくエラーにした。** `G019` と同じで、承知のうえで放置してよい
    場合が無い。読む人に届いていない本文がそこにある、というだけである。
    """
    issues: list[Issue] = []
    for node in graph.sorted_nodes():
        try:
            text = node.path.read_text(encoding="utf-8")
        except OSError:
            continue  # 読めないものは他のルールが指す

        found = content_after_auto_block(text)
        if found is None:
            continue

        lineno, line = found
        issues.append(
            Issue(
                "G021",
                ERROR,
                f"{lineno} 行目から、自動生成ブロックより後ろに本文が残っています。"
                "ブロックは文書の締めなので、読む人はここまで来ません。"
                f"本文をブロックの前へ移してください: {line[:60]}",
                node.rel,
            )
        )

    return issues


# --------------------------------------------------------------------------
# G022: 同じ用語が複数のドメインノードで定義されている
# --------------------------------------------------------------------------
def _linked_ids(by_path: dict[Path, str], graph: Graph, node: Node, text: str) -> set[str]:
    """セルの中のリンクが指しているノードの id。loader と同じく、ノードの場所から解決する。"""
    ids = {raw.strip() for raw in WIKILINK_RE.findall(text) if raw.strip() in graph.nodes}
    for href in MDLINK_RE.findall(text):
        target = by_path.get((node.path.parent / href.split("#", 1)[0]).resolve())
        if target is not None:
            ids.add(target)
    return ids


def rule_g022_duplicate_terms(graph: Graph) -> list[Issue]:
    """同じ用語が複数のドメインノードの用語表にあり、定義元が決まっていないものを警告する。

    **同じ意味なら同じ用語で、定義は 1 か所に置く。** 別の意味なら語を分ける。
    `G013` は依存の向きにしか届かないので、**兄弟ノードが同じ語を別の意味で
    定義していても、これまで誰も気づけなかった**（META-01 の G013 の節）。

    **意図した再掲は黙る。** 他のノードの語を自分の表にも載せるときは、
    「意味」の欄から定義元へリンクする。同じ語を載せている行のうち、
    **他の定義元へリンクしていない行が 1 つだけなら、それが定義元である。**

    実測（1.20.0）: tournament-bot の重複 5 件のうち 3 件がリンクつきの再掲で、
    鳴るのは 2 件（別の意味で 2 回定義されていた）。ほかの派生 4 つは 0 件。

    **リンクは「承知している」印にすぎない。** 同じ意味かどうかまでは見ない。
    """
    by_path = {n.path.resolve(): n.id for n in graph.nodes.values()}
    defined: dict[str, list[tuple[Node, str]]] = {}
    for node in graph.sorted_nodes():
        if node.type != "domain":
            continue
        for row in term_rows(node.body):
            term = _EMPHASIS_RE.sub("", row.get(schema.TERM_COLUMN, "")).strip()
            if term:
                defined.setdefault(term, []).append(
                    (node, row.get(schema.TERM_MEANING_COLUMN, ""))
                )

    issues: list[Issue] = []
    for term, owners in sorted(defined.items()):
        ids = {node.id for node, _ in owners}
        if len(ids) < 2:
            continue
        unlinked = sorted(
            {
                node.id
                for node, meaning in owners
                if not (_linked_ids(by_path, graph, node, meaning) & (ids - {node.id}))
            }
        )
        if len(unlinked) < 2:
            continue
        issues.append(
            Issue(
                "G022",
                WARN,
                f"{term!r} が {' / '.join(sorted(ids))} の用語表で定義されていて、"
                f"{' / '.join(unlinked)} のどれも他の定義元へリンクしていません。"
                "同じ意味なら定義を 1 か所に置き、ほかの行は「意味」から定義元へリンクしてください。"
                "別の意味なら語を分けてください",
                graph.nodes[unlinked[0]].rel,
            )
        )
    return issues
