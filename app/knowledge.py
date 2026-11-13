"""经验库：把"某个平台某个动作怎么做成的"存下来，下次直接检索复用。

不算真正的向量 RAG，但对中文界面操作这类短文本够用：
按字符二元组（bigram）算重合度，避免中文分词依赖。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

STORE = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "flows.jsonl"


def _bigrams(text: str) -> set[str]:
    s = "".join(ch for ch in (text or "") if not ch.isspace())
    return {s[i : i + 2] for i in range(len(s) - 1)} or {s}


def _load() -> list[dict[str, Any]]:
    if not STORE.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def save(entry: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    with STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find(platform: str, action: str, query: str, top: int = 2) -> list[dict[str, Any]]:
    """检索最相关的经验：先按平台+动作过滤，再按文字相似度排序。"""
    q = _bigrams(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for e in _load():
        if e.get("platform") != platform:
            continue
        if action and e.get("action") not in (action, ""):
            continue
        text = f"{e.get('goal', '')} {e.get('title', '')} {' '.join(e.get('steps') or [])}"
        overlap = len(q & _bigrams(text))
        score = overlap / max(1, len(q))
        if score > 0.08:
            scored.append((score, e))
    scored.sort(key=lambda p: -p[0])
    return [e for _, e in scored[:top]]


def render(entries: list[dict[str, Any]]) -> str:
    """把检索到的经验拼成给模型看的提示。"""
    if not entries:
        return ""
    parts = ["已知的可行做法（供参考，不一定要照抄）："]
    for e in entries:
        if not e.get("success"):
            parts.append(f"- 【此前失败过】{e.get('goal')}：这些入口试过但无效，别再重复：")
            for tip in (e.get("tips") or [])[:4]:
                parts.append(f"    × {tip}")
            continue
        parts.append(f"- {e.get('title') or e.get('goal')}")
        for i, s in enumerate(e.get("steps") or [], 1):
            parts.append(f"    {i}) {s}")
        for tip in e.get("tips") or []:
            parts.append(f"    注意：{tip}")
    return "\n".join(parts)
