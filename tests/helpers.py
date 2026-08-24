"""テスト用の小さな組み立て道具。"""

from __future__ import annotations

from tools.graph.model import Graph, Node


def make_graph(nodes: list[Node]) -> Graph:
    graph = Graph()
    for node in nodes:
        graph.add(node)
    return graph
