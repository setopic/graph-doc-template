"""設計文書のグラフを検証し、可視化するツール。

外部依存は無い。リポジトリの根で`python -m tools.graph check`を実行する。
"""

from .loader import load
from .model import Edge, Graph, Issue, Node
from .rules import check_all

__all__ = ["load", "check_all", "Graph", "Node", "Edge", "Issue"]
