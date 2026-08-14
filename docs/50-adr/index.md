---
id: IDX-ADR
type: index
title: 決定記録
status: stable
tags: [index]
---

# 決定記録 / ADR（横断）

**決定と、その理由と、却下した案**を残す。層ルールの対象外なので、どの層のノードにも
`decides` を張れる。

- 決定を変えるときは既存 ADR を書き換えず、新しい ADR を起票して `supersedes` で繋ぐ
- 置き換えられた側は `status: deprecated` にする
- 採番は 4 桁ゼロ埋め、欠番を作らない

## ノード一覧

<!-- graph:children:start -->
- [ADR-0001 設計文書をグラフとして管理する](./adr-0001-graph-driven-docs.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type adr --id ADR-0002 --title "..." --slug some-slug
```
