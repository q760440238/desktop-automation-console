"""快手网页版适配器。

动作：关注用户、发送私信。
与抖音同一套基类，差异只在域名、搜索路径与部分按钮文案上。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 快手主页 ID：纯数字 uid 或 3x 开头的长串
_UID_RE = re.compile(r"^[0-9A-Za-z_-]{3,40}$")


class KuaishouAdapter(WebAdapter):
    platform = "kuaishou"
    kind = "web"
    actions = {"follow", "send_message", "comment"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("/profile/",)

    display_name = "快手"
    home_url = "https://www.kuaishou.com"

    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"css": 'button:has-text("登录")'},
        {"role": "link", "name": "登录", "exact": True},
        {"css": '[class*="login"]'},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "+ 关注", "exact": True},
        {"text": "关注 TA", "exact": True},
        {"css": 'button:has-text("关注")'},
        {"css": '[class*="follow"]'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"text": "私信", "exact": True},
        {"text": "发消息", "exact": True},
        {"css": 'button:has-text("私信")'},
        {"css": '[class*="message"]'},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
        {"css": '[class*="send"]'},
    ]

    user_card_candidates: list[Selector] = [
        {"css": 'a[href*="/profile/"]'},
        {"css": '[class*="user"] a'},
    ]

    nick_separators = (" - ", " | ", " — ", "的快手", "_快手")
    nick_suffixes = ("的快手", "- 快手", "_快手")
    site_titles = ("快手", "快手-记录世界记录你", "记录世界记录你")

    def build_profile_url(self, target: str) -> str:
        """快手主页固定是 /profile/<uid>，纯 ID 可以直接拼。"""
        tid = (target or "").strip().strip("/")
        if not _UID_RE.match(tid):
            return ""
        if tid.lower().startswith("http"):
            return ""
        return f"https://www.kuaishou.com/profile/{quote(tid, safe='')}"

    def build_search_url(self, target: str) -> str:
        return f"https://www.kuaishou.com/search/video?searchKey={quote(target, safe='')}"
