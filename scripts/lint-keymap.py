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


# ------------------------------------------------------------------ 字句処理


def strip_comments(text: str) -> str:
    """コメントを空白で潰す。行番号とオフセットは保つ。"""

    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    return re.sub(r"//[^\n]*", blank, text)


def strip_preprocessor(text: str) -> str:
    """#include <...> の山括弧が対応チェックを汚すので、# 行を落とす。"""
    return "\n".join("" if l.lstrip().startswith("#") else l for l in text.split("\n"))


def line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def match_brace(text: str, open_idx: int) -> tuple[str | None, int | None]:
    """text[open_idx] == '{' のとき (中身, 閉じ括弧の次の位置) を返す。"""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], i + 1
    return None, None


def find_node(text: str, name: str) -> str | None:
    """`name { ... }`（`label: name {` も可）を探して中身を返す。"""
    for m in re.finditer(r"(?:^|[\s;{}])" + re.escape(name) + r"\s*\{", text):
        return match_brace(text, text.index("{", m.start()))[0]
    return None


def child_nodes(body: str):
    """直下の子ノードを (名前, 中身) で宣言順に返す。

    素朴な正規表現だと `combos` / `keymap` 自身をレイヤーと誤認するため、
    波括弧の対応を数えながら走査する。
    """
    i = 0
    pat = re.compile(r"([A-Za-z_][\w-]*)\s*(?::\s*[A-Za-z_][\w-]*\s*)?\{")
    while True:
        m = pat.search(body, i)
        if not m:
            return
        open_idx = body.index("{", m.start())
        child, end = match_brace(body, open_idx)
        if child is None or end is None:
            err("波括弧が対応していません: %r 付近" % body[m.start() : m.start() + 40])
            return
        yield m.group(1), child
        i = end


def prop_cells(body: str, prop: str) -> list[str]:
    """`prop = < ... >;` の中身を、出現順にすべて返す。

    プロパティ名は完全一致させる。前方の境界を見ないと
    `bindings` が `sensor-bindings` にも当たってしまう。
    """
    out: list[str] = []
    for m in re.finditer(r"(?<![\w-])" + re.escape(prop) + r"\s*=\s*<", body):
        start = body.index("<", m.start())
        depth = 0
        for i in range(start, len(body)):
            if body[i] == "<":
                depth += 1
            elif body[i] == ">":
                depth -= 1
                if depth == 0:
                    if not body[i + 1 :].lstrip().startswith(";"):
                        err(
                            "`%s` (%d 行目) が `>;` で終わっていません"
                            % (prop, line_of(body, m.start()))
                        )
                    out.append(body[start + 1 : i])
                    break
        else:
            err("`%s` (%d 行目) の `>` がありません" % (prop, line_of(body, m.start())))
    return out


def behaviors(payload: str) -> list[str]:
    return re.findall(r"&[A-Za-z_]\w*", payload)


def groups(payload: str) -> list[list[str]]:
    """`&a X Y &b Z` を [['&a','X','Y'], ['&b','Z']] に割る。"""
    out: list[list[str]] = []
    cur: list[str] | None = None
    for tok in payload.split():
        if tok.startswith("&"):
            cur = [tok]
            out.append(cur)
        elif cur is not None:
            cur.append(tok)
    return out


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

    layers = list(child_nodes(km))
    if not layers:
        err("`keymap` ノードにレイヤーがありません")

    seen_reserved = False
    for idx, (name, lbody) in enumerate(layers):
        reserved = re.search(r'status\s*=\s*"reserved"', lbody) is not None
        cells = prop_cells(lbody, "bindings")

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

        for payload in prop_cells(lbody, "sensor-bindings"):
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
        for name, cbody in child_nodes(combos):
            pos_cells = prop_cells(cbody, "key-positions")
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
            cb = prop_cells(cbody, "bindings")
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
