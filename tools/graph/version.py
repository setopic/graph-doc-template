"""テンプレートの版。

派生プロジェクトはこのファイルを共有しているため、`git merge template/main` を
すると自動的に更新される。マージ前は自分の版、マージ後はテンプレートの版になる。

**`schema.py` には置かない。** あちらはプロジェクトが語彙を調整するために
書き換える前提のファイルで、版を混ぜるとマージのたびに競合する。

変更内容と移行手順は TEMPLATE_CHANGELOG.md にある。
"""

from __future__ import annotations

TEMPLATE_VERSION = "1.3.0"
