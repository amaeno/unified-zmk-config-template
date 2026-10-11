"""変更履歴: main に取り込んだ単位（マージコミット）を、git の履歴から新しい順に並べる。

main が進むたびに中身が変わるので volatile（--check では比べない）。
"""
from __future__ import annotations

import subprocess

from .common import REPO, Page, SourceMissing, badge, code, esc, generator, source_note

# 本家（ELEKIT）の最後のコミット。これより後がこのリポジトリでの変更
FORK_POINT = "4d059f1"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise SourceMissing("git %s が失敗: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def tags_by_commit() -> dict[str, list[tuple[str, str]]]:
    """コミット → [(タグ名, タグのメッセージ)]。注釈付きタグは指している先のコミットで引く。"""
    out: dict[str, list[tuple[str, str]]] = {}
    for line in git("for-each-ref", "refs/tags", "--format=%(objectname)%09%(*objectname)%09%(refname:short)%09%(contents:subject)").splitlines():
        obj, deref, name, subject = (line.split("\t") + ["", "", "", ""])[:4]
        out.setdefault(deref or obj, []).append((name, subject))
    return out


@generator("changelog", volatile=True)
def gen_changelog(page: Page, args: dict[str, str]) -> str:
    log = git("log", "--first-parent", "main", "%s..main" % FORK_POINT, "--date=short", "--format=%H%x1f%ad%x1f%s%x1f%b%x1e")
    tags = tags_by_commit()
    items = []
    for rec in log.split("\x1e"):
        if not rec.strip():
            continue
        sha, date, subject, body = (rec.strip("\n").split("\x1f") + ["", "", "", ""])[:4]
        bullets = [l[2:].strip() for l in body.splitlines() if l.startswith("- ")]
        rest = [l.strip() for l in body.splitlines() if l.strip() and not l.startswith(("- ", "  ", "Co-Authored-By"))]
        head = "%s %s %s" % (
            code(date),
            esc(subject),
            " ".join(badge(name, "ok") + ' <small>%s</small>' % esc(msg) for name, msg in tags.get(sha, [])),
        )
        parts = ['<li><p class="item-head">%s</p>' % head.strip()]
        if bullets:
            parts.append("<ul>\n%s\n</ul>" % "\n".join("<li>%s</li>" % esc(b) for b in bullets))
        if rest:
            parts.append("<p>%s</p>" % esc(" ".join(rest)))
        parts.append("</li>")
        items.append("\n".join(parts))
    return '<div class="gen">\n<ul class="item-list history">\n%s\n</ul>\n%s\n</div>' % (
        "\n".join(items),
        source_note("git の履歴（<code>main</code> に取り込んだ単位。<code>python3 scripts/gen-docs.py</code> を実行した時点）"),
    )
