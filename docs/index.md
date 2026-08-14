---
id: IDX-ROOT
type: index
title: ドキュメントグラフのルート
status: stable
tags: [index]
---

# ドキュメントグラフ

このリポジトリの設計文書は **1 文書 = 1 ノード、リンク = エッジ** のグラフとして管理する。
すべてのノードはこのページから辿れなければならない（辿れないものは `G005` で落ちる）。

まず読むもの:

- [META-01 グラフの規約](./00-meta/graph-rules.md) — ルール ID と違反時の直し方
- [META-02 ノード種別と層](./00-meta/node-types.md) — どの文書をどこに置くか

## 層

抽象度の高い順に並ぶ。**依存は必ず上（数字の小さい側）へ向ける。**

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

グラフを図で見る:

```bash
python -m tools.graph render --format mermaid --out docs/graph.mmd
```
