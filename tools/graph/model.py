"""グラフのデータ構造。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from . import schema

ERROR = "error"
WARN = "warn"


@dataclass(frozen=True)
class Edge:
    """ノードの間の、向きを持つリンク。"""

    src: str  # 出発するノードのid
    dst: str  # 到達するノードのid（解決できなかった場合は、生の参照の文字列）
    kind: str  # schema.EDGE_KINDSのキー、またはBODY_EDGE_KIND
    origin: str  # "frontmatter" | "body"
    resolved: bool = True


@dataclass
class Node:
    """1つのMarkdownの文書が、1つのノードになる。"""

    id: str
    type: str
    title: str
    status: str
    tags: list[str]
    path: Path  # 絶対パス
    rel: str  # リポジトリの根からの相対パス（POSIXの表記）
    meta: dict  # フロントマター全体
    body: str  # 自動生成ブロックを取り除いた本文
    edges: list[Edge] = field(default_factory=list)

    def out_edges(self, kind: str | None = None) -> list[Edge]:
        if kind is None:
            return list(self.edges)
        return [e for e in self.edges if e.kind == kind]


@dataclass
class Issue:
    """検証で見つかった問題。"""

    code: str  # G001など
    severity: str  # ERROR | WARN
    message: str
    location: str  # ファイルのパス、または"graph"

    def format(self) -> str:
        mark = "ERROR" if self.severity == ERROR else "WARN "
        return f"{mark} {self.code} {self.location}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    load_issues: list[Issue] = field(default_factory=list)
    # リポジトリの根。implemented_byの指し先を確かめるのに要る（G016）。
    # 部分グラフでも引き継ぐ。読めなかった場合はNone。
    root: Path | None = None

    def add(self, node: Node) -> None:
        self.nodes[node.id] = node

    def edges(self) -> list[Edge]:
        return [e for node in self.nodes.values() for e in node.edges]

    def incoming(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges() if e.dst == node_id and e.resolved]

    def by_type(self, node_type: str) -> list[Node]:
        return sorted(
            (n for n in self.nodes.values() if n.type == node_type),
            key=lambda n: n.id,
        )

    def sorted_nodes(self) -> list[Node]:
        return sorted(self.nodes.values(), key=lambda n: (n.type, n.id))

    def hops(
        self,
        focus_ids: list[str],
        depth: int = 1,
        *,
        include_mentions: bool = False,
    ) -> dict[str, int]:
        """指定したノードから`depth`ホップ以内のノードと、そこまでのホップ数を返す。

        エッジの向きは無視する。前提（依存先）と影響範囲（依存元）の両方を
        見たいので、片方向に絞ると、近傍として役に立たない。
        """
        adjacency: dict[str, set[str]] = {}
        for node in self.nodes.values():
            for edge in node.edges:
                if not edge.resolved:
                    continue
                if not include_mentions and edge.kind == schema.BODY_EDGE_KIND:
                    continue
                adjacency.setdefault(edge.src, set()).add(edge.dst)
                adjacency.setdefault(edge.dst, set()).add(edge.src)

        distance = {node_id: 0 for node_id in focus_ids if node_id in self.nodes}
        frontier = set(distance)

        for hop in range(1, max(depth, 0) + 1):
            nxt: set[str] = set()
            for node_id in frontier:
                nxt |= adjacency.get(node_id, set())
            nxt -= distance.keys()
            if not nxt:
                break
            for node_id in nxt:
                distance[node_id] = hop
            frontier = nxt
        return distance

    def subgraph(self, selected: set[str], *, include_mentions: bool = False) -> "Graph":
        """`selected`のノードと、その間のエッジだけを含む部分グラフを返す。"""
        sub = Graph(root=self.root)
        for node_id in selected:
            node = self.nodes[node_id]
            kept = [
                edge
                for edge in node.edges
                if edge.resolved
                and edge.dst in selected
                and (include_mentions or edge.kind != schema.BODY_EDGE_KIND)
            ]
            sub.add(replace(node, edges=kept))
        return sub

    def without_kinds(self, kinds: set[str]) -> "Graph":
        """`kinds`の種類のエッジを除いたグラフを返す。ノードはすべて残す。"""
        out = Graph(root=self.root)
        for node in self.nodes.values():
            out.add(replace(node, edges=[e for e in node.edges if e.kind not in kinds]))
        return out

    def without_implied(
        self, kind: str, among: set[str] | None = None
    ) -> tuple["Graph", int]:
        """`kind`の線のうち、ほかの`kind`の線を辿れば分かるものを除いたグラフと、除いた本数を返す。

        A→B→CとA→Cがあるとき、A→Cを除く。辿る経路も`kind`の線だけにする。
        `among`を渡すと、その中のノードどうしの線だけを見て、経路もその中だけで辿る。
        図に描かないノードを通る経路で線を消すと、図だけでは辿れなくなるからである。
        線を1本除くごとに、残った線で辿れるかを確かめるので、循環があっても、
        どのノードからどのノードへ辿れるかは変わらない。
        """
        inside = set(self.nodes) if among is None else among & set(self.nodes)
        adjacency: dict[str, set[str]] = {}
        for node in self.nodes.values():
            for edge in node.edges:
                if (
                    edge.kind == kind
                    and edge.resolved
                    and edge.src in inside
                    and edge.dst in inside
                    and edge.src != edge.dst
                ):
                    adjacency.setdefault(edge.src, set()).add(edge.dst)

        def reachable(src: str, dst: str) -> bool:
            seen = {src}
            stack = [src]
            while stack:
                for nxt in adjacency.get(stack.pop(), ()):
                    if nxt == dst:
                        return True
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            return False

        removed: set[tuple[str, str]] = set()
        # 名前の順に見て、結果を安定させる
        for src in sorted(adjacency):
            for dst in sorted(adjacency[src]):
                adjacency[src].discard(dst)
                if reachable(src, dst):
                    removed.add((src, dst))
                else:
                    adjacency[src].add(dst)

        out = Graph(root=self.root)
        for node in self.nodes.values():
            kept = [
                e for e in node.edges if not (e.kind == kind and (e.src, e.dst) in removed)
            ]
            out.add(replace(node, edges=kept))
        return out, len(removed)
