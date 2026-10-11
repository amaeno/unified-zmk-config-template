#!/usr/bin/env python3
"""双掌 (sosho) のキーマップをツールチェーン無しで検査する。

    python3 scripts/lint-keymap.py [--keys N] [--sensors N]

終了コード 0 = 問題なし、1 = エラーあり。1 秒かからず終わるので、
Docker ビルドを回す前の一次チェックとして使う。

期待キー数は 44 をハードコードせず、物理レイアウト (sosho-layouts.dtsi) と
マトリクス変換 (sosho.dtsi) から導出する。3 者が食い違えばそれ自体がエラー
（キーマップとマトリクスの乖離は、ビルドは通るのに無反応キーができる)。

キーマップと overlay が参照するラベル（&kp や &zip_* など）は、ZMK 本体・外部モジュールの
調査用コピー（.zmk-ref/）とこのリポジトリの定義に照らし、見つからなければ警告する。
.zmk-ref/ が無ければこの確認は飛ばす（scripts/build-local.sh --ref で作れる）。
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
SHIELD_DIR = REPO / "boards" / "shields" / "sosho"
LAYOUTS = SHIELD_DIR / "sosho-layouts.dtsi"
SHIELD = SHIELD_DIR / "sosho.dtsi"
REF = REPO / ".zmk-ref"

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

    # 5. 参照しているラベルが実在するか（存在しないラベルは、今はビルドするまで気づけない）
    if REF.is_dir():
        known = defined_labels()
        for label, where in referenced_labels(src):
            if label not in known:
                warn(
                    "`&%s`（%s）の定義が、ZMK・モジュール（.zmk-ref/）にもこのリポジトリにも見つかりません"
                    % (label, where)
                )

    return report(n_keys, n_sens, n_layers)


def defined_labels() -> set[str]:
    """`label: node {` の形で定義されたラベル。ZMK 本体・外部モジュールとこのリポジトリから集める。"""
    files = list(REF.rglob("*.dtsi")) + list(SHIELD_DIR.glob("*.dtsi")) + list(SHIELD_DIR.glob("*.overlay")) + [KEYMAP]
    labels: set[str] = set()
    for p in files:
        try:
            text = strip_comments(p.read_text("utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        labels.update(re.findall(r"([A-Za-z_]\w*)\s*:\s*[\w@,.-]+\s*\{", text))
    return labels


def referenced_labels(keymap_src: str) -> list[tuple[str, str]]:
    """キーマップのバインディングと overlay の input-processors が参照するラベルを (ラベル, 場所) で返す。"""
    out: list[tuple[str, str]] = []
    for prop in ("bindings", "sensor-bindings"):
        for payload in prop_cells(keymap_src, prop):
            out += [(b[1:], "キーマップの %s" % prop) for b in behaviors(payload)]
    for p in sorted(SHIELD_DIR.glob("*.overlay")):
        text = strip_comments(p.read_text("utf-8"))
        for m in re.finditer(r"(?<![\w-])input-processors\s*=\s*([^;]+);", text):
            out += [(l, "%s の input-processors" % p.name) for l in re.findall(r"&(\w+)", m.group(1))]
    return sorted(set(out))


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
