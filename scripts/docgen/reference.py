"""ZMK の調査用コピー（.zmk-ref/）から作るもの: 使っている版、behavior の一覧。

.zmk-ref/ は git 管理外なので、無い環境では SourceMissing を投げて前の内容を残す。
作り直すには `./scripts/build-local.sh --ref`。
"""
from __future__ import annotations

import re

import zmk_dts as dts

from .build import PROJECT_NOTES
from .common import (
    KEYMAP,
    REPO,
    WEST_YML,
    Page,
    SourceMissing,
    badge,
    code,
    esc,
    generator,
    table,
    yaml_items,
)
from .keymap import combos, keymap_src, layers

REF = REPO / ".zmk-ref"
VERSIONS = REF / "VERSIONS.txt"
REF_NOTE = "<code>.zmk-ref/</code>（<code>./scripts/build-local.sh --ref</code> で作る）"

# west.yml に無いが、資料に載せたいプロジェクト（ZMK 本体の west.yml から入るもの）
EXTRA_PROJECTS = {
    "zephyr": ("https://github.com/zmkfirmware/zephyr", "RTOS（ZMK 向けの修正入りのフォーク）"),
}


def versions() -> dict[str, tuple[str, str]]:
    """VERSIONS.txt を {名前: (revision, コミット)} にする。"""
    if not VERSIONS.exists():
        raise SourceMissing(".zmk-ref/VERSIONS.txt が無い")
    out = {}
    for line in VERSIONS.read_text("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith("#"):
            out[parts[0]] = (parts[1], parts[2])
    return out


@generator("zmk-versions")
def gen_zmk_versions(page: Page, args: dict[str, str]) -> str:
    vs = versions()
    remotes = {r.get("name", ""): r.get("url-base", "") for r in yaml_items(WEST_YML, "remotes")}
    projects = [
        (p.get("name", ""), "%s/%s" % (remotes.get(p.get("remote", ""), "").rstrip("/"), p.get("name", "")), PROJECT_NOTES.get(p.get("name", ""), "—"))
        for p in yaml_items(WEST_YML, "projects")
    ]
    projects.insert(1, ("zephyr", *EXTRA_PROJECTS["zephyr"]))
    rows = []
    for name, url, note in projects:
        if name not in vs:
            continue
        rev, sha = vs[name]
        rows.append(
            [
                '<a href="%s">%s</a>' % (esc(url), esc(name)),
                badge("コミットで固定", "ok") if rev == sha else code(rev),
                '<a href="%s/commit/%s">%s</a>' % (esc(url), esc(sha), code(sha[:7])),
                note,
            ]
        )
    rest = len(vs) - len(rows)
    out = table(["プロジェクト", "revision", "使っているコミット", "用途"], rows, REF_NOTE + " の <code>VERSIONS.txt</code>")
    return out + "\n<p>ほかに %d 個のプロジェクト（Nordic の HAL など）を取り込んでいます。全部の版は <code>.zmk-ref/VERSIONS.txt</code> にあります。</p>" % rest


@generator("zmk-commit")
def gen_zmk_commit(page: Page, args: dict[str, str]) -> str:
    """本文に埋め込む、いま使っている ZMK 本体のコミット（先頭 7 桁）。"""
    rev, sha = versions().get("zmk", ("", ""))
    if not sha:
        raise SourceMissing("VERSIONS.txt に zmk が無い")
    return code(sha[:7])


def behavior_defs() -> list[tuple[str, str, str]]:
    """ZMK 本体と外部モジュールが定義している behavior を (ラベル, compatible, 定義ファイル) で返す。"""
    files = sorted(REF.glob("zmk-app/dts/behaviors/*.dtsi")) + sorted(REF.glob("*/dts/behaviors/*.dtsi"))
    files = [f for i, f in enumerate(files) if f not in files[:i]]  # 重複を除く
    if not files:
        raise SourceMissing(".zmk-ref/ に behavior の定義が無い")
    out = []
    for f in files:
        src = dts.strip_comments(f.read_text("utf-8"))
        for m in re.finditer(r"([A-Za-z_]\w*)\s*:\s*[\w@,.-]+\s*\{", src):
            body, _ = dts.match_brace(src, src.index("{", m.start()))
            compat = dts.prop_str(body or "", "compatible") or ""
            if compat.startswith("zmk,behavior"):
                out.append((m.group(1), compat, f.relative_to(REF).as_posix()))
    return out


def usage_counts() -> dict[str, int]:
    """キーマップのファイル（各レイヤー・エンコーダ・コンボ）で、各 behavior を何回使っているか。"""
    counts: dict[str, int] = {}
    groups = [g for l in layers() for g in l.keys + (l.sensors or [])] + [c.binding for c in combos()]
    for g in groups:
        if g:
            counts[g[0][1:]] = counts.get(g[0][1:], 0) + 1
    return counts


@generator("zmk-behaviors")
def gen_zmk_behaviors(page: Page, args: dict[str, str]) -> str:
    defs = behavior_defs()
    counts = usage_counts()
    own = [
        (label, dts.prop_str(body, "compatible") or "", "config/sosho.keymap")
        for label, _, body in dts.labeled_nodes(dts.find_node(keymap_src(), "behaviors") or "")
        if label
    ]
    rows, classes = [], []
    for label, compat, where in sorted(own + defs, key=lambda d: (-counts.get(d[0], 0), d[0])):
        n = counts.get(label, 0)
        rows.append([code("&" + label), code(compat), "%d 回" % n if n else "—", code(where)])
        classes.append("" if n else "dim")
    return table(
        ["ラベル", "compatible", "ファイルでの使用", "定義"],
        rows,
        "%s と %s（使用回数はファイルの初期値で数える）" % (REF_NOTE, code(KEYMAP.relative_to(REPO).as_posix())),
        classes,
    )
