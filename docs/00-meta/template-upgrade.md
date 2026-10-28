---
id: META-08
type: meta
title: テンプレートの更新を取り込む
status: stable
tags: [meta, flow]
related:
  - META-01
  - META-07
---

# テンプレートの更新を取り込む

テンプレートから作ったプロジェクトに、あとからテンプレート側の改善を反映する手順を決める。**ファイルをコピーしない。** コピーすると、どれが共通ファイルかを毎回判断することになり、削除も伝わらず、いずれ気づかないうちにテンプレートとずれていく。

この文書は共通ファイルなので、取り込みで手順も一緒に更新される。`README.md`は`merge=ours`で、プロジェクトが書き換えたあとは取り込みが届かないため、手順を置かない。上に重ねた層のテンプレートも、この文書を指し、手順をREADMEに写さない。

## 共通ファイル

テンプレートから作ったリポジトリを、派生プロジェクトと呼ぶ。略して派生とも書く。上に重ねた層のテンプレートも、下の層から見れば派生プロジェクトである。

派生プロジェクトがテンプレートから取り込み、自分では書き換えないファイルを、共通ファイルと呼ぶ。共通ファイルの範囲は、この節で決める。ほかの文書は、範囲を写さずにこの節を指す。

| 共通ファイル | 共通ファイルではないもの |
| --- | --- |
| `tools/`、`tests/`、`docs/00-meta/`、`.claude/skills/`、`CLAUDE.md`、`TEMPLATE_CHANGELOG.md`、`Makefile`、`.github/`、`.gitattributes`、`.gitignore`、`LICENSE` | `.gitattributes`で`merge=ours`にしたファイル（`README.md`・各`index.md`など）、ノード本体、`.claude/CLAUDE.md` |

上の層のテンプレートから作ったなら、その層が足した共通ファイルも含める。どれを足したかは、その層のREADMEにある。

## 1. 最初に一度だけ

"Use this template"で作ったリポジトリは、テンプレートと履歴を共有していない。そのままマージすると、共通の祖先が無いので、共通ファイルまで軒並み競合する。先に共通ファイルをテンプレートと一致させ、競合するところを無くしてから繋ぐ。

1. 共通ファイル（上の「共通ファイル」）をテンプレートの内容で上書きして、コミットする。`README.md`・`docs/index.md`・各`index.md`・ノード本体は、プロジェクト固有なので対象外である

2. upstreamを追加する。URLは、作るときに使ったテンプレートのリポジトリにする。

   ```bash
   git remote add template https://github.com/setopic/graph-doc-template.git
   ```

3. 初回だけ、`--allow-unrelated-histories`を付けて取り込む。

   ```bash
   make update UPDATE_ARGS=--allow-unrelated-histories
   ```

   `make update`は、`.gitattributes`の`merge=ours`を有効にして取り込む。`merge=ours`のドライバは、この取り込みのときだけ有効にする。クローンに常設すると、作業ブランチどうしのマージでも`merge=ours`が使われ、相手の変更が気づかないうちに捨てられる。

4. 以前の`make setup`でドライバを常設したクローンなら、設定を外す。設定が無ければ何もしないので、何度実行してもよい。

   ```bash
   make setup
   ```

5. issueの型が使うラベルを作る（[META-07](issue-pr-flow.md)）。

   ```bash
   gh label clone setopic/graph-doc-template
   ```

   ラベルの実体が無いと、`labels:`の指定はエラーを出さずに無視される。issueは立つが、ラベルが付かないまま残る。`gh`の組み込みのコマンドで、すでにあるラベルは飛ばすので、何度実行してもよい。

## 2. 取り込む

まず、テンプレートとの差を調べる。このコマンドは読み取りだけで、何も書き込まない。

```bash
python -m tools.graph upgrade
```

テンプレートより遅れていれば、その間の変更履歴と、変更されるファイルの一覧が出る。**majorが上がっていれば、移行作業が要る。** マージしただけでは動かなくなるので、表示された移行手順を先に読む。

取り込みの手順は次のとおりである。

```bash
make update
```

`make update`は、マージコミットのメッセージを「テンプレートの<バージョン>を取り込む」にする。バージョンは`python -m tools.graph upgrade --label`が作り、遅れている層のバージョンを下の層から並べる（「3. テンプレートの層」）。競合したときも、解いたあとの`git commit`で同じメッセージが使われる。

```bash
python -m tools.graph reset-samples --yes
```

**取り込む側が、自分でもサンプルノードを配るテンプレートなら、`reset-samples`は回さない。** 配るはずのサンプルノードが消え、目次からも外れる。

```bash
python -m tools.graph check && python -m tools.graph sync
```

続けて、READMEの図を作り直す。`make update`は図を作り直さない。取り込みでノードやエッジが変わると、図が古いまま残り、CIの`readme-check`が落ちる。図を持つ`README.md`はふつうプロジェクトが書き換えてあるので、`merge=ours`でプロジェクト側が残り、テンプレート側の図は入らない。

```bash
make readme
```

`make all`は`check`・`sync`・`linkify`・`readme`をまとめて回すので、上の`check`・`sync`・`make readme`の代わりに使ってよい。

取り込むときに知っておくことは、次のとおりである。

| 知っておくこと | 説明 |
| --- | --- |
| サンプルノードは毎回追加される | マージは、テンプレート側にしかないファイルをそのまま足す。そのため、`reset-samples`で消すところまでが1セットである。省くと、プロジェクト側の同じidと衝突して`G002`が残る。サンプルノードを配るテンプレートは例外で、`reset-samples`を回さない |
| `README.md`と`docs/index.md`は競合しない | `make update`で取り込めば、`.gitattributes`の`merge=ours`で、プロジェクト側が優先される。ただし優先されるのは、プロジェクトが書き換えたファイルだけである（下の段落）。`git merge`を直接使うと`merge=ours`が使われず、競合する。テンプレート側の改善を取り込みたいときは、`git diff HEAD template/main -- README.md`で差分を見て、手で反映する |
| テンプレートがサンプルノードを変更したときだけ、modify/deleteの競合が出る | `git rm <path>`で解決してよい |
| 初回のマージだけ`--allow-unrelated-histories`が要る | GitHubの"Use this template"は、履歴を引き継がないため |

`merge=ours`のドライバが呼ばれるのは、マージの基点（前回取り込んだテンプレートのコミット）のあと、プロジェクトとテンプレートの両方がそのファイルを変えたときだけである。プロジェクトが基点のあと書き換えていないファイルには、ドライバは呼ばれず、テンプレート側の内容がそのまま入る。`merge=ours`は「テンプレートの変更を届けない」指定ではなく、「両方が変えたらプロジェクト側を残す」指定である。

そのため、変更履歴の「取り込む側の作業」に`merge=ours`のファイルの変更を書くときは、「届かない」と言い切らず、「プロジェクトが書き換えていれば届かない」と書く。上の層の変更履歴も同じである。言い切ると、書き換えていない派生が、取り込みでもう届いた内容を手で二重に足す。

## 3. テンプレートの層

テンプレートは層を重ねられる。下の層はもとになるテンプレート（このリポジトリ、`graph-doc-template`）で、上の層は下の層の上に重ねたテンプレートである。バージョンと変更履歴は層ごとにあり、`upgrade`は層ごとに比べる。

| 層 | バージョン | 変更履歴 | 取り込みのバージョンの書き方 |
| --- | --- | --- | --- |
| graph-doc-template | `tools/graph/version.py`の`TEMPLATE_VERSION` | `TEMPLATE_CHANGELOG.md` | `1.38.0` |
| 上の層 | `tools/graph/layers/<層の名前>.toml`の`version` | 同じファイルの`changelog`が指すもの | `<label>-<バージョン>`（`<label>-0.14.0`など） |

両方の層が遅れていれば、取り込みのバージョンは`1.38.0-<label>-0.14.0`になる。上の層を作るときは、`tools/graph/layers/<層の名前>.toml`を1つ置く。層ごとにファイルの名前が違うので、層を重ねても取り込みで競合しない。

```toml
name = "<層の名前>"
label = "<label>"
below = "graph-doc-template"
version = "0.14.0"
changelog = "<変更履歴のファイル>"
repository = "https://github.com/<owner>/<repo>.git"
```

`label`は、取り込みのバージョンで層を見分ける名前で、英小文字と数字で書く。`below`には1つ下の層の`name`を書く。リモート`template`が無いとき、`upgrade`はいちばん上の層の`repository`を案内する。

PRの題にバージョンを求めるときは、`versioned_title = true`を足す。書かなければ求めない。CIの`names`は、`repository`がPRのリポジトリと同じ層だけに当てるので、宣言が写った派生では求めない（[META-07](issue-pr-flow.md)）。

上の層が足す規約の文書は、下の層の規約の文書を`related`に入れない。`related`は相互に書く決まりなので、入れると下の層の共通ファイルを書き換えることになる。下の層の規約の文書へは、本文のリンクで案内する（[META-01](graph-rules.md)の「規約の文書には逆引きを書かない」）。

上の層は、下の層のサンプルノードを指すノードを足さない。サンプルノードの自動生成ブロックには、そのノードを参照しているノードが書かれる。上の層と下の層が同じサンプルノードを指すノードをそれぞれ足すと、このブロックが上の層の取り込みで競合する。

上の層のREADMEには、その層が足したもの（共通ファイル・サンプルノード・手順の例外）の説明と、この文書へのリンクだけを書く。取り込みの手順を写すと、写した側が古くなる。

## 4. 取り込みのPR

取り込みをPRにするときは、本文の「対応するノード」の節に、行の先頭から`なし`と書く（`- なし`のように箇条書きにしてもよい）。取り込みには対応するノードが無いからである。`gh pr create --body`で本文を渡すと、PRの雛形を通らず、この節が入らない。節が無いと、CIの`refs`が落ちる。

```markdown
## 対応するノード

なし（テンプレートの取り込みのみ）
```

取り込みのブランチ名は`chore/template-<バージョン>`にし（バージョンは`make update`のメッセージと同じもの）、PRの題は`chore: テンプレートの<バージョン>を取り込む`のように書く。CIの`names`が、ブランチ名とPRの題を確かめる（[META-07](issue-pr-flow.md)）。取り込みに入る上流のコミットは確かめない。

取り込みのPRは、squashではなくマージコミットでマージする（`gh pr merge --merge`）。squashすると、上流のコミットとの親子関係が消え、次の`make update`の基点が古いままになる。[META-07](issue-pr-flow.md)の「ブランチ名とコミットの1行目」も、派生がマージコミットで本体のコミットを取り込むことを前提にしている。マージコミットの1行目はGitHubの既定の「Merge pull request #N ...」になるが、CIの`names`はマージコミットを確かめないので、直さなくてよい。

`merge=ours`のファイルに手で反映するものは、取り込みのPRとは別のPRにする（[META-07](issue-pr-flow.md)の「1つのPRには、1つの変更だけを入れる」）。

---

<!-- graph:auto:start -->

## 関連ドキュメント（自動生成 / 手で編集しない）

`related`: 依存はしないが、一緒に読むべきノード

- [META-01 グラフの規約](./graph-rules.md)
- [META-07 issueとPRの流れ](./issue-pr-flow.md)

<!-- graph:auto:end -->
