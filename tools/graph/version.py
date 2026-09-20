"""テンプレートの版。

派生プロジェクトはこのファイルを共有しているため、`git merge template/main` を
すると自動的に更新される。マージ前は自分の版、マージ後はテンプレートの版になる。

**`schema.py` には置かない。** あちらはプロジェクトが語彙を調整するために
書き換える前提のファイルで、版を混ぜるとマージのたびに競合する。

変更内容と移行手順は TEMPLATE_CHANGELOG.md にある。
"""

from __future__ import annotations

TEMPLATE_VERSION = "1.18.0"

# 動作を保証する Python の下限。**動かしている場所すべてが 3.12 に揃っている。**
# 開発機・CI・本番ホスト（deadsnakes の python3.12 で作った venv）のいずれもで、
# 幅を持たせる理由が無くなったので、実際に回している版をそのまま下限にする。
#
# **これより古い版は誰も試していない。** 3.11 で動くかは分からない、が正しい。
# 上げるときは 3 つを揃える。ずれたら test_python_floor が落ちる。
#   1. この定数
#   2. .github/workflows/graph-check.yml の python-version
#   3. README の「必要なもの」
MIN_PYTHON = "3.12"
