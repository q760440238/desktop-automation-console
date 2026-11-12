"""微博网页版适配器。

动作：关注用户、发送私信。
纯数字目标直接拼 https://weibo.com/u/<UID>；其它目标走站内用户搜索并点开第一条用户卡片。
微博私信受双方关注关系限制，页面若提示不可发送，会如实记录失败原因且不自动重试。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 允许「1234567890」「u/1234567890」「UID:1234567890」等写法
_UID_RE = re.compile(r"^(?:u/)?(?:uid[:：]?)?(\d{4,})$", re.IGNORECASE)


class WeiboAdapter(WebAdapter):
    platform = "weibo"
    kind = "web"
    actions = {"follow", "send_message", "comment"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("weibo.com/u/", "weibo.com/n/")

    display_name = "微博"
    home_url = "https://weibo.com"

    # 未登录会被跳到 passport.weibo.com，首页也会出现「登录」入口
    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"role": "link", "name": "登录", "exact": True},
        {"css": 'a[href*="passport.weibo.com"]'},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "+关注", "exact": True},
        {"text": "关注", "exact": True},
        {"css": '[action-type="follow"]'},
        {"css": 'a:has-text("关注")'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"text": "私信", "exact": True},
        {"css": 'a[href*="/chat"]'},
        {"text": "发消息", "exact": True},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]

    # s.weibo.com/user 搜索结果里的第一条用户
    user_card_candidates: list[Selector] = [
        {"css": ".card-wrap .name a"},
        {"css": 'a[href*="weibo.com/u/"]'},
        {"css": ".card-wrap a[usercard]"},
    ]

    nick_separators = (" - ", " | ", " — ", "的微博", "_微博")
    nick_suffixes = ("的微博", "_微博")
    site_titles = (
        "微博",
        "微博 – 随时随地发现新鲜事",
        "微博-随时随地发现新鲜事",
        "随时随地发现新鲜事",
    )

    def build_profile_url(self, target: str) -> str:
        """数字 UID 直接拼主页；昵称无法反查 UID，走搜索。"""
        tid = (target or "").strip().lstrip("@")
        match = _UID_RE.match(tid)
        if not match:
            return ""
        return f"https://weibo.com/u/{match.group(1)}"

    def build_search_url(self, target: str) -> str:
        return f"https://s.weibo.com/user?q={quote(target, safe='')}"
