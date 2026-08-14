# テンプレートの変更履歴

`graph-doc-template` 本体の変更を記録する。**派生プロジェクト固有の変更は
各リポジトリで記録すること。** このファイルはテンプレートの履歴だけを扱う。

このファイルは共有ファイルなので `git merge template/main` で更新される。
**マージしたらここを読む。** 何が変わり、何をすべきかが分かる。

現在の版:

```bash
python -m tools.graph --version
```

## 版の付け方

| 上げる箇所 | 意味 | 取り込む側の作業 |
| --- | --- | --- |
| major | **移行作業が要る** | 下記の「移行手順」に従った作業が必要。マージだけでは壊れる |
| minor | 追加のみ | 通常のマージで済む。新しい警告が出ることはある |
| patch | 文言・不具合の修正 | 通常のマージで済む |

**破壊的な変更を入れるときは、必ず「移行手順」を書く。**
書けないなら、その変更は入れない。手順のない破壊的変更は、
放置されたリポジトリを黙って壊す。

---

## 1.1.0 — 2026-08-14

### 追加

**`upgrade` コマンド。** テンプレートとの差を調べる。**読み取りのみで、
何も書き込まない。** 取り込みは従来どおり README の手順で行う。

```bash
python -m tools.graph upgrade
```

- ローカルとテンプレートの版を比べる
- 遅れていれば、その間の変更履歴をここから抜き出して表示する
- major が上がっていれば「破壊的変更を含む」と警告する
- 変更されるファイルの一覧を出す

**解決している問題**: 派生リポジトリは、マージし忘れても何も起きない。
遅れていることに気づく機会が存在しなかった。

**`tools/graph/migrations/` を新設。** 破壊的変更の移行スクリプトを置く場所。
まだ 1 つもない。書き方の約束は同ディレクトリの `__init__.py` にある。
枠組み（版の比較による自動実行）は、実例が 2〜3 個たまってから設計する。

### 変更

`git` の呼び出しを `tools/graph/git.py` に共通化した（`history.py` と `upgrade.py` で使う）。

### 取り込む側の作業

なし。通常のマージで済む。

**ただし 1.0.0 のリポジトリでは `upgrade` がまだ存在しない。**
この版に上げる最初の 1 回だけは、手動で `git fetch template && git merge template/main`
する必要がある。以後は `upgrade` で差を確認できる。

---

## 1.0.0 — 2026-08-14

版を定めた最初の版。ここまでの内容をまとめる。

### 含まれるもの

**層とノード種別**

| 層 | 種別 | 接頭辞 |
| --- | --- | --- |
| 10 | `architecture` | `ARCH-` |
| 20 | `domain` | `DOM-` |
| 30 | `usecase` | `UC-` |
| 40 | `contract` | `CON-` |
| 横断 | `adr` | `ADR-` |
| — | `index` / `meta` | `IDX-` / `META-` |

**エッジ種別** — `depends_on` / `refines` / `related` / `supersedes` / `decides`。
本文の `[[ID]]` は `mentions` として扱い、リンク切れのみ検査する。

**検証ルール** — `G001`〜`G012`。`G001`〜`G008` は構造の誤り（CI 失敗）、
`G009`〜`G012` は健全性の警告（`--strict` でのみ失敗）。

**コマンド** — `check` / `sync` / `render` / `new` / `rename` / `reset-samples` / `stats`。

**雛形** — `architecture` / `domain` / `usecase` / `usecase-runbook` /
`contract` / `contract-http` / `adr`。

**仕組み**

- 更新の取り込みは `git merge template/main`。`.gitattributes` の `merge=ours` で
  `README.md`・各 `index.md`・`adr-0001` はプロジェクト側が残る
- CI は `check` / `sync --check` / `render --into README.md --check` の 3 本
- 外部パッケージ依存なし（標準ライブラリのみ）

### 1.0.0 より前にあった破壊的変更（記録）

版を定める前に破壊的変更が 1 件あった。当時は派生プロジェクト 3 件を手で直したが、
**同種の変更が再び起きたときのために手順を残す。**

#### 層 `40-api` を `40-contracts` に改称

この層は HTTP の API に限らないため（実プロジェクトでは Discord の
インタラクションと CSV の形式が入った）、名前を実態に合わせた。
`type`・接頭辞・ディレクトリが同時に変わる。

**マージしただけでは壊れる。** 契約ノードの `type: api` が未知の語彙になり、
ノードの数だけ `G003` が出る。

```
ERROR G003 docs/40-api/api-01-....md: 未知の type 'api'（許可: ..., contract, adr）
```

移行手順:

1. `tools/graph/schema.py` の `NODE_TYPES` を更新する
   （`api` → `contract`、`API` → `CON`、`40-api` → `40-contracts`）

2. 契約ノードを 1 つずつ改名する。`type` の書き換えとファイルの移動も同時に行われる

   ```bash
   python -m tools.graph rename --from API-01 --to CON-01
   ```

3. 目次ノードは種別からディレクトリが決まらないので、移動先を明示する

   ```bash
   python -m tools.graph rename --from IDX-API --to IDX-CON --path docs/40-contracts/index.md
   ```

4. 雛形の名前を合わせる（`api.md` → `contract.md`、`api-http.md` → `contract-http.md`）

5. **散文は `rename` の対象外。** 「`40-api` ディレクトリ」のような記述は手で直す

6. `check` → `sync` → `render --into README.md` を回して確認する

`rename` は id を単語として置換し、コードブロック・コードスパン・HTML コメントの
中は書き換えない。規約に載せた使用例が壊れないようにするため。
