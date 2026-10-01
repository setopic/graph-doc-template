---
id: IDX-UC
type: index
title: ユースケース
status: stable
tags: [index]
---

# ユースケース（層 30）

誰が何をして、何が起きるかを書く。**事後条件はドメインの用語だけで書く。**

`depends_on`には、そのユースケースが前提とするドメインノードを挙げる。
`depends_on`が空のユースケースは、扱っている概念がまだ定義されていない。

## ノード一覧

<!-- graph:children:start -->
- [UC-01 予約を確定する](./uc-01-sample-confirm-booking.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type usecase --id UC-02 --title "..." --slug some-slug
```
