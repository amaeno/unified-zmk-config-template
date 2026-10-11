"""ビルドまわり: build.yaml のターゲット、build-local.sh のコマンド、west.yml のモジュール。"""
from __future__ import annotations

import re

from .common import (
    BUILD_SH,
    BUILD_YAML,
    SHIELD_DIR,
    WEST_YML,
    Page,
    badge,
    code,
    esc,
    generator,
    my_targets,
    read,
    rel,
    table,
    yaml_items,
)

# config/west.yml の各プロジェクトの用途。west.yml には書く場所が無いのでここで持つ。
# 値は HTML としてそのまま埋め込む。
PROJECT_NOTES = {
    "zmk": "ZMK 本体",
    "zmk-rgbled-widget": "RGB LED による状態表示（電池残量・接続状態）",
    "zmk-pmw3610-driver": "トラックボール (PMW3610) のドライバ",
    "zmk_encoder": "エンコーダでのスクロール（<code>zmk,behavior-encoder-mouse-scroll</code>）",
}


def west_default_revision() -> str:
    m = re.search(r"^\s*defaults:\s*\n\s+revision:\s*(\S+)", read(WEST_YML), re.M)
    return m.group(1) if m else ""


@generator("build-targets")
def gen_build_targets(page: Page, args: dict[str, str]) -> str:
    mine = my_targets()
    rows, classes = [], []
    for e in yaml_items(BUILD_YAML, "include"):
        shield = e.get("shield", "")
        first = shield.split()[0] if shield else ""
        name = e.get("artifact-name") or first
        conf = SHIELD_DIR / (first + ".conf")
        studio = "ZMK_STUDIO=y" in e.get("cmake-args", "") or (
            conf.exists() and re.search(r"^CONFIG_ZMK_STUDIO=y", read(conf), re.M)
        )
        if "_R_" in first:
            side, role = "右", "セントラル"
        elif "_L_" in first:
            side, role = "左", "ペリフェラル"
        elif first == "settings_reset":
            side, role = "左右とも", "設定の消去"
        else:
            side, role = "—", "—"
        if "trackpad" in first:
            pointer = "トラックパッド (Cirque)"
        elif "trackball" in first:
            pointer = "トラックボール (PMW3610)"
        else:
            pointer = "—"
        used = name in mine
        rows.append([code(name) + (" " + badge("この機体", "ok") if used else ""), side, role, pointer, "有効" if studio else "—"])
        classes.append("" if used or name == "settings_reset" else "dim")
    return table(["ターゲット", "書き込む側", "役割", "ポインタ", "Studio"], rows, code(rel(BUILD_YAML)), classes)


@generator("build-commands")
def gen_build_commands(page: Page, args: dict[str, str]) -> str:
    rows = []
    for line in read(BUILD_SH).splitlines()[1:]:
        if not line.startswith("#"):
            break
        m = re.match(r"#\s+(scripts/build-local\.sh.*)$", line)
        if not m:
            continue
        # 説明との区切りは「2 つ以上の空白」か「空白 + 日本語」
        parts = re.split(r"\s{2,}| (?=[^\x00-\x7f])", m.group(1).strip(), maxsplit=1)
        if len(parts) == 2:
            rows.append([code("./" + parts[0]), esc(parts[1])])
    return table(["コマンド", "内容"], rows, "%s の冒頭コメント" % code(rel(BUILD_SH)))


@generator("west-projects")
def gen_west_projects(page: Page, args: dict[str, str]) -> str:
    remotes = {r.get("name", ""): r.get("url-base", "") for r in yaml_items(WEST_YML, "remotes")}
    default_rev = west_default_revision()
    rows, floating = [], []
    for p in yaml_items(WEST_YML, "projects"):
        name = p.get("name", "")
        url = "%s/%s" % (remotes.get(p.get("remote", ""), "").rstrip("/"), p.get("repo-path", name))
        rev = p.get("revision") or default_rev
        pinned = re.fullmatch(r"[0-9a-f]{7,40}|v\d[\w.\-]*", rev) is not None
        if not pinned:
            floating.append(name)
        rows.append(
            [
                '<a href="%s">%s</a>' % (esc(url), esc(name)),
                code(rev) + ("" if pinned else " " + badge("ブランチ追従", "warn")),
                code(p.get("path", name)),
                PROJECT_NOTES.get(name, "—"),
            ]
        )
    out = table(["プロジェクト", "revision", "置き場所", "用途"], rows, code(rel(WEST_YML)))
    if floating:
        out += (
            '\n<aside class="callout warn"><p><strong>バージョンが固定されていません。</strong>'
            "%s は revision がブランチ名なので、<code>./scripts/build-local.sh --update</code> を"
            "実行するたびにその時点の最新を取り込みます（通常のビルドでは動きません）。"
            "安定させたいならコミットかタグに固定します。</p></aside>" % "、".join(code(n) for n in floating)
        )
    return out
