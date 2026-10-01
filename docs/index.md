---
id: IDX-ROOT
type: index
title: ドキュメントグラフのルート
status: stable
tags: [index]
---

# ドキュメントグラフ

このリポジトリの設計文書は、1つの文書を1つのノード、リンクをエッジとするグラフとして管理する。
すべてのノードは、このページから辿れなければならない。辿れないノードがあると`G005`で落ちる。

最初に読む文書は次の3つである。

| 文書 | 書いてあること |
| --- | --- |
| [META-01 グラフの規約](./00-meta/graph-rules.md) | ルールIDと、違反したときの直し方 |
| [META-02 ノード種別と層](./00-meta/node-types.md) | どの文書をどこに置くか |
| [META-03 本文のレビュー（AI）](./00-meta/ai-review.md) | checkとは別に、AIが本文について助言する |

## 層

層は抽象度の高い順に並んでいる。**依存は必ず上（数字の小さい側）へ向ける。**

| 層 | ディレクトリ | 目次 |
| --- | --- | --- |
| 10 | `10-architecture/` | [IDX-ARCH アーキテクチャ](./10-architecture/index.md) |
| 20 | `20-domain/` | [IDX-DOM ドメイン](./20-domain/index.md) |
| 30 | `30-usecases/` | [IDX-UC ユースケース](./30-usecases/index.md) |
| 40 | `40-contracts/` | [IDX-CON 契約](./40-contracts/index.md) |
| 横断 | `50-adr/` | [IDX-ADR 決定記録](./50-adr/index.md) |

## 使い方

```bash
python -m tools.graph check
```

グラフを図で見るときは、次を使う。

```bash
python -m tools.graph render --format mermaid --out docs/graph.mmd
```
