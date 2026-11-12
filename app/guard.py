"""安全守卫：目标清洗、去重、频率限制、风险分级、文案体检。

设计原则：宁可少发，不可误发。所有拦截都要给出人能看懂的原因。
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from . import store
from .settings import limits_for, load_settings

URL_RE = re.compile(r"^https?://", re.I)
BLOCKED_SCHEMES = {"javascript", "file", "data", "about"}
PLATFORM_DOMAINS = {
    "douyin": ("douyin.com", "iesdouyin.com"),
    "kuaishou": ("kuaishou.com", "kwai.com", "gifshow.com"),
    "weibo": ("weibo.com", "weibo.cn"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "zhihu": ("zhihu.com",),
    "tieba": ("tieba.baidu.com", "baidu.com"),
}


def clean_targets(raw: list[str]) -> list[str]:
    """去空白、去重、保持顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        for line in str(item).replace("，", "\n").replace(",", "\n").splitlines():
            t = line.strip().strip('"').strip("'")
            if not t:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def render_message(template: str, target: str, nick: str | None = None, keep_nick: bool = False) -> str:
    """渲染文案变量。

    keep_nick=True 时保留 {nick} 交给适配器在执行时用真实昵称替换
    （网页平台能读到对方昵称；桌面端读不到，由引擎兜底替换成 target）。
    """
    text = template or ""
    if not keep_nick:
        text = text.replace("{nick}", nick or target)
    return text.replace("{target}", target)


def check_url_safety(platform: str, target: str) -> tuple[bool, str]:
    """限制只能跳转到该平台自己的域名，避免被当成任意网页驱动器。"""
    if not URL_RE.match(target):
        return True, ""
    try:
        parsed = urlparse(target)
    except ValueError:
        return False, "链接格式无法解析"
    if parsed.scheme.lower() in BLOCKED_SCHEMES:
        return False, "不接受本地/脚本类链接"
    host = (parsed.hostname or "").lower()
    allowed = PLATFORM_DOMAINS.get(platform, ())
    if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
        return False, f"链接域名 {host} 不属于 {platform}，为安全起见拒绝"
    return True, ""


def risk_of(platform: str, action: str, target: str) -> str:
    if action == "send_message":
        return "high"  # 主动私信是最容易被判定骚扰的行为
    if action in ("add_friend", "join_group"):
        return "medium"
    return "low"


def evaluate(
    platform: str,
    action: str,
    target: str,
    settings: dict[str, Any] | None = None,
) -> tuple[bool, str, str]:
    """返回 (是否允许, 原因, 风险等级)。"""
    cfg = settings or load_settings()
    safety = cfg.get("safety", {})
    risk = risk_of(platform, action, target)

    if not target:
        return False, "目标为空", risk
    if len(target) > 200:
        return False, "目标过长（>200 字符）", risk

    for kw in safety.get("blocked_keywords", []):
        if kw and kw in target:
            return False, f"命中禁用词「{kw}」", risk

    ok, why = check_url_safety(platform, target)
    if not ok:
        return False, why, risk

    # 去重：N 小时内同一目标不重复触达
    dedupe_hours = int(cfg.get("dedupe_hours", 168))
    prev = store.last_contact(platform, target)
    if prev and prev.get("last_at") and dedupe_hours > 0:
        from datetime import datetime, timedelta

        try:
            last = datetime.fromisoformat(prev["last_at"])
            if datetime.now() - last < timedelta(hours=dedupe_hours):
                return (
                    False,
                    f"{dedupe_hours} 小时内已对同一目标执行过（{prev.get('last_action')}，{prev['last_at']}）",
                    risk,
                )
        except ValueError:
            pass

    # 频率：小时/日上限
    lim = limits_for(platform, cfg)
    if store.usage_count(platform, 1) >= int(lim.get("per_hour", 15)):
        return False, f"已触发小时上限（{int(lim.get('per_hour', 15))} 次/小时）", risk
    if store.usage_count(platform, 24) >= int(lim.get("per_day", 50)):
        return False, f"已触发每日上限（{int(lim.get('per_day', 50))} 次/天）", risk

    return True, "可以执行", risk


def message_health(platform: str, text: str) -> tuple[bool, str]:
    """文案体检：太长、全链接、空内容直接拦。"""
    if not text or not text.strip():
        return False, "文案为空"
    if len(text) > 600:
        return False, "文案超过 600 字，容易触发风控"
    if text.count("http") > 2:
        return False, "文案里链接过多（>2），容易被判定为垃圾信息"
    return True, ""
