"""抖音网页版适配器。

动作：关注用户、发送私信。
非链接目标走站内用户搜索，点开第一条用户卡片；关注后复查「已关注 / 互相关注」，
避免把「点了但没生效」误判成成功。私信前若页面提示对方不可接收，直接如实失败。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 抖音 sec_uid 的固定前缀，只有这种长 ID 才能直接拼主页链接
_SEC_UID_RE = re.compile(r"^MS4wLjAB[A-Za-z0-9_-]{10,}$")


class DouyinAdapter(WebAdapter):
    platform = "douyin"
    kind = "web"
    actions = {"follow", "send_message", "comment"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("/user/",)

    display_name = "抖音"
    home_url = "https://www.douyin.com"

    # 未登录时首页右上角是「登录」按钮
    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"css": 'button:has-text("登录")'},
        {"role": "link", "name": "登录", "exact": True},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "+ 关注", "exact": True},
        {"text": "关注 TA", "exact": True},
        {"css": '[data-e2e="user-follow"]'},
        {"css": 'button:has-text("关注")'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"text": "私信", "exact": True},
        {"text": "发消息", "exact": True},
        {"css": '[data-e2e="user-message"]'},
        {"css": 'button:has-text("私信")'},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": '[data-e2e="msg-send"]'},
        {"css": 'button:has-text("发送")'},
    ]

    # 搜索结果里的第一条用户卡片
    user_card_candidates: list[Selector] = [
        {"css": '[data-e2e="search-result-user"] a'},
        {"css": 'a[href*="/user/"]'},
    ]

    nick_separators = (" - ", " | ", " — ", "的抖音", "_抖音")
    nick_suffixes = ("的抖音", "- 抖音", "_抖音")
    site_titles = ("抖音", "抖音-记录美好生活", "记录美好生活")

    def build_profile_url(self, target: str) -> str:
        """只有 sec_uid 能直接拼主页；抖音号需要走搜索，无法反查。"""
        tid = (target or "").strip().strip("/")
        if not _SEC_UID_RE.match(tid):
            return ""
        return f"https://www.douyin.com/user/{quote(tid, safe='')}"

    def build_search_url(self, target: str) -> str:
        return f"https://www.douyin.com/search/{quote(target, safe='')}?type=user"
