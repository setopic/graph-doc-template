---
id: IDX-DOM
type: index
title: ドメイン
status: stable
tags: [index]
---

# ドメイン（層 20）

概念・属性・不変条件・用語。**この層の言葉が、上の層すべての共通語彙になる。**

書かないこと: 画面、エンドポイント、フレームワークの都合。
ユースケースを参照したくなったら、それは概念の切り出しが足りていない合図。

## ノード一覧

<!-- graph:children:start -->
- [DOM-01 予約](./dom-01-sample-booking.md)
<!-- graph:children:end -->

## 追加するとき

```bash
python -m tools.graph new --type domain --id DOM-02 --title "..." --slug some-slug
```

<!-- graph:terms:start -->

## 用語の一覧（自動生成 / 手で編集しない）

各ドメインノードの「用語」表を集めたもの。**直すときは元のノードの表を直す。**
同じ意味のことを書くときは、ここにある語を使う。

### [DOM-01 予約](./dom-01-sample-booking.md)

| 用語 | 意味 | 旧称 |
| --- | --- | --- |
| 資源 | 確保の対象となるもの。部屋・席・枠のどれでもよく、**実体の種類を問わない** | — |
| 確定 | 重なりの排除が保証された状態。**誰かが承認することではない** | 本予約（改める前の呼び名） |

<!-- graph:terms:end -->
