"""グラフの検証ルール。

ルールは 1 つの関数 = 1 つのコード。エラーメッセージに必ずコードを載せるので、
「G007 が出た」で規約のどの条項かをすぐ引ける。
"""

from __future__ import annotations

import re
from datetime import date

from . import schema
from .loader import strip_non_prose
from .model import ERROR, WARN, Graph, Issue, Node

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
    "G013": "依存先が禁じた言い換えを使っている",
    "G014": "テンプレートの必須の節が無い",
    "G015": "依存先が変わったのに追従していない",
}


def check_all(
    graph: Graph,
    *,
    history: dict[str, date] | None = None,
    today: date | None = None,
    changed: set[str] | None = None,
) -> list[Issue]:
    """`history` は `{相対パス: 最終コミット日}`。無ければ G011 を飛ばす。

    `changed` は「この変更で動いたノードの id」。無ければ G015 を飛ばす。
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
    ):
        issues.extend(rule(graph))

    if history:
        issues.extend(rule_g011_stale(graph, history, today or date.today()))

    if changed:
        issues.extend(rule_g015_unfollowed_changes(graph, changed))

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
# G013: 用語の一貫性
# --------------------------------------------------------------------------
# 「## 用語」の節。次の同レベル見出しか文末まで。
_TERM_SECTION_RE = re.compile(
    rf"^##\s+{re.escape(schema.TERM_SECTION_HEADING)}\s*$(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
# セル末尾の丸括弧。禁止の理由か、使ってよい条件が入っている
_TRAILING_NOTE_RE = re.compile(r"[（(]([^）)]*)[）)]\s*$")
_INNER_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")
_SEPARATOR_RE = re.compile(r"[、,]")
_SNIPPET_PAD = 20


def _table_rows(section: str) -> list[list[str]]:
    """Markdown の表を行ごとのセル一覧にする。区切り行（`| --- |`）は落とす。"""
    rows: list[list[str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        rows.append(cells)
    return rows


def forbidden_terms(body: str) -> dict[str, tuple[str, str]]:
    """「用語」表から `{使ってはいけない語: (正しい用語, 注記)}` を作る。

    列は位置ではなく見出しで探す。列が増えても壊れないようにするため。
    """
    section = _TERM_SECTION_RE.search(body)
    if section is None:
        return {}

    rows = _table_rows(section.group(1))
    if not rows:
        return {}

    header = rows[0]
    try:
        term_at = header.index(schema.TERM_COLUMN)
        forbidden_at = header.index(schema.TERM_FORBIDDEN_COLUMN)
    except ValueError:
        return {}  # 見出しが違う表。用語表ではないので触らない

    found: dict[str, tuple[str, str]] = {}
    for cells in rows[1:]:
        if max(term_at, forbidden_at) >= len(cells):
            continue
        term = cells[term_at]
        raw = cells[forbidden_at]
        if not term or not raw:
            continue  # 雛形の空行

        # 末尾の括弧はセル全体にかかる注記として扱う。
        # 「承認、昇格（第三者が判断する語感になる）」の理由は両方にかかっている
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
    """依存先が「使ってはいけない言い換え」に挙げた語の使用を警告する。

    規約の「`depends_on` に挙げたノードの用語だけを使って書く」を機械で見る。
    これまで唯一、人の注意力だけに任せていた条項だった。

    **語の意味までは分からない。** 別の概念について同じ語を使っている場合や、
    「承認は挟まない」のように否定するために持ち出した場合も引っかかる。
    だから警告に留め、判断の材料（注記と前後の文）を出すところまでを仕事とする。
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
        # 用語表そのものは対象外。禁止語を「挙げている」ことは「使っている」ことではない
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
                        f"{word!r} は {owner_id} が使ってはいけない言い換えに挙げています"
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
