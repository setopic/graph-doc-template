# tools/graphを直すとき

`tools/graph/`と`tests/`を直すときの決まりである。テンプレート本体（`graph-doc-template`）で直す。派生プロジェクトでは直さず、テンプレート側に入れてから`make update`で取り込む。

語彙（ノード種別・エッジ種別・層）は`tools/graph/schema.py`に集めてある。ここを変えたら、`docs/00-meta/node-types.md`の表も必ず合わせる。

検証ルールは`tools/graph/rules.py`に、1ルール1関数で並んでいる。ルールを足したら、`RULE_INDEX`と`graph-rules.md`の一覧の両方に追記する。テストも足し、`tests/`に`unittest`で置く。`python -m unittest discover -s tests -t .`が、CIで最初に回るテストである。テストどうしの読み込みは`from tests.helpers import make_graph`のように`tests.`から書く。`from .helpers`と書くと、`-t .`を付けずに回したときに読み込みで落ちる。

外部依存を足さない。標準ライブラリだけで動くことが、このツールの前提である。`check`はオフラインで完結させる。通信するのは`review`だけで、`review`はCIから呼ばず、終了コードも常に0である（`docs/00-meta/ai-review.md`）。

テキストを書き出すときは、必ず`encoding="utf-8"`と`newline="\n"`を渡す。**既定に任せると、Windowsでだけ改行がCRLFに、文字コードがcp932になる。** gitが改行を正規化するので、`git status`にも出ない。`test_newline_discipline`が構文木を調べて、渡し忘れを見つける。

動作を保証するPythonの下限は、`version.py`の`MIN_PYTHON`である。開発機・CI・本番で実際に回しているバージョンで、願望ではない。下限を動かすなら、CIの`python-version`とREADMEも同時に直す。ずれると`test_python_floor`が落ちる。
