"""B站（哔哩哔哩）网页版适配器。

动作：关注用户、发送私信。
纯数字 UID 直接拼 https://space.bilibili.com/<UID>；其它目标走站内搜索并点开第一条用户。
B站私信入口在个人空间页，部分账号关闭了陌生人私信，页面提示会如实反馈。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 允许「12345678」「UID:12345678」「uid：12345678」等写法
_UID_RE = re.compile(r"^(?:uid[:：]?)?(\d{3,})$", re.IGNORECASE)


class BilibiliAdapter(WebAdapter):
    platform = "bilibili"
    kind = "web"
    actions = {"follow", "send_message", "comment"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("space.bilibili.com",)

    display_name = "B站"
    home_url = "https://www.bilibili.com"

    # 未登录时顶栏右侧是「登录」入口（header-login-entry）
    login_candidates: list[Selector] = [
        {"css": ".header-login-entry"},
        {"role": "link", "name": "登录", "exact": True},
        {"role": "button", "name": "登录", "exact": True},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "+ 关注", "exact": True},
        {"css": ".follow-btn"},
        {"css": 'button:has-text("关注")'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "发消息", "exact": True},
        {"text": "发消息", "exact": True},
        {"css": ".send-msg"},
        {"text": "私信", "exact": True},
        {"css": 'a:has-text("发消息")'},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]

    # 综合搜索页里的第一条 UP 主
    user_card_candidates: list[Selector] = [
        {"css": ".b-user-name a"},
        {"css": 'a[href*="space.bilibili.com"]'},
    ]

    nick_separators = (" - ", " | ", " — ", "的个人空间", "的个人主页")
    nick_suffixes = ("的个人空间", "的个人主页", "_哔哩哔哩_bilibili")
    site_titles = ("哔哩哔哩", "哔哩哔哩_bilibili", "哔哩哔哩 (゜-゜)つロ 干杯~-bilibili")

    def build_profile_url(self, target: str) -> str:
        """纯数字 UID 直接拼空间链接；昵称走搜索。"""
        match = _UID_RE.match((target or "").strip())
        if not match:
            return ""
        return f"https://space.bilibili.com/{match.group(1)}"

    def build_search_url(self, target: str) -> str:
        return f"https://search.bilibili.com/all?keyword={quote(target, safe='')}"
