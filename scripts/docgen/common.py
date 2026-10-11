"""資料生成の共通部品: 生成器の登録、HTML の部品、リポジトリのファイルの読み取り。"""
from __future__ import annotations

import ast
import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
BUILD_YAML = REPO / "build.yaml"
WEST_YML = REPO / "config" / "west.yml"
KEYMAP = REPO / "config" / "sosho.keymap"
BUILD_SH = REPO / "scripts" / "build-local.sh"
SHIELD_DIR = REPO / "boards" / "shields" / "sosho"
CLAUDE_MD = REPO / "CLAUDE.md"
SKILLS = REPO / ".claude" / "skills"
AGENTS = REPO / ".claude" / "agents"


class Page:
    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text


Generator = Callable[[Page, "dict[str, str]"], str]
GENERATORS: dict[str, Generator] = {}


def generator(name: str) -> Callable[[Generator], Generator]:
    """`<!-- gen:name -->` の中身を作る関数として登録する。"""

    def deco(fn: Generator) -> Generator:
        GENERATORS[name] = fn
        return fn

    return deco


# ------------------------------------------------------------------ HTML の部品


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def code(s: object) -> str:
    return "<code>%s</code>" % esc(s)


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def badge(text: str, kind: str = "") -> str:
    return '<span class="badge%s">%s</span>' % (" " + kind if kind else "", esc(text))


def source_note(source_html: str) -> str:
    """生成ブロックの末尾に付ける「どこから作ったか」の注記。"""
    return '<p class="gen-note">自動生成 · 元: %s</p>' % source_html


def sources(*paths: Path) -> str:
    return "、".join(code(rel(p)) for p in paths)


def table(head: list[str], rows: list[list[str]], source_html: str, row_classes: list[str] | None = None) -> str:
    """セルは HTML としてそのまま埋め込む。呼び出し側でエスケープしておくこと。"""
    out = [
        '<div class="gen">',
        '<div class="table-wrap">',
        "<table>",
        "<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % h for h in head),
        "<tbody>",
    ]
    for i, r in enumerate(rows):
        cls = row_classes[i] if row_classes and row_classes[i] else ""
        if len(r) == 1:  # セル 1 つの行は、分類の見出しとして横いっぱいに広げる
            cells = '<td colspan="%d">%s</td>' % (len(head), r[0])
        else:
            cells = "".join("<td>%s</td>" % c for c in r)
        out.append("<tr%s>%s</tr>" % (' class="%s"' % cls if cls else "", cells))
    out += ["</tbody>", "</table>", "</div>", source_note(source_html), "</div>"]
    return "\n".join(out)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


# ------------------------------------------------------------------ ファイルの読み取り


@lru_cache(maxsize=None)
def read(path: Path) -> str:
    return path.read_text("utf-8")


def yaml_items(path: Path, key: str) -> list[dict[str, str]]:
    """`key:` 直下のブロックシーケンスを dict のリストとして返す。

    build.yaml と west.yml が使っている形（`- k: v` と、それに続く `k: v`）だけを読む
    簡易版。入れ子のリストやフロースタイル（`[a, b]`）は読まない。
    """
    items: list[dict[str, str]] = []
    key_indent: int | None = None
    for raw in read(path).splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        text = line.strip()
        if not text or text == "---":
            continue
        indent = len(line) - len(line.lstrip())
        if key_indent is None:
            if text == key + ":":
                key_indent = indent
            continue
        # YAML はシーケンスを親キーと同じ深さに書いてもよいので、`- ` だけは同じ深さを許す
        if indent < key_indent or (indent == key_indent and not text.startswith("- ")):
            break
        if text.startswith("- "):
            items.append({})
            text = text[2:].strip()
        if items and ":" in text:
            k, _, v = text.partition(":")
            items[-1][k.strip()] = v.strip().strip("'\"")
    return items


def frontmatter(path: Path) -> dict[str, str]:
    """SKILL.md / エージェント定義の frontmatter を読む。1 行の `キー: 値` と `>` 折り返しだけ扱う。"""
    m = re.match(r"---\n(.*?)\n---\n", read(path), re.S)
    out: dict[str, str] = {}
    if not m:
        return out
    key = None
    for line in m.group(1).splitlines():
        km = re.match(r"([\w-]+):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("'\"")
        elif key and line.startswith(" "):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def script_summary(p: Path) -> str:
    """スクリプト冒頭の説明の 1 行目（.py は docstring、.sh は shebang 直後のコメント）。"""
    text = read(p)
    if p.suffix == ".py":
        doc = (ast.get_docstring(ast.parse(text)) or "").strip()
        return doc.splitlines()[0] if doc else "—"
    for line in text.splitlines()[1:]:
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip() and not line.startswith("#"):
            break
    return "—"


def claude_section(title: str) -> str:
    """CLAUDE.md の `## title` の節の本文（Markdown）。"""
    m = re.search(r"^## %s[ \t]*\n(.*?)(?=^## |\Z)" % re.escape(title), read(CLAUDE_MD), re.S | re.M)
    if not m:
        raise ValueError("CLAUDE.md に「## %s」の節がありません" % title)
    return m.group(1)


def my_targets() -> list[str]:
    """この機体で使っているビルドターゲット（CLAUDE.md の「この機体」節の表に書いてあるもの）。

    表の下の説明文には「使っていないターゲット」も出てくるので、表の行だけを見る。
    """
    rows = "\n".join(l for l in claude_section("この機体").splitlines() if l.startswith("|"))
    return re.findall(r"`(sosho_[LR]_\w+)`", rows)


def conf_files() -> list[Path]:
    """シールドの .conf を、使っているものを先に R → L の順で返す。"""
    mine = my_targets()
    files = sorted(SHIELD_DIR.glob("sosho_*.conf"), key=lambda p: (p.stem not in mine, "_L_" in p.stem, p.stem))
    return files


# ------------------------------------------------------------------ GPIO の表記

# XIAO nRF52840 の端のピン D0〜D10（Zephyr の seeed_xiao_connector.dtsi の xiao_d より）
XIAO_PINS = {
    (0, 2): "D0",
    (0, 3): "D1",
    (0, 28): "D2",
    (0, 29): "D3",
    (0, 4): "D4",
    (0, 5): "D5",
    (1, 11): "D6",
    (1, 12): "D7",
    (1, 13): "D8",
    (1, 14): "D9",
    (1, 15): "D10",
}


def pin(port: int, num: int) -> str:
    """`P0.02 (D0)` の形。D0〜D10 以外は Plus で増えたピンなので nRF の名前だけ。"""
    name = "P%d.%02d" % (port, num)
    d = XIAO_PINS.get((port, num))
    return '%s<span class="tag">%s</span>' % (code(name), d) if d else code(name)
