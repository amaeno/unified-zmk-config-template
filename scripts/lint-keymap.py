#!/usr/bin/env python3
"""双掌 (sosho) のキーマップをツールチェーン無しで検査する。

    python3 scripts/lint-keymap.py [--keys N] [--sensors N]

終了コード 0 = 問題なし、1 = エラーあり。数十 ms で終わるので、
Docker ビルドを回す前の一次チェックとして使う。

期待キー数は 44 をハードコードせず、物理レイアウト (sosho-layouts.dtsi) と
マトリクス変換 (sosho.dtsi) から導出する。3 者が食い違えばそれ自体がエラー
（キーマップとマトリクスの乖離は、ビルドは通るのに無反応キーができる)。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from zmk_dts import (
    behaviors,
    child_nodes,
    find_node,
    groups,
    line_of,
    prop_cells,
    strip_comments,
    strip_preprocessor,
)

REPO = Path(__file__).resolve().parent.parent
KEYMAP = REPO / "config" / "sosho.keymap"
LAYOUTS = REPO / "boards" / "shields" / "sosho" / "sosho-layouts.dtsi"
SHIELD = REPO / "boards" / "shields" / "sosho" / "sosho.dtsi"

ERRORS: list[str] = []
WARNS: list[str] = []


def err(m: str) -> None:
    ERRORS.append(m)


def warn(m: str) -> None:
    WARNS.append(m)


# ------------------------------------------------------------------ 期待値


def expected_keys(override: int | None) -> int:
    if override:
        return override
    counts: dict[str, int] = {}
    if LAYOUTS.exists():
        n = len(re.findall(r"&key_physical_attrs", strip_comments(LAYOUTS.read_text("utf-8"))))
        if n:
            counts["物理レイアウト"] = n
    if SHIELD.exists():
        m = re.search(r"map\s*=\s*<(.*?)>", strip_comments(SHIELD.read_text("utf-8")), re.S)
        if m:
            n = len(re.findall(r"RC\(", m.group(1)))
            if n:
                counts["マトリクス変換"] = n
    if not counts:
        err("キー数を導出できません。--keys N を指定してください")
        return 0
    if len(set(counts.values())) > 1:
        err("シールド定義でキー数が食い違っています: %s" % counts)
    return max(counts.values())


def expected_sensors(override: int | None) -> int:
    if override is not None:
        return override
    if not SHIELD.exists():
        return 0
    m = re.search(r"sensors\s*=\s*<([^>]*)>", strip_comments(SHIELD.read_text("utf-8")))
    return len(re.findall(r"&\w+", m.group(1))) if m else 0


# ------------------------------------------------------------------ 本体


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", type=int, help="1 レイヤーあたりの期待キー数を明示指定")
    ap.add_argument("--sensors", type=int, help="期待センサ数を明示指定")
    args = ap.parse_args()

    src = strip_comments(KEYMAP.read_text("utf-8"))
    n_keys = expected_keys(args.keys)
    n_sens = expected_sensors(args.sensors)

    # 1. 括弧の対応
    body = strip_preprocessor(src)
    for op, cl, what in (("{", "}", "波括弧"), ("<", ">", "山括弧"), ("(", ")", "丸括弧")):
        a, b = body.count(op), body.count(cl)
        if a != b:
            err("%sが対応していません: `%s` %d 個 vs `%s` %d 個" % (what, op, a, cl, b))

    # 2. レイヤー
    km = find_node(src, "keymap")
    if km is None:
        err("`keymap { ... }` ノードが見つかりません")
        return report()

    layers = list(child_nodes(km, err))
    if not layers:
        err("`keymap` ノードにレイヤーがありません")

    seen_reserved = False
    for idx, (name, lbody) in enumerate(layers):
        reserved = re.search(r'status\s*=\s*"reserved"', lbody) is not None
        cells = prop_cells(lbody, "bindings", err)

        if reserved:
            seen_reserved = True
            if cells:
                err("レイヤー %d `%s` は reserved なのに bindings を持っています" % (idx, name))
            continue
        if seen_reserved:
            warn(
                "レイヤー %d `%s` が reserved レイヤーより後ろにあります"
                "（ZMK Studio は reserved を末尾に置く前提）" % (idx, name)
            )
        if not cells:
            err("レイヤー %d `%s` に `bindings` がありません" % (idx, name))
            continue
        if len(cells) > 1:
            err("レイヤー %d `%s` が `bindings` を複数回宣言しています" % (idx, name))

        got = len(behaviors(cells[0]))
        if got != n_keys:
            err("レイヤー %d `%s`: bindings が %d 個、期待は %d 個" % (idx, name, got, n_keys))

        for payload in prop_cells(lbody, "sensor-bindings", err):
            gs = groups(payload)
            if n_sens and len(gs) != n_sens:
                err(
                    "レイヤー %d `%s`: sensor-bindings が %d 個、期待は %d 個"
                    % (idx, name, len(gs), n_sens)
                )
            for g in gs:
                if len(g) - 1 != 2:
                    err(
                        "レイヤー %d `%s`: sensor-binding `%s` の引数が %d 個、"
                        "期待は 2 個 (#sensor-binding-cells)" % (idx, name, g[0], len(g) - 1)
                    )

    n_layers = len(layers)

    # 3. レイヤー参照が存在するか
    for m in re.finditer(r"&(mo|to|tog|sl|df|lt)\s+(\d+)", src):
        n = int(m.group(2))
        if n >= n_layers:
            err(
                "%d 行目: `&%s %d` は存在しないレイヤーを参照しています"
                "（レイヤーは %d 個、0〜%d）"
                % (line_of(src, m.start()), m.group(1), n, n_layers, n_layers - 1)
            )

    # 4. コンボ
    combos = find_node(src, "combos")
    if combos:
        for name, cbody in child_nodes(combos, err):
            pos_cells = prop_cells(cbody, "key-positions", err)
            if not pos_cells:
                err("コンボ `%s` に `key-positions` がありません" % name)
                continue
            try:
                pos = [int(x) for x in pos_cells[0].split()]
            except ValueError:
                err("コンボ `%s`: key-positions が数値ではありません %r" % (name, pos_cells[0]))
                continue
            if len(pos) < 2:
                err("コンボ `%s` には key-positions が 2 個以上必要です" % name)
            if len(set(pos)) != len(pos):
                err("コンボ `%s` の key-positions に重複があります %s" % (name, pos))
            for p in pos:
                if not 0 <= p < n_keys:
                    err(
                        "コンボ `%s`: key-position %d が範囲外です（0〜%d）"
                        % (name, p, n_keys - 1)
                    )
            cb = prop_cells(cbody, "bindings", err)
            if not cb:
                err("コンボ `%s` に `bindings` がありません" % name)
            elif len(behaviors(cb[0])) != 1:
                err(
                    "コンボ `%s` の bindings は behavior 1 個である必要があります（%d 個）"
                    % (name, len(behaviors(cb[0])))
                )
            if "timeout-ms" not in cbody:
                warn("コンボ `%s` に timeout-ms がありません（ZMK の既定値が使われます）" % name)

    return report(n_keys, n_sens, n_layers)


def report(n_keys=None, n_sens=None, n_layers=None) -> int:
    for w in WARNS:
        print("warn:  %s" % w)
    for e in ERRORS:
        print("ERROR: %s" % e)
    if ERRORS:
        print("\n%s に %d 件のエラー" % (KEYMAP.relative_to(REPO), len(ERRORS)))
        return 1
    print(
        "ok: %s  (レイヤー %s / 1 レイヤー %s キー / センサ %s)%s"
        % (
            KEYMAP.relative_to(REPO),
            n_layers,
            n_keys,
            n_sens,
            "  [警告 %d 件]" % len(WARNS) if WARNS else "",
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
