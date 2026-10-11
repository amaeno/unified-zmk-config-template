"""資料のフリーワード検索の索引（docs/assets/search-index.js）を作る。

各ページを、id の付いた h2・h3 ごとの節に分け、見出しと本文（タグを除いた文章）を並べる。
生成ブロックの中身（表など）も含めるので、ピン名や設定名でも引ける。
ファイルを直接開いても読めるよう、JSON ではなく <script> で読み込む JS として書き出す。
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

HEADING = re.compile(r'<h([23]) id="([^"]+)">(.*?)</h\1>', re.S)


def plain(fragment: str) -> str:
    """HTML の断片を、検索用の 1 行の文章にする。"""
    fragment = re.sub(r"<!--.*?-->", " ", fragment, flags=re.S)
    fragment = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def page_sections(path: Path, text: str) -> list[dict[str, str]]:
    m = re.search(r"<main>(.*)</main>", text, re.S)
    main = m.group(1) if m else ""
    main = re.sub(r'<nav class="toc".*?</nav>', " ", main, flags=re.S)
    title_m = re.search(r"<h1>(.*?)</h1>", main, re.S)
    title = plain(title_m.group(1)) if title_m else path.stem
    out = []
    heads = list(HEADING.finditer(main))
    intro = main[: heads[0].start()] if heads else main
    out.append({"p": path.name, "t": title, "h": title, "a": "", "x": plain(intro)})
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(main)
        out.append({"p": path.name, "t": title, "h": plain(h.group(3)), "a": h.group(2), "x": plain(main[h.end() : end])})
    return [s for s in out if s["x"] or s["a"]]


def build_index(pages: dict[Path, str]) -> str:
    entries = []
    for path in sorted(pages):
        entries += page_sections(path, pages[path])
    return (
        "/* 資料の検索索引。scripts/gen-docs.py が docs/*.html から作る。手で編集しない */\n"
        "window.SOSHO_SEARCH_INDEX = %s;\n" % json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
    )
