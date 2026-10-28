"""グラフを、層を列に並べたSVGの図として書き出す（render --format svg）。

このモジュールは、配置・箱・線・クラス名だけを決める。色・フォント・線の太さ・動きの
見た目は、テーマのCSS（既定は`themes/default.css`）で決め、SVGの中の`<style>`に埋め込む。
GitHubはREADMEのSVGをimgで出すので、外部のCSSやフォントは読めないからである。

配置は次のとおりである。

- 層のルールの対象の種別（`exempt_layer`でないもの）は、1種別を1列にし、`layer`の大きい順に
  左から並べる。既定の種別では、40 契約 → 30 ユースケース → 20 ドメイン → 10 アーキテクチャ
- 層のルールの対象外の種別は、列の上下の帯に置く。いちばん上の列より`layer`が大きいもの
  （既定では決定記録）は上、それ以外（メタ / 規約、目次）は下に置く
- 列と帯の中の並びは、重心法で決める。つながっている相手の位置の平均で並べ替えることを
  数回くり返し、線の交差を減らす

出力は決定的にする。同じグラフ・テーマ・設定からは、同じバイト列を返す。
`make readme-check`が、書き出したファイルとバイト列で比べるからである。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import schema
from .model import Graph
from .render import _UNDIRECTED, _diagram_edges, aggregate_totals, types_parts

DEFAULT_THEME = Path(__file__).resolve().parent / "themes" / "default.css"

# 文字の幅の見積もりに使う大きさ。既定のテーマの文字の大きさに合わせてある。
# テーマで文字を大きくすると、箱からはみ出すことがある
ID_FONT = 12.0
TITLE_FONT = 12.5
LABEL_FONT = 13.0
EDGE_LABEL_FONT = 10.5  # 線の名前
LANE_LABEL_FONT = 13.0  # 列の見出し

# 既定のテーマが名前を書かない線の種類（まとめた線でないとき）。帯の箱の間に、名前の幅を取らない
QUIET_LABELS = {"depends_on", "related"}

MARGIN = 20
PAD_X = 12
BOX_MIN_W = 120
BOX_MAX_W = 240
LINE_H = 17
BOX_GAP = 22  # 列の中の箱と箱、帯の中の箱と箱の間
LABEL_PAD = 10  # 帯の中で隣り合う箱を結ぶ線の、名前の左右に空ける幅
LANE_PAD = 14
LANE_HEAD = 34  # 列の見出しの高さ
COL_GAP = 64  # 列と列の間。線と、その名前を通す
BAND_HEAD = 24  # 帯の見出しの高さ
BAND_GAP = 36  # 帯と列の間
ARC_SPACE = 44  # 帯の中の弧の線に取っておく高さ
PARALLEL_STEP = 16  # 同じ2つの箱を結ぶ線どうしの間隔
DUMMY_H = 2  # 2列以上離れた列を結ぶ線が、間の列で通る場所の高さ
DUMMY_GAP = 4  # 間の列で、通り道どうしの間。続けて並ぶ通り道は、束にして詰める
CORRIDOR_STEP = 4  # 廊下（帯と列の間）で、横に通る線どうしの間隔
SIDE_CHANNEL = 28  # 列の左右の端の、縦に線を通す場所の幅
SWEEPS = 8  # 重心法で並べ替える回数
INSERT_SEARCH_MAX = 40  # 帯の中の並びを、箱を1つずつ移して詰める箱の数の上限

# 動き。1周（period）のうち、点が線の上を進む割合と、箱が光る時間の位置
TRAVEL = 0.7


def load_theme(root: Path | None) -> str:
    """テーマのCSSを読む。`graph.toml`の`[render]`の`theme`が無ければ、既定のテーマを使う。"""
    if schema.RENDER_THEME and root is not None:
        path = root / schema.RENDER_THEME
    else:
        path = DEFAULT_THEME
    # read_textは改行をLFにそろえる。Windowsで読んでも、同じバイト列になる
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 図の中身
# --------------------------------------------------------------------------
@dataclass
class Box:
    key: str
    type: str
    head: str  # 1行目（idか、種別の名前）
    body: str  # 2行目以降（題か、件数）
    classes: list[str]
    lines: list[str] = field(default_factory=list)
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0


@dataclass
class Line:
    src: str
    dst: str
    kind: str
    count: int | None = None  # まとめた線なら本数


def _node_box(node, focus: set[str]) -> Box:
    classes = ["node", f"t-{node.type}", f"s-{node.status}"]
    if node.id in focus:
        classes.append("focus")
    return Box(node.id, node.type, node.id, node.title, classes)


def _group_box(key: str, type_name: str, count: int) -> Box:
    spec = schema.NODE_TYPES[type_name]
    return Box(key, type_name, spec["label"], f"{count} 件", ["node", "group", f"t-{type_name}"])


def _known(graph: Graph):
    """種別の分かるノード。種別の誤りはG003が指摘するので、図では何も言わずに飛ばす。"""
    return [n for n in graph.sorted_nodes() if n.type in schema.NODE_TYPES]


def _parts_plain(graph: Graph, include_mentions: bool, focus: set[str]):
    edges = list(_diagram_edges(graph, include_mentions))
    # to_mermaidと同じく、線を1本も持たないノードは描かない。focusのノードは残す
    drawn = {e.src for e in edges} | {e.dst for e in edges} | focus
    boxes = [_node_box(n, focus) for n in _known(graph) if n.id in drawn]
    keys = {b.key for b in boxes}
    lines = [Line(e.src, e.dst, e.kind) for e in edges if e.src in keys and e.dst in keys]
    return boxes, lines


def _parts_types(graph: Graph, types: set[str], include_mentions: bool):
    inner, totals, drawn = types_parts(graph, types, include_mentions)
    boxes = [_node_box(n, set()) for n in _known(graph) if n.id in drawn]
    for type_name, spec in schema.NODE_TYPES.items():
        if type_name in types:
            continue
        if any(spec["prefix"] in (src, dst) for src, _, dst in totals):
            boxes.append(_group_box(spec["prefix"], type_name, len(graph.by_type(type_name))))
    lines = [Line(e.src, e.dst, e.kind) for e in inner]
    lines += [Line(src, dst, kind, count) for (src, kind, dst), count in sorted(totals.items())]
    return boxes, lines


def _parts_aggregate(graph: Graph, include_mentions: bool):
    boxes = []
    for type_name, spec in schema.NODE_TYPES.items():
        nodes = graph.by_type(type_name)
        if nodes:
            boxes.append(_group_box(spec["prefix"], type_name, len(nodes)))
    totals = aggregate_totals(graph, include_mentions)
    lines = []
    for (src_type, kind, dst_type), count in sorted(
        totals.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(
            Line(
                schema.NODE_TYPES[src_type]["prefix"],
                schema.NODE_TYPES[dst_type]["prefix"],
                kind,
                count,
            )
        )
    return boxes, lines


# --------------------------------------------------------------------------
# 文字の幅と折り返し
# --------------------------------------------------------------------------
def _char_w(ch: str, size: float) -> float:
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return size
    return size * 0.6


def text_width(text: str, size: float) -> float:
    return sum(_char_w(ch, size) for ch in text)


def _wrap(text: str, size: float, limit: float, max_lines: int = 2) -> list[str]:
    """文字の幅で折り返す。収まらない分は、最後の行の末尾を「…」にする。"""
    out: list[str] = []
    line = ""
    for ch in text:
        if text_width(line + ch, size) > limit and line:
            # 英単語の途中で切らないよう、行の中の最後の空白で切れるなら、そこで切る
            cut = line.rfind(" ")
            if cut > 0 and not line.endswith(" "):
                out.append(line[:cut])
                line = line[cut + 1 :]
            else:
                out.append(line.rstrip())
                line = ""
            if len(out) == max_lines:
                break
        line += ch
    else:
        out.append(line)
        return [l for l in out if l] or [""]
    # 収まらなかった
    last = out[-1]
    while last and text_width(last + "…", size) > limit:
        last = last[:-1]
    out[-1] = last.rstrip() + "…"
    return out


def _label_text(line: Line) -> str:
    return line.kind if line.count is None else f"{line.kind} {line.count}"


def _measure(box: Box) -> None:
    limit = BOX_MAX_W - 2 * PAD_X
    box.lines = _wrap(box.body, TITLE_FONT, limit)
    widest = max(
        [text_width(box.head, ID_FONT) * 1.05] + [text_width(l, TITLE_FONT) for l in box.lines]
    )
    box.w = max(BOX_MIN_W, min(BOX_MAX_W, round(widest + 2 * PAD_X)))
    box.h = 41 + LINE_H * len(box.lines)


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
def _containers(boxes: list[Box]):
    """列（左から）と、上の帯・下の帯に入れる種別を決める。"""
    order = list(schema.NODE_TYPES)
    present = sorted({b.type for b in boxes}, key=order.index)
    columns = [t for t in present if not schema.NODE_TYPES[t]["exempt_layer"]]
    columns.sort(key=lambda t: (-schema.NODE_TYPES[t]["layer"], order.index(t)))
    top_layer = max((schema.NODE_TYPES[t]["layer"] for t in columns), default=0)
    bands = [t for t in present if schema.NODE_TYPES[t]["exempt_layer"]]
    top = [t for t in bands if schema.NODE_TYPES[t]["layer"] > top_layer]
    bottom = [t for t in bands if t not in top]
    return columns, top, bottom


def _band_order(bands: list[str], boxes: list[Box], lines: list[Line], near_last: bool) -> list[str]:
    """帯の並び。線の多い種別ほど列の近くに置き、列との間の帯を線が横切る数を減らす。"""
    kind_of = {b.key: b.type for b in boxes}
    touches = {t: 0 for t in bands}
    for line in lines:
        for end in (line.src, line.dst):
            if kind_of.get(end) in touches:
                touches[kind_of[end]] += 1
    order = list(schema.NODE_TYPES)
    ranked = sorted(bands, key=lambda t: (-touches[t], order.index(t)))
    # 上の帯は、最後に置いたものが列にいちばん近い
    return list(reversed(ranked)) if near_last else ranked


def _order(groups: dict[str, list[Box]], columns: list[str], links: list[tuple[str, str]]) -> None:
    """重心法で、列と帯の中の並びを決める。groupsの各リストを並べ替える。

    列の箱は、ほかの列でつながっている相手の縦の位置の平均で並べる。帯の箱は、
    つながっている相手の横の位置の平均で並べる。左右の向きを変えながらくり返す。
    """
    where: dict[str, str] = {b.key: t for t, bs in groups.items() for b in bs}
    neighbors: dict[str, list[str]] = {k: [] for k in where}
    for a, b in links:
        if a in where and b in where and a != b:
            neighbors[a].append(b)
            neighbors[b].append(a)
    col_index = {t: i for i, t in enumerate(columns)}

    def pos() -> dict[str, tuple[float, float]]:
        # (横, 縦)の位置を0〜1で表す。列の箱は列の番号で横を、並びで縦を決める。
        # 帯の箱は並びで横を決める
        out = {}
        for t, bs in groups.items():
            n = max(len(bs) - 1, 1)
            for i, b in enumerate(bs):
                if t in col_index:
                    out[b.key] = ((col_index[t] + 0.5) / max(len(columns), 1), i / n)
                else:
                    out[b.key] = (i / n, 0.0)
        return out

    def resort(t: str) -> None:
        p = pos()
        bs = groups[t]
        n = max(len(bs) - 1, 1)
        keyed = []
        for i, b in enumerate(bs):
            if t in col_index:
                others = [p[o][1] for o in neighbors[b.key] if where[o] in col_index and where[o] != t]
            else:
                others = [p[o][0] for o in neighbors[b.key]]
            center = sum(others) / len(others) if others else i / n
            keyed.append((round(center, 6), i, b))
        keyed.sort(key=lambda item: (item[0], item[1]))
        groups[t] = [b for _, _, b in keyed]

    bands = [t for t in groups if t not in col_index]
    for sweep in range(SWEEPS):
        for t in columns if sweep % 2 == 0 else list(reversed(columns)):
            resort(t)
        for t in bands:
            resort(t)

    # 帯の中では、重心法だけだと、つながりの多い箱が端に寄る（相手の箱もその箱に寄るため）。
    # 隣り合う2つを入れ替えて、帯の中の線の長さと、ほかの場所の相手からのずれの和が
    # 減るなら入れ替える、をくり返す
    p = pos()
    for t in bands:
        bs = groups[t]
        n = len(bs)
        if n < 3:
            continue
        inside = {b.key for b in bs}
        target = {}
        for b in bs:
            outer = [p[o][0] for o in neighbors[b.key] if o not in inside]
            target[b.key] = sum(outer) / len(outer) * (n - 1) if outer else None

        def cost(seq: list[Box]) -> float:
            at = {b.key: i for i, b in enumerate(seq)}
            total = 0.0
            for b in seq:
                for o in neighbors[b.key]:
                    if o in inside and b.key < o:
                        total += abs(at[b.key] - at[o])
                if target[b.key] is not None:
                    total += 0.5 * abs(at[b.key] - target[b.key])
            return total

        best = cost(bs)
        for _ in range(4 * n):
            improved = False
            if n <= INSERT_SEARCH_MAX:
                # 1つの箱を、ほかのどの位置へ移すと減るかを全部試す
                trials = (
                    rest[:j] + [bs[i]] + rest[j:]
                    for i in range(n)
                    for rest in [bs[:i] + bs[i + 1 :]]
                    for j in range(n)
                    if j != i
                )
            else:
                # 箱が多いと時間がかかるので、隣り合う2つの入れ替えだけを試す
                trials = (bs[:i] + [bs[i + 1], bs[i]] + bs[i + 2 :] for i in range(n - 1))
            for trial in trials:
                c = cost(trial)
                if c < best - 1e-9:
                    bs, best, improved = trial, c, True
                    break
            if not improved:
                break
        groups[t] = bs


@dataclass
class Layout:
    width: int
    height: int
    boxes: dict[str, Box]
    lanes: list[tuple[str, float, float, float, float]]  # 種別, x, y, 幅, 高さ
    bands: list[tuple[str, float, float]]  # 種別, 見出しのx, 見出しのy
    rows: dict[str, tuple[str, int, int]]  # 帯の箱 → (帯の種別, 行, 行の中の位置)
    columns: dict[str, int]  # 列の箱 → 列の番号
    band_side: dict[str, int]  # 帯の種別 → 列から見た向き（上は-1、下は1）
    dummies: dict[int, list[Box]]  # 線の番号 → 間の列に置いた通り道
    channels: list[float]  # 列と列の間（と両端）の、縦に線を通す位置のx
    corridor: dict[int, float]  # 上（-1）と下（1）の、横に線を通す位置のy
    corridor_half: dict[int, float]  # 上と下の廊下の、高さの半分


def _layout(boxes: list[Box], lines: list[Line]) -> Layout:
    for box in boxes:
        _measure(box)
    columns, top, bottom = _containers(boxes)
    top = _band_order(top, boxes, lines, near_last=True)
    bottom = _band_order(bottom, boxes, lines, near_last=False)
    groups: dict[str, list[Box]] = {t: [] for t in columns + top + bottom}
    for box in boxes:
        groups[box.type].append(box)
    col_index = {t: i for i, t in enumerate(columns)}
    col_of_box = {b.key: col_index[b.type] for b in boxes if b.type in col_index}

    # 2列以上離れた列を結ぶ線には、間の列に通り道（描かない小さな箱）を置く。
    # 通り道も並べ替えに加えるので、線が間の列の箱の上を通らない
    dummies: dict[int, list[Box]] = {}
    links: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        ca, cb = col_of_box.get(line.src), col_of_box.get(line.dst)
        if ca is None or cb is None or abs(ca - cb) < 2:
            links.append((line.src, line.dst))
            continue
        step = 1 if cb > ca else -1
        chain = [line.src]
        dummies[i] = []
        for c in range(ca + step, cb, step):
            d = Box(f"~{i}~{c}", columns[c], "", "", [], w=0, h=DUMMY_H)
            groups[columns[c]].append(d)
            dummies[i].append(d)
            chain.append(d.key)
        chain.append(line.dst)
        links += list(zip(chain, chain[1:]))
    _order(groups, columns, links)

    # 列の幅は、その列でいちばん幅の広い箱に合わせる
    col_w = {t: max([b.w for b in groups[t] if b.head] or [BOX_MIN_W]) for t in columns}
    lanes_w = sum(col_w[t] + 2 * LANE_PAD for t in columns) + COL_GAP * max(len(columns) - 1, 0)
    # 列の左右の端にも、縦に線を通す場所を取る
    side = SIDE_CHANNEL if columns else 0
    content_w = max(lanes_w + 2 * side, 640)

    # 帯の中の箱を、幅に収まるように行へ分ける。行の中で隣り合う箱を結ぶ線は、箱の間を
    # まっすぐ通り、名前もその間に書く。名前が箱に隠れないよう、間を名前の幅だけ空ける
    pair_gap = _pair_gaps(lines)
    lead: dict[str, float] = {}  # 帯の箱 → 行の中で、左の箱との間
    rows: dict[str, tuple[str, int, int]] = {}
    band_rows: dict[str, list[list[Box]]] = {}
    for t in top + bottom:
        band_rows[t] = [[]]
        used = 0.0
        for box in groups[t]:
            row = band_rows[t][-1]
            lead[box.key] = pair_gap.get(frozenset((row[-1].key, box.key)), BOX_GAP) if row else 0.0
            need = box.w + lead[box.key]
            if band_rows[t][-1] and used + need > content_w:
                band_rows[t].append([])
                used = 0.0
                lead[box.key] = 0.0
                need = box.w
            band_rows[t][-1].append(box)
            used += need
        for r, row in enumerate(band_rows[t]):
            for i, box in enumerate(row):
                rows[box.key] = (t, r, i)

    # 帯の中の、同じ行で隣り合わない箱を結ぶ線は、弧にする。弧の分の高さを取っておく
    arcs: set[str] = set()
    for line in lines:
        a, b = rows.get(line.src), rows.get(line.dst)
        if a and b and a[0] == b[0] and a[1] == b[1] and abs(a[2] - b[2]) > 1:
            arcs.add(a[0])

    band_side_of = {t: -1 for t in top} | {t: 1 for t in bottom}
    y = float(MARGIN)
    bands: list[tuple[str, float, float]] = []
    band_side: dict[str, int] = {}

    def place_band(t: str, y: float, side_: int) -> float:
        band_side[t] = side_
        if side_ < 0 and t in arcs:
            y += ARC_SPACE
        bands.append((t, MARGIN, y + 14))
        y += BAND_HEAD
        for r, row in enumerate(band_rows[t]):
            x = float(MARGIN)
            for box in row:
                x += lead[box.key]
                box.x, box.y = x, y
                x += box.w
            y += max(b.h for b in row) + (BOX_GAP if r < len(band_rows[t]) - 1 else 0)
        if side_ > 0 and t in arcs:
            y += ARC_SPACE
        return y

    # 帯と列の間の廊下は、横に通る線の数に合わせて広げる
    top_gap, bottom_gap = (_corridor_gap(lines, rows, set(col_of_box), band_side_of, s) for s in (-1, 1))
    for i, t in enumerate(top):
        y = place_band(t, y, -1) + (top_gap if i == len(top) - 1 else BAND_GAP)

    lanes: list[tuple[str, float, float, float, float]] = []
    channels: list[float] = []
    corridor: dict[int, float] = {}
    if columns:
        corridor[-1] = y - top_gap / 2
        inner_h = max(_stack_h(groups[t]) for t in columns)
        lane_h = LANE_HEAD + inner_h + LANE_PAD
        x = float(MARGIN + side)
        channels.append(MARGIN + side / 2)
        for i, t in enumerate(columns):
            lane_w = col_w[t] + 2 * LANE_PAD
            lanes.append((t, x, y, lane_w, lane_h))
            by = y + LANE_HEAD
            prev = None
            for box in groups[t]:
                if prev is not None:
                    by += _gap(prev, box)
                box.x, box.y, box.w = x + LANE_PAD, by, col_w[t]
                by += box.h
                prev = box
            x += lane_w + COL_GAP
            channels.append(x - COL_GAP / 2 if i < len(columns) - 1 else x - COL_GAP + side / 2)
        y += lane_h
        corridor[1] = y + bottom_gap / 2

    for i, t in enumerate(bottom):
        y = place_band(t, y + (bottom_gap if i == 0 else BAND_GAP), 1)

    width = int(MARGIN * 2 + content_w)
    # まとめた図の、同じ種別どうしの線（自分への輪）の分だけ、右に余白を取る
    if any(line.src == line.dst for line in lines):
        width += COL_GAP
    height = int(y + MARGIN)
    return Layout(
        width,
        height,
        {b.key: b for b in boxes},
        lanes,
        bands,
        rows,
        col_of_box,
        band_side,
        dummies,
        channels,
        corridor,
        {-1: top_gap / 2, 1: bottom_gap / 2},
    )


def _pair_gaps(lines: list[Line]) -> dict[frozenset[str], float]:
    """2つの箱を結ぶ線の名前が、その2つの箱の間に収まる幅。BOX_GAPより広くなる組だけを返す。"""
    out: dict[frozenset[str], float] = {}
    for line in lines:
        if line.src == line.dst or (line.count is None and line.kind in QUIET_LABELS):
            continue
        need = text_width(_label_text(line), EDGE_LABEL_FONT) + 2 * LABEL_PAD
        key = frozenset((line.src, line.dst))
        if need > max(out.get(key, 0), BOX_GAP):
            out[key] = round(need, 1)
    return out


def _gap(a: Box, b: Box) -> float:
    """列の中で、上の箱aと下の箱bの間。通り道どうしは詰め、箱と通り道の間は半分にする。"""
    if not a.head and not b.head:
        return DUMMY_GAP
    if not a.head or not b.head:
        return BOX_GAP / 2
    return BOX_GAP


def _stack_h(column: list[Box]) -> float:
    """列の箱と通り道を、上から順に積んだ高さ。"""
    return sum(b.h for b in column) + sum(_gap(a, b) for a, b in zip(column, column[1:]))


def _corridor_gap(lines: list[Line], rows: dict, in_columns: set[str], band_side_of: dict, side: int) -> float:
    """帯と列の間の高さ。廊下を横に通る線が多ければ、CORRIDOR_STEPずつ並ぶだけの高さを取る。"""
    n = 0
    for line in lines:
        ends = [band_side_of[rows[e][0]] for e in (line.src, line.dst) if e in rows]
        if not ends or line.src == line.dst:
            continue
        if len(ends) == 1 and (line.src in in_columns or line.dst in in_columns) and ends[0] == side:
            n += 1
        elif len(ends) == 2 and ends[0] != ends[1] and in_columns:
            n += 1
    return max(BAND_GAP, CORRIDOR_STEP * n + 16)


# --------------------------------------------------------------------------
# 線の道筋
# --------------------------------------------------------------------------
def _n(v: float) -> str:
    """座標を書き出す。小数1桁に丸め、末尾の.0は書かない。"""
    r = round(v, 1)
    if r == int(r):
        return str(int(r))
    return f"{r:.1f}"


def _center(b: Box) -> tuple[float, float]:
    return b.x + b.w / 2, b.y + b.h / 2


def _clip(b: Box, toward: tuple[float, float], gap: float = 3) -> tuple[float, float]:
    """箱の中心からtowardへ向かう線が、箱の縁（からgapだけ外）と交わる点。"""
    cx, cy = _center(b)
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min(
        (b.w / 2 + gap) / abs(dx) if dx else float("inf"),
        (b.h / 2 + gap) / abs(dy) if dy else float("inf"),
    )
    return cx + dx * t, cy + dy * t


Point = tuple[float, float]


def _rounded(points: list[Point], radius: float = 10) -> str:
    """折れ線を、角を丸めたpathにする。同じ点や一直線に並ぶ点は省く。"""
    pts: list[Point] = []
    for p in points:
        if pts and abs(pts[-1][0] - p[0]) < 0.05 and abs(pts[-1][1] - p[1]) < 0.05:
            continue
        pts.append(p)
    d = [f"M{_n(pts[0][0])},{_n(pts[0][1])}"]
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1 = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 or 1
        l2 = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1
        r = min(radius, l1 / 2, l2 / 2)
        a = (x1 - (x1 - x0) / l1 * r, y1 - (y1 - y0) / l1 * r)
        b = (x1 + (x2 - x1) / l2 * r, y1 + (y2 - y1) / l2 * r)
        d.append(f"L{_n(a[0])},{_n(a[1])} Q{_n(x1)},{_n(y1)} {_n(b[0])},{_n(b[1])}")
    d.append(f"L{_n(pts[-1][0])},{_n(pts[-1][1])}")
    return " ".join(d)


def _lerp(a: Point, b: Point, t: float) -> Point:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _halfway(points: list[Point]) -> Point:
    """折れ線の長さの半分の位置。線の名前を置く。"""
    segs = list(zip(points, points[1:]))
    lengths = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in segs]
    half = sum(lengths) / 2
    for (a, b), length in zip(segs, lengths):
        if half <= length and length:
            t = half / length
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        half -= length
    return points[-1]


def _exit_label(box: Box, side: int, kind: str) -> tuple[Point, str, tuple]:
    """帯の箱から列の側へ出る線の名前の位置。箱の列に向いた縁の、左寄りに置く。

    帯から出る線は廊下に集まるので、線ごとに名前を書くと重なって読めない。
    箱ごとに、線の種類ごとの名前を1つだけ書く。まとめた線（本数つき）は線ごとに数が違うので、
    これまでどおり線の途中に書く。
    """
    x = box.x + 6
    y = box.y + box.h + 15 if side < 0 else box.y - 2
    return (x, y), "start", ("exit", box.key, kind)


@dataclass
class Route:
    d: str
    label: Point
    anchor: str = "middle"
    # 同じ値を持つ線の名前は、最初の1つだけを書く。帯の箱から出る線の名前を、箱ごとに1つにまとめる
    label_key: tuple | None = None
    # 名前を置ける所が無かった線。名前は図に書かず、線のツールチップ（<title>）にする
    tooltip: bool = False


def label_rect(text: str, at: Point, anchor: str = "middle") -> tuple[float, float, float, float]:
    """線の名前が占める矩形（左, 上, 右, 下）の見積もり。名前は、atのyから4だけ上を文字の下端にして書く。"""
    w = text_width(text, EDGE_LABEL_FONT)
    left = at[0] - w / 2 if anchor == "middle" else at[0]
    base = at[1] - 4
    return left, base - EDGE_LABEL_FONT * 0.85, left + w, base + EDGE_LABEL_FONT * 0.2


def _meets(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """2つの矩形（左, 上, 右, 下）が交わるか。"""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _hits(rect: tuple[float, float, float, float], box: Box) -> bool:
    return _meets(rect, (box.x, box.y, box.x + box.w, box.y + box.h))


# 帯の箱どうしを結ぶ線で、名前を置いてみる線の上の位置（0が始まり、1が終わり）。真ん中から順に試す
LABEL_SPOTS = (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8)


class _Router:
    """線の道筋を決める。同じ場所を通る線は、少しずつずらして重ならないようにする。"""

    def __init__(self, lay: Layout, lines: list[Line]):
        self.lay = lay
        self.lines = lines
        self.parallel = self._parallel()
        self.ports = self._ports()
        # 同じ通り道を使う線の数を、先に1度道筋を引いて数える。多ければ、ずらし幅を詰めて
        # 通り道の幅に収め、端に重ならないようにする
        self.used: dict[tuple, int] = {}
        self.counts: dict[tuple, int] = {}
        # 線の名前が占める矩形。帯の箱のそばに書く名前は、先に1度道筋を引いたときに集める
        self.exits: dict[tuple, tuple[float, float, float, float]] = {}
        self.spots: list[tuple[float, float, float, float]] = []
        for i in range(len(lines)):
            self.route(i)
        self.counts, self.used, self.spots = self.used, {}, []

    def _parallel(self) -> list[float]:
        """同じ2つの箱を結ぶ線どうしの、ずらし幅。"""
        groups: dict[frozenset[str], list[int]] = {}
        for i, line in enumerate(self.lines):
            groups.setdefault(frozenset((line.src, line.dst)), []).append(i)
        out = [0.0] * len(self.lines)
        for members in groups.values():
            n = len(members)
            for k, i in enumerate(members):
                out[i] = (k - (n - 1) / 2) * PARALLEL_STEP
        return out

    def _ports(self) -> dict[tuple[int, str], float]:
        """列から列への線が、箱の横から出入りする縦の位置。相手の高さの順に、箱の横に散らす。"""
        lay = self.lay
        sides: dict[tuple[str, str], list[tuple[float, int, str]]] = {}
        for i, line in enumerate(self.lines):
            ca, cb = lay.columns.get(line.src), lay.columns.get(line.dst)
            if ca is None or cb is None or ca == cb:
                continue
            hop = lay.dummies.get(i, [])
            for end, toward in (
                (line.src, hop[0] if hop else lay.boxes[line.dst]),
                (line.dst, hop[-1] if hop else lay.boxes[line.src]),
            ):
                box = lay.boxes[end]
                side = "r" if toward.x > box.x else "l"
                sides.setdefault((end, side), []).append((_center(toward)[1], i, end))
        out: dict[tuple[int, str], float] = {}
        for (key, _side), items in sides.items():
            box = lay.boxes[key]
            items.sort()
            n = len(items)
            step = min(box.h * 0.6 / n, 12)
            for k, (_, i, end) in enumerate(items):
                out[(i, end)] = box.y + box.h / 2 + (k - (n - 1) / 2) * step
        return out

    def _slot(self, key: tuple, spread: float, limit: float) -> float:
        """同じ通り道（廊下や列の間）を使う線を、順にspreadずつずらす。"""
        k = self.used.get(key, 0)
        self.used[key] = k + 1
        widest = self.counts.get(key, 0) // 2
        if widest and spread * widest > limit:
            spread = limit / widest
        # 0, +1, -1, +2, -2, ... の順に使う
        m = (k + 1) // 2 * (1 if k % 2 else -1)
        return max(-limit, min(limit, m * spread))

    def route(self, i: int) -> Route:
        route = self._route(i)
        line = self.lines[i]
        key = route.label_key
        if key is not None and key[0] == "exit" and not (line.count is None and line.kind in QUIET_LABELS):
            self.exits[key] = label_rect(_label_text(line), route.label, route.anchor)
        return route

    def _route(self, i: int) -> Route:
        lay, line = self.lay, self.lines[i]
        a, b = lay.boxes[line.src], lay.boxes[line.dst]
        offset = self.parallel[i]

        if line.src == line.dst:
            # 自分への線。箱の右に輪を描く
            x = a.x + a.w + 3
            y1, y2 = a.y + a.h * 0.3, a.y + a.h * 0.7
            bulge = 36 + abs(offset)
            d = f"M{_n(x)},{_n(y1)} C{_n(x + bulge)},{_n(y1 - 18)} {_n(x + bulge)},{_n(y2 + 18)} {_n(x)},{_n(y2)}"
            return Route(d, (x + bulge * 0.75 + 4, a.y + a.h / 2), "start")

        ca, cb = lay.columns.get(line.src), lay.columns.get(line.dst)
        if ca is not None and cb is not None and ca != cb:
            return self._between_columns(i, a, b, ca < cb)
        if ca is not None and ca == cb:
            return self._same_column(a, b, offset)
        if ca is not None or cb is not None:
            return self._band_column(i, a, b)
        return self._bands(i, a, b, offset)

    def _between_columns(self, i: int, a: Box, b: Box, rightward: bool) -> Route:
        """列から列へ。箱の横から出て、間の列の通り道を抜け、相手の横に入る曲線にする。"""
        lay, line = self.lay, self.lines[i]
        y1 = self.ports.get((i, line.src), a.y + a.h / 2)
        y2 = self.ports.get((i, line.dst), b.y + b.h / 2)
        if rightward:
            start, end = (a.x + a.w + 3, y1), (b.x - 3, y2)
        else:
            start, end = (a.x - 3, y1), (b.x + b.w + 3, y2)
        # 通り道では、列の幅いっぱいを水平に通る
        stops: list[tuple[Point, Point]] = []
        for dmy in lay.dummies.get(i, []):
            lane_left = dmy.x - LANE_PAD
            lane_right = dmy.x + dmy.w + LANE_PAD
            yy = dmy.y + dmy.h / 2
            stops.append(((lane_left, yy), (lane_right, yy)) if rightward else ((lane_right, yy), (lane_left, yy)))
        d = [f"M{_n(start[0])},{_n(start[1])}"]
        cur = start
        points = [start]
        for enter, leave in stops + [(end, end)]:
            mx = (enter[0] - cur[0]) / 2
            d.append(
                f"C{_n(cur[0] + mx)},{_n(cur[1])} {_n(enter[0] - mx)},{_n(enter[1])} {_n(enter[0])},{_n(enter[1])}"
            )
            points.append(enter)
            if leave != enter:
                d.append(f"L{_n(leave[0])},{_n(leave[1])}")
                points.append(leave)
            cur = leave
        if stops:
            label = _halfway(points)
        else:
            label = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        return Route(" ".join(d), label)

    def _same_column(self, a: Box, b: Box, offset: float) -> Route:
        lay = self.lay
        col = lay.columns[a.key]
        order = sorted(
            (k for k, c in lay.columns.items() if c == col), key=lambda k: lay.boxes[k].y
        )
        gap = abs(order.index(a.key) - order.index(b.key))
        if gap == 1 and offset == 0:
            # 隣り合う箱は、上下にまっすぐ結ぶ
            down = a.y < b.y
            x = a.x + a.w / 2
            y1 = a.y + a.h + 3 if down else a.y - 3
            y2 = b.y - 3 if down else b.y + b.h + 3
            return Route(f"M{_n(x)},{_n(y1)} L{_n(x)},{_n(y2)}", (x + 8, (y1 + y2) / 2 + 8), "start")
        # 離れた箱は、列の右側に張り出す弧で結ぶ
        x = a.x + a.w + 3
        y1, y2 = a.y + a.h / 2, b.y + b.h / 2
        bulge = min(COL_GAP - 14, 18 + 8 * gap) + offset
        d = f"M{_n(x)},{_n(y1)} C{_n(x + bulge)},{_n(y1)} {_n(x + bulge)},{_n(y2)} {_n(x)},{_n(y2)}"
        return Route(d, (x + bulge * 0.75 + 4, (y1 + y2) / 2), "start")

    def _channel_for(self, col: int, from_x: float) -> tuple[float, str]:
        """列colの箱に横から入るときに通る、列の間の位置と、入る側（lかr）。"""
        left, right = self.lay.channels[col], self.lay.channels[col + 1]
        if abs(left - from_x) <= abs(right - from_x):
            return left, "l"
        return right, "r"

    def _band_column(self, i: int, a: Box, b: Box) -> Route:
        """帯の箱と列の箱。帯から廊下へ出て、列の間を縦に通り、箱の横に入る。"""
        lay, line = self.lay, self.lines[i]
        band_box, col_box = (a, b) if a.key in lay.rows else (b, a)
        side = lay.band_side[lay.rows[band_box.key][0]]
        col = lay.columns[col_box.key]
        bx = band_box.x + band_box.w / 2 + self._slot(("port", band_box.key), 8, band_box.w / 2 - 10)
        # 帯の箱からは、列に向いた側（上の帯なら下、下の帯なら上）から出る
        by = band_box.y + band_box.h + 3 if side < 0 else band_box.y - 3
        # 帯が下なら列の下の廊下、上なら上の廊下を通る
        cy = lay.corridor[side] + self._slot(("corridor", side), 5, lay.corridor_half[side] - 5)
        chx, enter = self._channel_for(col, bx)
        chx += self._slot(("channel", round(chx)), 6, COL_GAP / 2 - 8)
        # 列から列への線は箱の横の真ん中あたりに集まるので、帯からの線は下寄りに入れる
        ty = col_box.y + col_box.h * 0.8 + self._slot(("side", col_box.key, enter), 5, col_box.h * 0.15)
        tx = col_box.x - 3 if enter == "l" else col_box.x + col_box.w + 3
        points = [(bx, by), (bx, cy), (chx, cy), (chx, ty), (tx, ty)]
        label = _halfway(points[1:3]) if abs(chx - bx) > 60 else _halfway(points)
        if band_box is b:
            points.reverse()
        if line.count is None:
            return Route(_rounded(points), *_exit_label(band_box, side, line.kind))
        return Route(_rounded(points), label)

    def _bands(self, i: int, a: Box, b: Box, offset: float) -> Route:
        lay = self.lay
        ra, rb = lay.rows[a.key], lay.rows[b.key]
        sa, sb = lay.band_side[ra[0]], lay.band_side[rb[0]]
        if ra[0] == rb[0] and ra[1] == rb[1] and abs(ra[2] - rb[2]) > 1:
            # 帯の同じ行で離れた箱は、列から遠い側へ張り出す弧で結ぶ
            (ax, _), (bx, _) = _center(a), _center(b)
            # 箱の底の、相手の側に寄せたところから出す。同じ箱から出る弧が重ならない
            ax += (12 if bx > ax else -12) + self._slot(("arc", a.key), 6, a.w / 2 - 20)
            bx += (12 if ax > bx else -12) + self._slot(("arc", b.key), 6, b.w / 2 - 20)
            y1 = a.y + a.h + 3 if sa > 0 else a.y - 3
            y2 = b.y + b.h + 3 if sa > 0 else b.y - 3
            depth = min(ARC_SPACE - 6, 10 + abs(bx - ax) * 0.06) + abs(offset)
            cy = max(y1, y2) + 2 * depth if sa > 0 else min(y1, y2) - 2 * depth
            d = f"M{_n(ax)},{_n(y1)} Q{_n((ax + bx) / 2)},{_n(cy)} {_n(bx)},{_n(y2)}"
            return Route(d, ((ax + bx) / 2, (y1 + 2 * cy + y2) / 4 + 4 * sa))
        if sa != sb and lay.lanes:
            # 上の帯から下の帯へ。廊下と列の間を通って、列の箱の上を通らない
            ax = a.x + a.w / 2 + self._slot(("port", a.key), 8, a.w / 2 - 10)
            bx = b.x + b.w / 2 + self._slot(("port", b.key), 8, b.w / 2 - 10)
            y1 = a.y + a.h + 3 if sa < 0 else a.y - 3
            y2 = b.y + b.h + 3 if sb < 0 else b.y - 3
            c1 = lay.corridor[sa] + self._slot(("corridor", sa), 5, lay.corridor_half[sa] - 5)
            c2 = lay.corridor[sb] + self._slot(("corridor", sb), 5, lay.corridor_half[sb] - 5)
            mid = (ax + bx) / 2
            chx = min(lay.channels, key=lambda c: (abs(c - mid), c))
            chx += self._slot(("channel", round(chx)), 6, COL_GAP / 2 - 8)
            points = [(ax, y1), (ax, c1), (chx, c1), (chx, c2), (bx, c2), (bx, y2)]
            if self.lines[i].count is None:
                return Route(_rounded(points), *_exit_label(a, sa, self.lines[i].kind))
            label = _halfway(points[1:3]) if abs(chx - ax) > 60 else _halfway(points)
            return Route(_rounded(points), label)
        # そのほか（同じ側の帯どうし）は、中心どうしを結ぶ直線を箱の縁で切る
        p = _clip(a, _center(b))
        q = _clip(b, _center(a))
        if offset == 0:
            return self._spot(i, f"M{_n(p[0])},{_n(p[1])} L{_n(q[0])},{_n(q[1])}", lambda t: _lerp(p, q, t))
        # 平行な線は、中点を横にずらした曲線にする
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = (dx * dx + dy * dy) ** 0.5 or 1
        nx, ny = -dy / length, dx / length
        c = ((p[0] + q[0]) / 2 + nx * offset * 2, (p[1] + q[1]) / 2 + ny * offset * 2)
        d = f"M{_n(p[0])},{_n(p[1])} Q{_n(c[0])},{_n(c[1])} {_n(q[0])},{_n(q[1])}"
        return self._spot(i, d, lambda t: _lerp(_lerp(p, c, t), _lerp(c, q, t), t))

    def _spot(self, i: int, d: str, at) -> Route:
        """帯の箱どうしを結ぶ線の名前を、箱にもほかの線の名前にも重ならない位置に置く。
        行をまたぐ線は、間の箱の上を通ることがあり、真ん中に置くと名前が箱に隠れる。
        線の上のLABEL_SPOTSの位置を順に試し、どこも重なるなら、名前をツールチップにする。
        """
        line = self.lines[i]
        if line.count is None and line.kind in QUIET_LABELS:
            return Route(d, at(0.5))
        text = _label_text(line)
        boxes = self.lay.boxes.values()
        taken = list(self.exits.values()) + self.spots
        for t in LABEL_SPOTS:
            point = at(t)
            rect = label_rect(text, point)
            if not any(_hits(rect, box) for box in boxes) and not any(_meets(rect, o) for o in taken):
                self.spots.append(rect)
                return Route(d, point)
        return Route(d, at(0.5), tooltip=True)


# --------------------------------------------------------------------------
# 書き出し
# --------------------------------------------------------------------------
# まとめた線の名前を、ほかの名前や箱に重ならないようにずらすときの、位置の候補。
# 縦は、線の名前の1行分（LABEL_STEP）ずつ、もとの位置の上下に離していく。
# それで収まらなければ、名前の幅だけ左右にずらして、また上下を試す
LABEL_STEP = 12
COUNTED_SHIFTS = (0, -1, 1, -2, 2, -3, 3)


def _settle_counted(routes: list[Route], lines: list[Line], lay: Layout) -> list[Route]:
    """まとめた線（本数つき）の名前を、互いに重ならない位置に置き直す。

    型ごとにまとめた図では、同じ2つの箱の間を、種類の違う線が何本も通る。線の名前は
    線の真ん中に書くので、名前どうしが重なる。本数の多い線から順に、もとの位置から
    LABEL_STEPずつ上下に、さらに名前の幅だけ左右にずらし、箱にも、先に置いた名前にも重ならない所に書く。
    どこも重なるなら、名前をその線のツールチップにする。本数の無い線の名前は動かさない。
    """
    # 列の見出し（層の番号と名前）にも重ねない
    taken: list[tuple[float, float, float, float]] = []
    for t, x, y, _w, _h in lay.lanes:
        spec = schema.NODE_TYPES[t]
        head = f"{spec['layer']} {spec['label']}"
        taken.append((x + 12, y + 22 - LANE_LABEL_FONT, x + 12 + text_width(head, LANE_LABEL_FONT), y + 22 + 3))
    seen: set[tuple] = set()
    for route, line in zip(routes, lines):
        if line.count is not None or route.tooltip or (line.kind in QUIET_LABELS):
            continue
        if route.label_key is not None:
            if route.label_key in seen:
                continue
            seen.add(route.label_key)
        taken.append(label_rect(_label_text(line), route.label, route.anchor))
    boxes = list(lay.boxes.values())
    order = sorted(
        (i for i, line in enumerate(lines) if line.count is not None and not routes[i].tooltip),
        key=lambda i: (-(lines[i].count or 0), i),
    )
    out = list(routes)
    for i in order:
        route, text = routes[i], _label_text(lines[i])
        w = text_width(text, EDGE_LABEL_FONT) + 6
        for dx, k in ((dx, k) for dx in (0, -w, w) for k in COUNTED_SHIFTS):
            point = (route.label[0] + dx, route.label[1] + k * LABEL_STEP)
            rect = label_rect(text, point, route.anchor)
            if not any(_hits(rect, box) for box in boxes) and not any(_meets(rect, o) for o in taken):
                taken.append(rect)
                out[i] = Route(route.d, point, route.anchor, route.label_key)
                break
        else:
            out[i] = Route(route.d, route.label, route.anchor, route.label_key, tooltip=True)
    return out


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _sec(v: float) -> str:
    r = round(v, 3)
    return f"{r:g}s" if r else "0s"


def _flow(lay: Layout, lines: list[Line], ids: list[str], period: float) -> list[str]:
    """depends_onの線の上を流れる点と、行き着いた先の箱が光る動き（SMIL）。

    点は1周（period）のうちTRAVELの割合で線を進み、着いたところで先の箱が光る。
    始まりの時刻を負にずらして、表示したときから全部の点が動いているようにする。
    ずらし幅は、線の始まりの列で決める。左の列から右の列へ、波のように流れる。
    """
    out: list[str] = []
    glows: dict[tuple[str, str], None] = {}
    per_column: dict[int, int] = {}
    ncols = max(len({c for c in lay.columns.values()}), 1)
    for line, eid in zip(lines, ids):
        if line.kind != "depends_on" or line.src == line.dst:
            continue
        col = lay.columns.get(line.src, 0)
        j = per_column.get(col, 0)
        per_column[col] = j + 1
        phase = (col / ncols * 0.5 + (j % 4) * 0.07) % 1.0
        begin = _sec(-phase * period)
        dur = _sec(period)
        out.append(
            f'<circle class="flow-dot k-{line.kind}" r="4" opacity="0">'
            f'<animateMotion dur="{dur}" begin="{begin}" repeatCount="indefinite" '
            f'keyPoints="0;1;1" keyTimes="0;{TRAVEL};1" calcMode="spline" '
            f'keySplines="0.45 0 0.25 1;0 0 1 1"><mpath href="#{eid}"/></animateMotion>'
            f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.08;{TRAVEL - 0.06:g};{TRAVEL};1" '
            f'dur="{dur}" begin="{begin}" repeatCount="indefinite"/></circle>'
        )
        glows[(line.dst, begin)] = None
    for dst, begin in glows:
        b = lay.boxes[dst]
        out.append(
            f'<rect class="glow" x="{_n(b.x - 3)}" y="{_n(b.y - 3)}" width="{_n(b.w + 6)}" '
            f'height="{_n(b.h + 6)}" opacity="0">'
            f'<animate attributeName="opacity" values="0;0;1;0;0" '
            f'keyTimes="0;{TRAVEL - 0.04:g};{TRAVEL + 0.04:g};{TRAVEL + 0.22:g};1" '
            f'dur="{_sec(period)}" begin="{begin}" repeatCount="indefinite"/></rect>'
        )
    return out


def _draw(
    lay: Layout,
    lines: list[Line],
    css: str,
    *,
    animate: bool,
    period: float,
    title: str,
) -> str:
    if "]]>" in css:
        raise ValueError("テーマのCSSに]]>があると、SVGに埋め込めない")
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lay.width} {lay.height}" '
        f'width="{lay.width}" height="{lay.height}" class="graph" role="img" aria-label="{_esc(title)}">',
        f"<title>{_esc(title)}</title>",
        "<style><![CDATA[",
        css.rstrip("\n"),
        "]]></style>",
    ]

    kinds = sorted({l.kind for l in lines if l.kind not in _UNDIRECTED})
    if kinds:
        o.append("<defs>")
        for kind in kinds:
            o.append(
                f'<marker id="arrow-{kind}" class="arrow k-{kind}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path class="arrow-head k-{kind}" d="M0,0 L10,5 L0,10 z"/></marker>'
            )
        o.append("</defs>")

    o.append(f'<rect class="bg" width="{lay.width}" height="{lay.height}"/>')

    o.append('<g class="lanes">')
    for t, x, y, w, h in lay.lanes:
        spec = schema.NODE_TYPES[t]
        o.append(
            f'<g class="lane t-{t}"><rect class="lane-bg" x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"/>'
            f'<text class="lane-label" x="{_n(x + 12)}" y="{_n(y + 22)}">{spec["layer"]} {_esc(spec["label"])}</text></g>'
        )
    for t, x, y in lay.bands:
        o.append(
            f'<g class="band t-{t}"><text class="band-label" x="{_n(x)}" y="{_n(y)}">'
            f'{_esc(schema.NODE_TYPES[t]["label"])}</text></g>'
        )
    o.append("</g>")

    router = _Router(lay, lines)
    ids = [f"e{i}" for i in range(len(lines))]
    routes = _settle_counted([router.route(i) for i in range(len(lines))], lines, lay)
    labels: list[str] = []
    labelled: set[tuple] = set()
    o.append('<g class="edges">')
    for line, eid, route in zip(lines, ids, routes):
        d, (lx, ly) = route.d, route.label
        classes = f"edge k-{line.kind}"
        if line.kind in _UNDIRECTED:
            classes += " undirected"
            marker = ""
        else:
            marker = f' marker-end="url(#arrow-{line.kind})"'
        text = _label_text(line)
        if route.tooltip:
            o.append(
                f'<path id="{eid}" class="{classes}" d="{d}"{marker} '
                f'data-src="{_esc(line.src)}" data-dst="{_esc(line.dst)}"><title>{_esc(text)}</title></path>'
            )
            continue
        o.append(
            f'<path id="{eid}" class="{classes}" d="{d}"{marker} '
            f'data-src="{_esc(line.src)}" data-dst="{_esc(line.dst)}"/>'
        )
        if route.label_key is not None:
            if route.label_key in labelled:
                continue
            labelled.add(route.label_key)
        counted = "" if line.count is None else " counted"
        labels.append(
            f'<text class="edge-label k-{line.kind}{counted}" x="{_n(lx)}" y="{_n(ly - 4)}" '
            f'text-anchor="{route.anchor}">{_esc(text)}</text>'
        )
    o.append("</g>")
    o.append('<g class="edge-labels">')
    o.extend(labels)
    o.append("</g>")

    if animate:
        flow = _flow(lay, lines, ids, period)
        if flow:
            o.append('<g class="flow">')
            o.extend(flow)
            o.append("</g>")

    o.append('<g class="nodes">')
    for box in sorted(lay.boxes.values(), key=lambda b: (b.y, b.x, b.key)):
        o.append(f'<g class="{" ".join(box.classes)}" data-id="{_esc(box.key)}">')
        o.append(
            f'<rect class="box" x="{_n(box.x)}" y="{_n(box.y)}" width="{_n(box.w)}" height="{_n(box.h)}"/>'
        )
        o.append(f'<text class="node-id" x="{_n(box.x + PAD_X)}" y="{_n(box.y + 22)}">{_esc(box.head)}</text>')
        spans = "".join(
            f'<tspan x="{_n(box.x + PAD_X)}" y="{_n(box.y + 41 + LINE_H * i)}">{_esc(l)}</tspan>'
            for i, l in enumerate(box.lines)
        )
        o.append(f'<text class="node-title">{spans}</text>')
        o.append("</g>")
    o.append("</g>")
    o.append("</svg>")
    return "\n".join(o) + "\n"


def to_svg(
    graph: Graph,
    *,
    css: str,
    include_mentions: bool = False,
    focus: set[str] | None = None,
    types: set[str] | None = None,
    aggregate: bool = False,
    animate: bool = True,
    period: float = 6.0,
    title: str = "設計文書のグラフ",
) -> str:
    """グラフをSVGの図にする。typesとaggregateの選び方は、Mermaidの図と同じである。"""
    if aggregate:
        boxes, lines = _parts_aggregate(graph, include_mentions)
    elif types:
        boxes, lines = _parts_types(graph, types, include_mentions)
    else:
        boxes, lines = _parts_plain(graph, include_mentions, focus or set())
    lay = _layout(boxes, lines)
    return _draw(lay, lines, css, animate=animate, period=period, title=title)
