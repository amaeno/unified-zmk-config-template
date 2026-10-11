#!/usr/bin/env python3
"""作業の区切りで、改善メモがたまっていれば retro skill での改善提案を促す（Stop フック）。

.claude/settings.json の hooks.Stop から呼ばれる。次の条件がそろったときだけ
{"decision": "block", "reason": ...} を出力し、Claude に改善案を出させる。

  - Stop フックによる継続中ではない（stop_hook_active が false）
  - .claude/improvements.md の「未対応」に 1 件以上ある
  - 未コミットの変更が無い（作業の区切り。improvements.md 自体の変更は数えない）
  - このセッションでまだ促していない（.claude/state/retro-nudge.json に記録）

どれかが欠ければ何も出力せずに終わるので、メモが無いあいだはトークンを使わない。
一時的に止めたいときは環境変数 SOSHO_RETRO_NUDGE=0。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

LOG = Path(".claude") / "improvements.md"
STATE = Path(".claude") / "state" / "retro-nudge.json"


def pending(root: Path) -> list[str]:
    try:
        text = (root / LOG).read_text("utf-8")
    except OSError:
        return []
    m = re.search(r"^## 未対応[ \t]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return [l for l in (m.group(1) if m else "").splitlines() if l.startswith("- ")]


def at_break(root: Path) -> bool:
    """未コミットの変更が無いか。improvements.md だけの変更は区切りとみなす。"""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        return False
    changed = [l[3:].strip() for l in r.stdout.splitlines() if l.strip()]
    return all(p == LOG.as_posix() for p in changed)


def already_nudged(root: Path, session_id: str) -> bool:
    try:
        return json.loads((root / STATE).read_text("utf-8")).get("session_id") == session_id
    except (OSError, ValueError):
        return False


def main() -> int:
    if os.environ.get("SOSHO_RETRO_NUDGE") == "0":
        return 0
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if data.get("stop_hook_active"):
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
    memos = pending(root)
    session_id = str(data.get("session_id", ""))
    if not memos or not at_break(root) or already_nudged(root, session_id):
        return 0
    (root / STATE).parent.mkdir(parents=True, exist_ok=True)
    (root / STATE).write_text(json.dumps({"session_id": session_id}), "utf-8")
    reason = (
        "作業の区切りです。.claude/improvements.md の「未対応」に改善メモが %d 件あります。"
        "retro skill の手順で改善案を短く提示し、どれを適用するかユーザーに確認してください。"
        "承認されるまでファイルは変更しないこと。" % len(memos)
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
