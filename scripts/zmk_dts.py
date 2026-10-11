"""双掌 (sosho) の devicetree とキーマップを、ツールチェーン無しで読むための部品。

lint-keymap.py と gen-docs.py が共有する。本物の DTS パーサではなく、
このリポジトリのファイルが使っている書き方だけを、括弧の対応を数えながら読む。
"""
from __future__ import annotations

import re
from typing import Callable, Iterator, Optional

# 形の崩れを見つけたときに呼ぶ関数。lint は自分のエラー一覧に積み、資料生成は None（黙って読み飛ばす）。
Err = Optional[Callable[[str], None]]


def _report(err: Err, msg: str) -> None:
    if err is not None:
        err(msg)


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


# ------------------------------------------------------------------ ノード


def find_node(text: str, name: str) -> str | None:
    """`name { ... }`（`label: name {` も可）を探して中身を返す。

    overlay の `&label { ... }` も、name に `&label` を渡せば探せる。
    """
    for m in re.finditer(r"(?:^|[\s;{}])" + re.escape(name) + r"\s*\{", text):
        return match_brace(text, text.index("{", m.start()))[0]
    return None


def find_labeled(text: str, label: str) -> str | None:
    """`label: ノード名 { ... }` の形で定義されたノードを探して中身を返す。"""
    for m in re.finditer(r"(?:^|[\s;{}])" + re.escape(label) + r"\s*:\s*[\w@,.-]+\s*\{", text):
        return match_brace(text, text.index("{", m.start()))[0]
    return None


def child_nodes(body: str, err: Err = None) -> Iterator[tuple[str, str]]:
    """直下の子ノードを (名前, 中身) で宣言順に返す。

    素朴な正規表現だと `combos` / `keymap` 自身をレイヤーと誤認するため、
    波括弧の対応を数えながら走査する。`label: name {` の形では label を返す。
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
            _report(err, "波括弧が対応していません: %r 付近" % body[m.start() : m.start() + 40])
            return
        yield m.group(1), child
        i = end


def labeled_nodes(body: str) -> Iterator[tuple[str | None, str, str]]:
    """直下の子ノードを (ラベル, ノード名, 中身) で宣言順に返す。ラベルが無ければ None。"""
    i = 0
    pat = re.compile(r"(?:([A-Za-z_][\w-]*)\s*:\s*)?([A-Za-z_][\w@,.-]*)\s*\{")
    while True:
        m = pat.search(body, i)
        if not m:
            return
        child, end = match_brace(body, body.index("{", m.start()))
        if child is None or end is None:
            return
        yield m.group(1), m.group(2), child
        i = end


# ------------------------------------------------------------------ プロパティ


def prop_cells(body: str, prop: str, err: Err = None) -> list[str]:
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
                        _report(
                            err,
                            "`%s` (%d 行目) が `>;` で終わっていません" % (prop, line_of(body, m.start())),
                        )
                    out.append(body[start + 1 : i])
                    break
        else:
            _report(err, "`%s` (%d 行目) の `>` がありません" % (prop, line_of(body, m.start())))
    return out


def prop_raw(body: str, prop: str) -> str | None:
    """`prop = 値;` の値の部分を、書かれたままの文字列で返す（最初の 1 つ）。

    `<a>, <b>` のような複数の値もまとめて返す。山括弧・丸括弧・引用符の中の `;` では切らない。
    """
    m = re.search(r"(?<![\w-])" + re.escape(prop) + r"\s*=", body)
    if not m:
        return None
    depth, quoted = 0, False
    for i in range(m.end(), len(body)):
        c = body[i]
        if c == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif c in "<(":
            depth += 1
        elif c in ">)":
            depth -= 1
        elif c == ";" and depth == 0:
            return body[m.end() : i].strip()
    return None


def prop_int(body: str, prop: str) -> int | None:
    raw = prop_raw(body, prop)
    m = re.search(r"\b\d+\b", raw or "")
    return int(m.group(0)) if m else None


def prop_str(body: str, prop: str) -> str | None:
    m = re.search(r'"([^"]*)"', prop_raw(body, prop) or "")
    return m.group(1) if m else None


def prop_bool(body: str, prop: str) -> bool:
    """`invert-x;` のような値を持たないプロパティがあるか。"""
    return re.search(r"(?<![\w-])" + re.escape(prop) + r"\s*;", body) is not None


def gpios(raw: str | None) -> list[tuple[int, int]]:
    """`<&gpio0 2 (...)>, <&gpio1 11 ...>` を [(0, 2), (1, 11)] にする。"""
    return [(int(p), int(n)) for p, n in re.findall(r"&gpio(\d)\s+(\d+)", raw or "")]


def psels(raw: str | None) -> list[tuple[str, int, int]]:
    """`<NRF_PSEL(SPIM_SCK, 1, 13)>, ...` を [("SPIM_SCK", 1, 13), ...] にする。"""
    return [(f, int(p), int(n)) for f, p, n in re.findall(r"NRF_PSEL\((\w+),\s*(\d+),\s*(\d+)\)", raw or "")]


def defines(text: str) -> dict[str, str]:
    """`#define 名前 値` を集める（コメントは除いて渡すこと）。"""
    return dict(re.findall(r"^\s*#define\s+(\w+)\s+(.+?)\s*$", text, re.M))


# ------------------------------------------------------------------ バインディング


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
