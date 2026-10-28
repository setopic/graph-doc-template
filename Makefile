PYTHON ?= python

# リポジトリ固有の設定があれば読む（無くてもよい）。
# READMEの図の線が多すぎる（G018）なら、**そのリポジトリのgraph.mkにだけ**次の1行を置く。
#
#     README_GRAPH_ARGS = --aggregate
#
# READMEの図をSVGではなくMermaidで描くなら、graph.mkに次の1行を置く。
#
#     README_GRAPH_FORMAT = mermaid
#
# graph-doc-templateはgraph.mkを配らない。だから取り込み（make update）で
# 競合せず、リポジトリごとに図の形を選べる。上の層のテンプレートがgraph.mkを
# 配るなら、取り込みで競合することがある。そのときは、その層の決まりに従う。
-include graph.mk

# READMEの図に足す引数。既定は無し（全ノードをそのまま描く）。
README_GRAPH_ARGS ?=

# READMEの図の形式（svgかmermaid）と、SVGの書き出し先。
# svgでは、SVGをファイルに書き、READMEのマーカーの中にはその画像への参照を書く。
README_GRAPH_FORMAT ?= svg
README_GRAPH_SVG ?= docs/graph.svg
README_GRAPH_OUT = $(if $(filter svg,$(README_GRAPH_FORMAT)),--out $(README_GRAPH_SVG))

.PHONY: help setup update update-fetch check strict sync sync-check linkify linkify-check graph json readme readme-check gif stats all

help:
	@echo "setup         以前のsetupが常設したmerge=oursドライバの設定を外す（何度実行してもよい）"
	@echo "update        テンプレートを取り込む（このときだけmerge=oursドライバを効かせる）"
	@echo "check         グラフを検証する（エラーがあれば失敗）"
	@echo "strict        警告も失敗として扱う"
	@echo "sync          各文書末尾の関連ドキュメントを再生成する"
	@echo "sync-check    再生成が必要なら失敗する（CI用）"
	@echo "linkify       本文の[[ID]]を相対リンクに直す"
	@echo "linkify-check 直す必要があれば失敗する（CI用）"
	@echo "graph         docs/graph.mmdを書き出す（Mermaid）"
	@echo "json          docs/graph.jsonを書き出す"
	@echo "readme        READMEの図を再生成する（既定はSVG。graph.mkのREADME_GRAPH_FORMATで選ぶ）"
	@echo "readme-check  READMEの図が古ければ失敗する（CI用）"
	@echo "gif           READMEのSVGの図からdocs/graph.gifを作る（任意。EdgeかChromeとPillowが要る）"
	@echo "stats         ノード数・エッジ数を表示する"
	@echo "all           check + sync + linkify + readme"

# テンプレートを取り込む。.gitattributesのmerge=oursは、プロジェクト側の内容を残すための指定で、
# このドライバを効かせたマージでだけ働く。ドライバは、この取り込みのときだけ-cで効かせる。
#
# 以前はsetupでドライバをクローンに常設していた。常設すると、テンプレートの取り込み以外の
# マージ（作業ブランチどうしのマージ）でもmerge=oursが効き、相手の変更が何も言わずに落ちる
# （setopic/graph-doc-template#36）。
#
# 初回だけは、履歴を共有していないので、引数を足す。
#   make update UPDATE_ARGS=--allow-unrelated-histories
#
# マージコミットのメッセージは「テンプレートの<バージョン>を取り込む」にする（setopic/graph-doc-template#116）。
# 渡さないと、gitの既定の英語の文が付く。メッセージはファイルに書いて-Fで渡す。
# Windowsのmakeはcmd経由で引数を渡すので、-mで日本語を渡すと文字が化ける。
# バージョンは、取り込んだ後のテンプレートのバージョンを読むので、fetchが済んでから展開する
# （makeはレシピの全行を、最初の行を実行する前に展開する。だからfetchを別のターゲットにする）。
# バージョンは層ごとにあるので、遅れている層のバージョンを`upgrade --label`で並べる（setopic/graph-doc-template#125）。
# 下の層だけなら「1.38.0」、上の層だけなら「<label>-0.14.0」のようになる。
# UPDATE_ARGSに-mを足すと、そのメッセージは次の段落に付く。
UPDATE_ARGS ?=
UPDATE_NEXT = $(shell $(PYTHON) -m tools.graph upgrade --label)
UPDATE_MSG_FILE = $(shell git rev-parse --path-format=absolute --git-path TEMPLATE_UPDATE_MSG)
update: update-fetch
	$(file >$(UPDATE_MSG_FILE),テンプレート$(if $(UPDATE_NEXT),の$(UPDATE_NEXT))を取り込む)
	git -c merge.ours.driver=true merge -F $(UPDATE_MSG_FILE) template/main $(UPDATE_ARGS)

update-fetch:
	git fetch template

# 以前のsetupが常設したドライバの設定を外す。設定が無ければ何もしない。何度実行してもよい。
# 外したあとのマージは、merge=oursのファイルも通常のマージになる。両側が変えていれば、
# 何も言わずに落ちる代わりに、競合として表に出る。
setup:
	@git config --unset merge.ours.driver || true
	@echo "merge=oursドライバの常設を外した。テンプレートの取り込みはmake updateで行う。"

check:
	$(PYTHON) -m tools.graph check

strict:
	$(PYTHON) -m tools.graph check --strict

sync:
	$(PYTHON) -m tools.graph sync

sync-check:
	$(PYTHON) -m tools.graph sync --check

linkify:
	$(PYTHON) -m tools.graph linkify

linkify-check:
	$(PYTHON) -m tools.graph linkify --check

readme:
	$(PYTHON) -m tools.graph render --format $(README_GRAPH_FORMAT) --into README.md $(README_GRAPH_OUT) $(README_GRAPH_ARGS)

readme-check:
	$(PYTHON) -m tools.graph render --format $(README_GRAPH_FORMAT) --into README.md --check $(README_GRAPH_OUT) $(README_GRAPH_ARGS)

# スライドや記事に貼るGIF。CIでは作らない。docs/graph.gifは.gitignoreで外してある
gif:
	$(PYTHON) -m tools.graph gif --svg $(README_GRAPH_SVG) --out docs/graph.gif

graph:
	$(PYTHON) -m tools.graph render --format mermaid --out docs/graph.mmd

json:
	$(PYTHON) -m tools.graph render --format json --out docs/graph.json

stats:
	$(PYTHON) -m tools.graph stats

all: check sync linkify readme
