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
| `contract` | `CON-` | `40-contracts/` | 40 | 境界をまたぐ約束事。API・UI 操作・ファイル形式・メッセージ構造 |
| `adr` | `ADR-` | `50-adr/` | 横断 | 決定・背景・却下案・影響 |

## 層の数字の意味

数字は**抽象度**であって実行順ではない。小さいほど「変わりにくく、他が依存する側」。

- `depends_on` は同じか小さい数字にしか向けられない（`G007`）
- ADR とメタは横断なので層ルールの対象外

## 採番

- `ARCH` `DOM` `UC` `CON` は 2 桁ゼロ埋め（`UC-01`）。50 を超えそうなら 3 桁に切り替える
- `ADR` は 4 桁ゼロ埋め（`ADR-0001`）。**欠番を作らず、取り消しは `deprecated` + `supersedes`**
- 一度振った id は再利用しない。削除したノードの id は永久欠番

## ノードを分割するとき

1 つのノードが大きくなりすぎたら分割する。目安は「読む人が一度に必要としない情報が
同居している」とき。分割した子には**新しい id を振り**、親を `refines` で指す。

```
UC-03 匿名でメッセージを投稿する        ← 親。アクター・事前条件・事後条件など共通部分
 ├── UC-09 ボタン経路で匿名投稿する      refines: [UC-03]
 └── UC-10 コマンド経路で匿名投稿する    refines: [UC-03]
```

守ること。

- **親を残す。** 親には全体の見取り図と共通部分を書く。親が空になるなら分割ではないので、
  `refines` を使わず親のノードごと畳む
- **子の id は新規に振る。** 親の id に枝番（`UC-03a`）を付けない。採番規約から外れる
- **子も index に載せる。** 載せないと `G005` で落ちる
- **前提は `refines` ではない。** 別の概念に依存しているだけなら `depends_on`。
  判断基準は [META-01](./graph-rules.md) の「`refines` と `depends_on` の使い分け」

`refines` は同じ `type` 同士に限られる（`G008`）。層をまたぐ分割は分割ではなく、
概念の切り出しなので `depends_on` で表す。

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

既定では `00-meta/templates/<type>.md` が使われる。`contract` だけ 2 種類ある。

| type | 既定の雛形 | 別の雛形 |
| --- | --- | --- |
| `contract` | `contract.md`（伝送方式に依存しない） | `contract-http.md`（HTTP 用） |
| その他 | `<type>.md` | — |

```bash
python -m tools.graph new --type contract --template contract-http --id CON-02 --title "..."
```

既定を汎用にしてあるのは、この層の抽象が「境界をまたぐ約束事」であって
HTTP に限らないため。UI 操作・メッセージキュー・ファイル形式もこの層に置ける。

## id を変えるとき

層を組み替えて接頭辞が変わった場合など、id の変更は手でやらない。
フロントマターのエッジ・本文の `[[ID]]`・目次の一覧・相対リンクのどれかを必ず落とす。

```bash
python -m tools.graph rename --from API-01 --to CON-01
```

新しい接頭辞が別の種別を指す場合は、`type` の書き換えとファイルの移動も同時に行う。
ディレクトリが決まらない `index` ノードは `--path` で移動先を明示する。

```bash
python -m tools.graph rename --from IDX-API --to IDX-CON --path docs/40-contracts/index.md
```

**本文の散文までは直らない。** 「40-api ディレクトリ」のような、id でもリンクでもない
記述は自分で直す。`--dry-run` で影響範囲を先に見ておくとよい。

コードブロック・コードスパン・HTML コメントの中は書き換えない。
この文書に載せた**使い方の例**が実行のたびに壊れないようにするため
（`check` がリンクを数えない範囲と同じ）。

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

**related** — 依存はしないが併読すべきノード

- [META-01 グラフの規約](./graph-rules.md)

**このノードを参照しているノード**

- (related) [META-01 グラフの規約](./graph-rules.md)

<!-- graph:auto:end -->
