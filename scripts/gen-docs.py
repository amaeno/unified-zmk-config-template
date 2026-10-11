#!/usr/bin/env python3
"""docs/*.html の自動生成ブロックを、リポジトリ内の元ファイルから作り直す。

    python3 scripts/gen-docs.py           生成ブロックを更新する
    python3 scripts/gen-docs.py --check   更新が要るファイルを列挙する（要るなら終了コード 1）

HTML の中の次の囲みだけを書き換える。囲みの外の手書き部分には触らない。

    <!-- gen:名前 キー=値 ... -->
    （ここはスクリプトが上書きする）
    <!-- /gen:名前 -->

build.yaml やキーマップのように繰り返し変わる事実を、手で二重管理しないための仕組み。
資料に新しい事実を載せるときは、手で書く前にここへ生成器を足せないか考える。
ホストの python3 標準ライブラリだけで動く（PyYAML も使わない）。
"""
from __future__ import annotations

import argparse
import ast
import html
import re
import sys
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
BUILD_YAML = REPO / "build.yaml"
WEST_YML = REPO / "config" / "west.yml"
BUILD_SH = REPO / "scripts" / "build-local.sh"
SHIELD_DIR = REPO / "boards" / "shields" / "sosho"
CLAUDE_MD = REPO / "CLAUDE.md"
SKILLS = REPO / ".claude" / "skills"
AGENTS = REPO / ".claude" / "agents"

# ナビゲーションに並べるページ（この順で表示）。ファイルが無いものは「準備中」になる。
PAGES = [
    ("index.html", "トップ", "目次と「やりたいこと → どこを見る」の早見表"),
    ("workflow.html", "開発フロー", "git の運用・ビルド・書き込み・トラブル対応・資料と AI の使い方"),
    ("hardware.html", "ハードウェア", "マイコン・左右の役割・ピン配置・エンコーダ・ポインティングデバイス"),
    ("keymap.html", "キーマップ", "レイヤー図・キー位置番号・コンボ・エンコーダの割り当て"),
    ("settings.html", "設定項目", "変えられる項目と現在値、変え方、ビルドの要否"),
    ("features.html", "機能", "使っている機能と、ZMK で追加できる機能の候補"),
    ("zmk-reference.html", "ZMK リファレンス", "参照している ZMK と外部モジュールの仕様メモ"),
    ("known-issues.html", "既知の課題", "動作に影響しない不整合と、未解決の課題"),
    ("changelog.html", "変更履歴", "カスタマイズの履歴と設計判断"),
]

# config/west.yml の各プロジェクトの用途。west.yml には書く場所が無いのでここで持つ。
# 値は HTML としてそのまま埋め込む。
PROJECT_NOTES = {
    "zmk": "ZMK 本体",
    "zmk-rgbled-widget": "RGB LED による状態表示（電池残量・接続状態）",
    "zmk-pmw3610-driver": "トラックボール (PMW3610) のドライバ",
    "zmk_encoder": "エンコーダでのスクロール（<code>zmk,behavior-encoder-mouse-scroll</code>）",
}

BLOCK = re.compile(
    r"(?P<open><!--\s*gen:(?P<name>[\w-]+)(?P<args>[^>]*?)\s*-->)"
    r".*?"
    r"(?P<close><!--\s*/gen:(?P=name)\s*-->)",
    re.S,
)


class Page:
    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text


Generator = Callable[[Page, "dict[str, str]"], str]
GENERATORS: dict[str, Generator] = {}


def generator(name: str) -> Callable[[Generator], Generator]:
    def deco(fn: Generator) -> Generator:
        GENERATORS[name] = fn
        return fn

    return deco


# ------------------------------------------------------------------ HTML の部品


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def code(s: str) -> str:
    return "<code>%s</code>" % esc(s)


def rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def source_note(source_html: str) -> str:
    """生成ブロックの末尾に付ける「どこから作ったか」の注記。"""
    return '<p class="gen-note">自動生成 · 元: %s</p>' % source_html


def table(head: list[str], rows: list[list[str]], source_html: str) -> str:
    """セルは HTML としてそのまま埋め込む。呼び出し側でエスケープしておくこと。"""
    out = [
        '<div class="gen">',
        '<div class="table-wrap">',
        "<table>",
        "<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % h for h in head),
        "<tbody>",
    ]
    out += ["<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows]
    out += ["</tbody>", "</table>", "</div>", source_note(source_html), "</div>"]
    return "\n".join(out)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


# ------------------------------------------------------------------ 元ファイルの読み取り


def yaml_items(path: Path, key: str) -> list[dict[str, str]]:
    """`key:` 直下のブロックシーケンスを dict のリストとして返す。

    build.yaml と west.yml が使っている形（`- k: v` と、それに続く `k: v`）だけを読む
    簡易版。入れ子のリストやフロースタイル（`[a, b]`）は読まない。
    """
    items: list[dict[str, str]] = []
    key_indent: int | None = None
    for raw in path.read_text("utf-8").splitlines():
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


def west_default_revision() -> str:
    m = re.search(r"^\s*defaults:\s*\n\s+revision:\s*(\S+)", WEST_YML.read_text("utf-8"), re.M)
    return m.group(1) if m else ""


def frontmatter(path: Path) -> dict[str, str]:
    """SKILL.md / エージェント定義の frontmatter を読む。1 行の `キー: 値` と `>` 折り返しだけ扱う。"""
    m = re.match(r"---\n(.*?)\n---\n", path.read_text("utf-8"), re.S)
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
    text = p.read_text("utf-8")
    if p.suffix == ".py":
        doc = (ast.get_docstring(ast.parse(text)) or "").strip()
        return doc.splitlines()[0] if doc else "—"
    for line in text.splitlines()[1:]:
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip() and not line.startswith("#"):
            break
    return "—"


# ------------------------------------------------------------------ Markdown（CLAUDE.md の一部を載せる用）


def md_inline(s: str) -> str:
    out = []
    for part in re.split(r"(`[^`]+`)", s):
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(code(part[1:-1]))
            continue
        t = esc(part)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
        out.append(t)
    return "".join(out)


def join_lines(lines: list[str]) -> str:
    """改行で折った文をつなぐ。日本語の途中に空白を入れないよう、英数字どうしのときだけ空白を挟む。"""
    out = ""
    for line in lines:
        if out and re.match(r"[\x21-\x7e]", out[-1]) and re.match(r"[\x21-\x7e]", line[0]):
            out += " "
        out += line
    return out


def md_table(rows: list[str]) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ['<div class="table-wrap">', "<table>"]
    out.append("<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % md_inline(c) for c in head))
    out.append("<tbody>")
    out += ["<tr>%s</tr>" % "".join("<td>%s</td>" % md_inline(c) for c in r) for r in body]
    out += ["</tbody>", "</table>", "</div>"]
    return "\n".join(out)


def md_to_html(md: str) -> str:
    """CLAUDE.md で使っている範囲（段落・箇条書き・表・コードブロック・### 見出し）だけを変換する。"""
    out: list[str] = []
    para: list[str] = []
    items: list[list[str]] = []
    rows: list[str] = []
    fence: list[str] | None = None

    def flush() -> None:
        if para:
            out.append("<p>%s</p>" % md_inline(join_lines(para)))
            para.clear()
        if items:
            lis = "\n".join("<li>%s</li>" % md_inline(join_lines(i)) for i in items)
            out.append("<ul>\n%s\n</ul>" % lis)
            items.clear()
        if rows:
            out.append(md_table(rows))
            rows.clear()

    for line in md.splitlines():
        if fence is not None:
            if line.startswith("```"):
                out.append("<pre><code>%s</code></pre>" % esc("\n".join(fence)))
                fence = None
            else:
                fence.append(line)
            continue
        s = line.strip()
        if line.startswith("```"):
            flush()
            fence = []
        elif not s or re.fullmatch(r"-{3,}|\*{3,}", s):
            flush()  # 空行と区切り線（節の境目にしか使っていない）
        elif s.startswith("|"):
            if not rows:
                flush()
            rows.append(s)
        elif re.match(r"#{3,6}\s", s):
            flush()
            level = len(s) - len(s.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (level, md_inline(s[level:].strip()), level))
        elif re.match(r"[-*]\s", line):
            if para or rows:
                flush()
            items.append([s[2:].strip()])
        elif items and line.startswith(" "):
            items[-1].append(s)
        else:
            if items or rows:
                flush()
            para.append(s)
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------ 生成器


@generator("nav")
def gen_nav(page: Page, args: dict[str, str]) -> str:
    items = []
    for fname, label, _ in PAGES:
        if not (DOCS / fname).exists():
            items.append('<li><span class="nav-todo">%s<small>準備中</small></span></li>' % esc(label))
        elif fname == page.path.name:
            items.append('<li><a href="%s" aria-current="page">%s</a></li>' % (fname, esc(label)))
        else:
            items.append('<li><a href="%s">%s</a></li>' % (fname, esc(label)))
    return "\n".join(
        [
            '<nav class="site-nav" aria-label="資料の目次">',
            '<a class="brand" href="index.html">双掌<span>sosho カスタマイズ資料</span></a>',
            "<ul>",
            *items,
            "</ul>",
            "</nav>",
        ]
    )


@generator("toc")
def gen_toc(page: Page, args: dict[str, str]) -> str:
    heads = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', page.text, re.S)
    lis = "\n".join('<li><a href="#%s">%s</a></li>' % (hid, strip_tags(t)) for hid, t in heads)
    return '<nav class="toc" aria-label="このページの目次">\n<p>このページの内容</p>\n<ol>\n%s\n</ol>\n</nav>' % lis


@generator("page-cards")
def gen_page_cards(page: Page, args: dict[str, str]) -> str:
    items = []
    for fname, label, desc in PAGES:
        if fname == "index.html":
            continue
        if (DOCS / fname).exists():
            items.append(
                '<li><a href="%s"><strong>%s</strong><span>%s</span></a></li>'
                % (fname, esc(label), esc(desc))
            )
        else:
            items.append(
                '<li><div class="todo"><strong>%s<small>準備中</small></strong><span>%s</span></div></li>'
                % (esc(label), esc(desc))
            )
    return '<ul class="cards">\n%s\n</ul>' % "\n".join(items)


@generator("build-targets")
def gen_build_targets(page: Page, args: dict[str, str]) -> str:
    rows = []
    for e in yaml_items(BUILD_YAML, "include"):
        shield = e.get("shield", "")
        first = shield.split()[0] if shield else ""
        name = e.get("artifact-name") or first
        conf = SHIELD_DIR / (first + ".conf")
        studio = "ZMK_STUDIO=y" in e.get("cmake-args", "") or (
            conf.exists() and re.search(r"^CONFIG_ZMK_STUDIO=y", conf.read_text("utf-8"), re.M)
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
        rows.append([code(name), side, role, pointer, "有効" if studio else "—"])
    return table(["ターゲット", "書き込む側", "役割", "ポインタ", "Studio"], rows, code(rel(BUILD_YAML)))


@generator("build-commands")
def gen_build_commands(page: Page, args: dict[str, str]) -> str:
    rows = []
    for line in BUILD_SH.read_text("utf-8").splitlines()[1:]:
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
                code(rev) + ("" if pinned else ' <span class="badge warn">ブランチ追従</span>'),
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


@generator("scripts")
def gen_scripts(page: Page, args: dict[str, str]) -> str:
    rows = [
        [code(rel(p)), esc(script_summary(p))]
        for p in sorted((REPO / "scripts").iterdir())
        if p.suffix in (".py", ".sh")
    ]
    return table(["ファイル", "内容"], rows, "<code>scripts/</code> の各ファイル冒頭")


@generator("ai-tools")
def gen_ai_tools(page: Page, args: dict[str, str]) -> str:
    # 説明文が長いので表ではなくカード状の一覧にする（狭い画面で列が潰れるため）
    def item(name: str, badges: list[str], fm: dict[str, str]) -> str:
        if fm.get("effort"):
            badges.append("effort: " + fm["effort"])
        return '<li><p class="item-head">%s %s</p><p>%s</p></li>' % (
            code(name),
            " ".join('<span class="badge">%s</span>' % esc(b) for b in badges),
            esc(fm.get("description", "")),
        )

    items = []
    for p in sorted(SKILLS.glob("*/SKILL.md")):
        fm = frontmatter(p)
        run = "fork で実行" if fm.get("context") == "fork" else "メイン会話で実行"
        model = fm.get("model", "メイン会話と同じモデル")
        items.append(item("/" + fm.get("name", p.parent.name), ["skill", model, run], fm))
    for p in sorted(AGENTS.glob("*.md")):
        fm = frontmatter(p)
        items.append(item(fm.get("name", p.stem), ["サブエージェント", fm.get("model", "inherit")], fm))
    return '<div class="gen">\n<ul class="item-list">\n%s\n</ul>\n%s\n</div>' % (
        "\n".join(items),
        source_note("<code>.claude/skills/*/SKILL.md</code>・<code>.claude/agents/*.md</code> の frontmatter"),
    )


@generator("claude-md")
def gen_claude_md(page: Page, args: dict[str, str]) -> str:
    title = args.get("section", "")
    m = re.search(
        r"^## %s[ \t]*\n(.*?)(?=^## |\Z)" % re.escape(title), CLAUDE_MD.read_text("utf-8"), re.S | re.M
    )
    if not m:
        raise ValueError("CLAUDE.md に「## %s」の節がありません" % title)
    return '<div class="gen">\n%s\n%s\n</div>' % (
        md_to_html(m.group(1)),
        source_note("<code>CLAUDE.md</code> の「%s」節" % esc(title)),
    )


# ------------------------------------------------------------------ 本体


def render(path: Path, text: str, errors: list[str]) -> str:
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
        args = dict(a.split("=", 1) for a in m.group("args").split() if "=" in a)
        try:
            body = fn(page, args)
        except (OSError, ValueError) as e:
            errors.append("%s: gen:%s を作れません: %s" % (rel(path), name, e))
            return m.group(0)
        return "%s\n%s\n%s" % (m.group("open"), body.strip("\n"), m.group("close"))

    return BLOCK.sub(sub, text)


def main() -> int:
    ap = argparse.ArgumentParser(description="docs/*.html の自動生成ブロックを更新する")
    ap.add_argument("--check", action="store_true", help="書き換えずに、更新が要るかだけを調べる")
    args = ap.parse_args()

    errors: list[str] = []
    stale: list[Path] = []
    n_blocks = 0
    for path in sorted(DOCS.glob("*.html")):
        old = path.read_text("utf-8")
        n_blocks += len(BLOCK.findall(old))
        new = render(path, old, errors)
        if new != old:
            stale.append(path)
            if not args.check:
                path.write_text(new, "utf-8")

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
