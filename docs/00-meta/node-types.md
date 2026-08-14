---
id: META-02
type: meta
title: ノード種別と層
status: stable
tags: [meta, taxonomy]
related:
  - META-01
---

# ノード種別と層

`tools/graph/schema.py` の `NODE_TYPES` がこの表の実体。**語彙を変えるときは両方を直す。**

| `type` | 接頭辞 | 置き場所 | 層 | 何を書くか |
| --- | --- | --- | --- | --- |
| `index` | `IDX-` | 各ディレクトリ | — | その層の目次。子ノードの一覧 |
| `meta` | `META-` | `00-meta/` | — | 規約・語彙。プロダクトの中身は書かない |
| `architecture` | `ARCH-` | `10-architecture/` | 10 | 構成要素と責務、技術選定の前提 |
| `domain` | `DOM-` | `20-domain/` | 20 | 概念・不変条件・用語。UI も API も出さない |
| `usecase` | `UC-` | `30-usecases/` | 30 | 誰が何をして何が起きるか。事前・事後条件 |
| `api` | `API-` | `40-api/` | 40 | 境界の契約。リクエスト / レスポンス / エラー |
| `adr` | `ADR-` | `50-adr/` | 横断 | 決定・背景・却下案・影響 |

## 層の数字の意味

数字は**抽象度**であって実行順ではない。小さいほど「変わりにくく、他が依存する側」。

- `depends_on` は同じか小さい数字にしか向けられない（`G007`）
- ADR とメタは横断なので層ルールの対象外

## 採番

- `ARCH` `DOM` `UC` `API` は 2 桁ゼロ埋め（`UC-01`）。50 を超えそうなら 3 桁に切り替える
- `ADR` は 4 桁ゼロ埋め（`ADR-0001`）。**欠番を作らず、取り消しは `deprecated` + `supersedes`**
- 一度振った id は再利用しない。削除したノードの id は永久欠番

## status の意味

| status | 意味 | 依存してよいか |
| --- | --- | --- |
| `draft` | 書きかけ。壊れてもよい | 参照は可、`stable` からの依存は警告 |
| `review` | レビュー中。大枠は固まった | 可 |
| `stable` | 合意済み。変更は ADR 経由 | 可 |
| `deprecated` | 置き換え済み。`supersedes` の対象 | 新規依存は作らない |

## ファイル名

`{id を小文字にしたもの}-{英数字スラッグ}.md`

```
docs/30-usecases/uc-01-confirm-booking.md
docs/50-adr/adr-0001-graph-driven-docs.md
```

日本語タイトルからスラッグを作れないときは `--slug` を明示する。
省略すると `dom-02.md` のように id だけのファイル名になる。

```bash
python -m tools.graph new --type usecase --id UC-02 --title "予約をキャンセルする" --slug cancel-booking
```

## 雛形

既定では `00-meta/templates/<type>.md` が使われる。`api` だけ 2 種類ある。

| type | 既定の雛形 | 別の雛形 |
| --- | --- | --- |
| `api` | `api.md`（伝送方式に依存しない契約） | `api-http.md`（HTTP 用） |
| その他 | `<type>.md` | — |

```bash
python -m tools.graph new --type api --template api-http --id API-02 --title "..."
```

`api` の既定を汎用にしてあるのは、この層の抽象が「境界の契約」であって
HTTP に限らないため。UI 操作・メッセージキュー・ファイル形式もこの層に置ける。

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

**related** — 依存はしないが併読すべきノード

- [META-01 グラフの規約](./graph-rules.md)

**このノードを参照しているノード**

- (related) [META-01 グラフの規約](./graph-rules.md)

<!-- graph:auto:end -->
