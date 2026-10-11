"""サイトの骨組み（ナビ・目次・ページ一覧）と、リポジトリのメタ情報（スクリプト・AI ツール・CLAUDE.md の節）。"""
from __future__ import annotations

import re

from . import md
from .common import (
    AGENTS,
    DOCS,
    REPO,
    SKILLS,
    Page,
    badge,
    claude_section,
    code,
    esc,
    frontmatter,
    generator,
    rel,
    script_summary,
    source_note,
    strip_tags,
    table,
)

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
                '<li><a href="%s"><strong>%s</strong><span>%s</span></a></li>' % (fname, esc(label), esc(desc))
            )
        else:
            items.append(
                '<li><div class="todo"><strong>%s<small>準備中</small></strong><span>%s</span></div></li>'
                % (esc(label), esc(desc))
            )
    return '<ul class="cards">\n%s\n</ul>' % "\n".join(items)


@generator("claude-md")
def gen_claude_md(page: Page, args: dict[str, str]) -> str:
    title = args.get("section", "")
    return '<div class="gen">\n%s\n%s\n</div>' % (
        md.to_html(claude_section(title)),
        source_note("<code>CLAUDE.md</code> の「%s」節" % esc(title)),
    )


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
            " ".join(badge(b) for b in badges),
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
