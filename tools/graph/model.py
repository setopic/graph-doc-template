"""グラフのデータ構造。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ERROR = "error"
WARN = "warn"


@dataclass(frozen=True)
class Edge:
    """ノード間の有向リンク。"""

    src: str  # 出発ノードの id
    dst: str  # 到達ノードの id（未解決の場合は生の参照文字列）
    kind: str  # schema.EDGE_KINDS のキー、または BODY_EDGE_KIND
    origin: str  # "frontmatter" | "body"
    resolved: bool = True


@dataclass
class Node:
    """1 つの Markdown 文書 = 1 ノード。"""

    id: str
    type: str
    title: str
    status: str
    tags: list[str]
    path: Path  # 絶対パス
    rel: str  # リポジトリルートからの相対パス（POSIX 表記）
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

    code: str  # G001 など
    severity: str  # ERROR | WARN
    message: str
    location: str  # ファイルパス、または "graph"

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
