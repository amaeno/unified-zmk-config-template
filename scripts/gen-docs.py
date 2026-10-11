#!/usr/bin/env python3
"""docs/*.html の自動生成ブロックを、リポジトリ内の元ファイルから作り直す。

    python3 scripts/gen-docs.py           生成ブロックを更新する
    python3 scripts/gen-docs.py --check   更新が要るファイルを列挙する（要るなら終了コード 1）

HTML の中の次の囲みだけを書き換える。囲みの外の手書き部分には触らない。

    <!-- gen:名前 キー=値 ... -->
    （ここはスクリプトが上書きする）
    <!-- /gen:名前 -->

build.yaml やキーマップのように繰り返し変わる事実を、手で二重管理しないための仕組み。
資料に新しい事実を載せるときは、手で書く前に生成器を足せないか考える。
生成器はテーマごとに scripts/docgen/ に分けてある（一覧は docgen/__init__.py）。
あわせて、資料の検索索引 docs/assets/search-index.js も作り直す。
git の履歴から作るもの（変更履歴）は --check では比べない。元が git 管理外で手元に無いもの
（.zmk-ref/ から作るもの）は、前の内容のまま残す。
ホストの python3 標準ライブラリだけで動く（PyYAML も使わない）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docgen import DOCS, GENERATORS, VOLATILE, Page, SourceMissing, build_index, rel

BLOCK = re.compile(
    r"(?P<open><!--\s*gen:(?P<name>[\w-]+)(?P<args>[^>]*?)\s*-->)"
    r".*?"
    r"(?P<close><!--\s*/gen:(?P=name)\s*-->)",
    re.S,
)
SEARCH_INDEX = DOCS / "assets" / "search-index.js"


def render(path: Path, text: str, errors: list[str], notes: list[str], check: bool = False) -> str:
    opens = len(re.findall(r"<!--\s*gen:", text))
    closes = len(re.findall(r"<!--\s*/gen:", text))
    if opens != closes:
        errors.append("%s: gen の開始 %d 個と終了 %d 個が対応していません" % (rel(path), opens, closes))
        return text
    page = Page(path, text)

    def sub(m: re.Match[str]) -> str:
        name = m.group("name")
        fn = GENERATORS.get(name)
        if fn is None:
            errors.append("%s: 未知の生成ブロック gen:%s" % (rel(path), name))
            return m.group(0)
        if check and name in VOLATILE:
            return m.group(0)  # git の履歴など、作るたびに変わりうるものは比べない
        args = dict(a.split("=", 1) for a in m.group("args").split() if "=" in a)
        try:
            body = fn(page, args)
        except SourceMissing as e:
            notes.append("%s: gen:%s は前の内容のまま（%s）" % (rel(path), name, e))
            return m.group(0)
        except (OSError, ValueError, IndexError, KeyError) as e:
            errors.append("%s: gen:%s %s を作れません: %s" % (rel(path), name, m.group("args").strip(), e))
            return m.group(0)
        return "%s\n%s\n%s" % (m.group("open"), body.strip("\n"), m.group("close"))

    return BLOCK.sub(sub, text)


def main() -> int:
    ap = argparse.ArgumentParser(description="docs/*.html の自動生成ブロックを更新する")
    ap.add_argument("--check", action="store_true", help="書き換えずに、更新が要るかだけを調べる")
    args = ap.parse_args()

    errors: list[str] = []
    notes: list[str] = []
    stale: list[Path] = []
    texts: dict[Path, str] = {}
    n_blocks = 0
    for path in sorted(DOCS.glob("*.html")):
        old = path.read_text("utf-8")
        n_blocks += len(BLOCK.findall(old))
        new = texts[path] = render(path, old, errors, notes, args.check)
        if new != old:
            stale.append(path)
            if not args.check:
                path.write_text(new, "utf-8")

    # 検索の索引は、生成し終えたページの文章から作る
    index = build_index(texts)
    if not SEARCH_INDEX.exists() or SEARCH_INDEX.read_text("utf-8") != index:
        stale.append(SEARCH_INDEX)
        if not args.check:
            SEARCH_INDEX.write_text(index, "utf-8")

    for n in notes:
        print("note:  %s" % n)
    for e in errors:
        print("ERROR: %s" % e)
    if errors:
        return 1
    if args.check:
        for p in stale:
            print("要更新: %s" % rel(p))
        if stale:
            print("\npython3 scripts/gen-docs.py を実行してください")
            return 1
        print("ok: docs/ の生成ブロック %d 個はすべて最新" % n_blocks)
        return 0
    for p in stale:
        print("更新: %s" % rel(p))
    print("ok: docs/ の生成ブロック %d 個（更新 %d ファイル）" % (n_blocks, len(stale)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
