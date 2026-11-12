"""小红书网页版适配器。

动作：关注用户、发送私信。
24 位十六进制用户 ID 可直接拼 https://www.xiaohongshu.com/user/profile/<ID>；
小红书的搜索结果页结构变动频繁，非链接目标一律走 type=user 搜索并点开第一条用户。
网页版风控较严，建议配合人工确认与较低频率使用。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 小红书用户主页 ID 为 24 位十六进制串
_USER_ID_RE = re.compile(r"^[0-9a-f]{24}$")


class XiaohongshuAdapter(WebAdapter):
    platform = "xiaohongshu"
    kind = "web"
    actions = {"follow", "send_message"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("/user/profile/",)

    display_name = "小红书"
    home_url = "https://www.xiaohongshu.com"

    # 未登录会弹出登录框，首页也有「登录」按钮
    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"css": ".login-btn"},
        {"role": "link", "name": "登录", "exact": True},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "关注", "exact": True},
        {"css": ".follow-btn"},
        {"css": 'button:has-text("关注")'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"text": "私信", "exact": True},
        {"css": 'button:has-text("私信")'},
        {"text": "发消息", "exact": True},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]

    # 搜索结果里的第一条用户
    user_card_candidates: list[Selector] = [
        {"css": 'a[href*="/user/profile/"]'},
        {"css": ".user-card"},
    ]

    nick_separators = (" - ", " | ", " — ", "的小红书", "_小红书")
    nick_suffixes = ("的小红书", "_小红书")
    site_titles = ("小红书", "小红书 - 你的生活指南", "你的生活指南")

    def build_profile_url(self, target: str) -> str:
        """24 位十六进制 ID 直接拼主页；小红书号/昵称需要走搜索。"""
        tid = (target or "").strip().strip("/")
        if not _USER_ID_RE.match(tid.lower()):
            return ""
        return f"https://www.xiaohongshu.com/user/profile/{tid}"

    def build_search_url(self, target: str) -> str:
        return f"https://www.xiaohongshu.com/search_result?keyword={quote(target, safe='')}&type=user"
