"""グラフの検証ルール。

ルールは 1 つの関数 = 1 つのコード。エラーメッセージに必ずコードを載せるので、
「G007 が出た」で規約のどの条項かをすぐ引ける。
"""

from __future__ import annotations

from . import schema
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
}


def check_all(graph: Graph) -> list[Issue]:
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
    ):
        issues.extend(rule(graph))
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
