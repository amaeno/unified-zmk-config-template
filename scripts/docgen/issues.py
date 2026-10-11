"""既知の課題が、いまもリポジトリに残っているかを調べる。

known-issues.html の各課題（`<h2 id="issue-ID">`）に対応するチェックをここに置く。
直した課題は資料の表示が自動で「解消済み」に変わるので、それを見て節ごと消せばよい。
"""
from __future__ import annotations

import re
from typing import Callable

import zmk_dts as dts

from .build import west_default_revision
from .common import BUILD_YAML, REPO, SHIELD_DIR, WEST_YML, Page, badge, code, esc, generator, read, yaml_items
from .keymap import combos, keymap_src, layers

# チェックは (残っているか, 補足) を返す
Check = Callable[[], "tuple[bool, str]"]
CHECKS: dict[str, Check] = {}


def check(issue_id: str) -> Callable[[Check], Check]:
    def deco(fn: Check) -> Check:
        CHECKS[issue_id] = fn
        return fn

    return deco


def active_lines(path, pattern: str) -> list[str]:
    """コメント行（# 始まり）を除いて、pattern に当たる行を返す。"""
    return [l for l in read(path).splitlines() if not l.lstrip().startswith("#") and re.search(pattern, l)]


@check("transform0")
def _transform0() -> tuple[bool, str]:
    found = "&default_transform0" in dts.strip_comments(read(SHIELD_DIR / "sosho-layouts.dtsi"))
    return found, ""


@check("pref-dup")
def _pref_dup() -> tuple[bool, str]:
    n = len(active_lines(SHIELD_DIR / "sosho_L_trackpad.conf", r"^CONFIG_BT_PERIPHERAL_PREF_MIN_INT="))
    return n > 1, "%d 回宣言" % n if n > 1 else ""


@check("zmk-mouse")
def _zmk_mouse() -> tuple[bool, str]:
    files = [p.name for p in sorted(SHIELD_DIR.glob("*.conf")) if active_lines(p, r"^CONFIG_ZMK_MOUSE=y")]
    return bool(files), "、".join(files)


@check("studio-dup")
def _studio_dup() -> tuple[bool, str]:
    in_yaml = any("ZMK_STUDIO" in e.get("cmake-args", "") for e in yaml_items(BUILD_YAML, "include"))
    in_conf = [p.name for p in sorted(SHIELD_DIR.glob("*.conf")) if active_lines(p, r"^CONFIG_ZMK_STUDIO=y")]
    return in_yaml and bool(in_conf), ""


@check("west-floating")
def _west_floating() -> tuple[bool, str]:
    default = west_default_revision()
    names = [
        p.get("name", "")
        for p in yaml_items(WEST_YML, "projects")
        if not re.fullmatch(r"[0-9a-f]{7,40}|v\d[\w.\-]*", p.get("revision") or default)
    ]
    return bool(names), "、".join(names)


@check("boot-delay")
def _boot_delay() -> tuple[bool, str]:
    cmake_on = re.search(r"^\s*cmake:\s*\.", read(REPO / "zephyr" / "module.yml"), re.M) is not None
    return (REPO / "src" / "boot_delay_hack.c").exists() and not cmake_on, ""


@check("zmk-yml")
def _zmk_yml() -> tuple[bool, str]:
    text = read(SHIELD_DIR / "sosho.zmk.yml")
    return "seeeduino_xiao_ble" in text or "abababababababa" in text, ""


@check("scrl-unused")
def _scrl_unused() -> tuple[bool, str]:
    # zmk_encoder はスクロール量を ±1 に正規化するので、この値が効くのは &msc を割り当てたキーだけ
    has_define = "ZMK_POINTING_DEFAULT_SCRL_VAL" in dts.defines(keymap_src())
    bound = any(b[:1] == ["&msc"] for l in layers() for b in l.keys + (l.sensors or [])) or any(
        c.binding[:1] == ["&msc"] for c in combos()
    )
    return has_define and not bound, ""


@check("ec11-resolution")
def _ec11_resolution() -> tuple[bool, str]:
    src = dts.strip_comments(read(SHIELD_DIR / "sosho.dtsi"))
    found = [l for l in ("left_encoder", "right_encoder") if dts.prop_raw(dts.find_labeled(src, l) or "", "resolution")]
    return bool(found), "、".join(found)


def status_html(issue_id: str) -> str:
    fn = CHECKS.get(issue_id)
    if fn is None:
        raise ValueError("課題 %s のチェックが scripts/docgen/issues.py にありません" % issue_id)
    remains, detail = fn()
    if not remains:
        return badge("解消済み", "ok")
    return badge("未修正", "warn") + (" <small>%s</small>" % esc(detail) if detail else "")


@generator("issue-status")
def gen_issue_status(page: Page, args: dict[str, str]) -> str:
    return status_html(args.get("id", ""))


@generator("issue-summary")
def gen_issue_summary(page: Page, args: dict[str, str]) -> str:
    rows = []
    for issue_id, title in re.findall(r'<h2 id="issue-([\w-]+)">(.*?)</h2>', page.text, re.S):
        rows.append('<tr><td><a href="#issue-%s">%s</a></td><td>%s</td></tr>' % (issue_id, title, status_html(issue_id)))
    return "\n".join(
        [
            '<div class="gen">',
            '<div class="table-wrap">',
            "<table>",
            "<thead><tr><th>課題</th><th>状態</th></tr></thead>",
            "<tbody>",
            *rows,
            "</tbody>",
            "</table>",
            "</div>",
            '<p class="gen-note">自動生成 · 状態は %s がファイルを調べて判定</p>' % code("scripts/docgen/issues.py"),
            "</div>",
        ]
    )
