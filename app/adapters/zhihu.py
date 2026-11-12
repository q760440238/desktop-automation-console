"""知乎网页版适配器。

动作：关注用户、发送私信。
知乎主页地址是 /people/<url_token>，登录用户才看得到「关注」按钮。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .web_common import Selector, WebAdapter

# 知乎 url_token 一般是字母数字下划线组合
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{2,64}$")


class ZhihuAdapter(WebAdapter):
    platform = "zhihu"
    kind = "web"
    actions = {"follow", "send_message", "comment"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("/people/",)

    display_name = "知乎"
    home_url = "https://www.zhihu.com"

    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"role": "link", "name": "登录", "exact": True},
        {"css": 'button:has-text("登录")'},
    ]

    follow_candidates: list[Selector] = [
        {"role": "button", "name": "关注", "exact": True},
        {"text": "+ 关注", "exact": True},
        {"css": 'button:has-text("关注")'},
        {"css": '.FollowButton'},
    ]
    followed_texts = ("已关注", "互相关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"role": "button", "name": "发私信", "exact": True},
        {"text": "私信", "exact": True},
        {"css": 'button:has-text("私信")'},
    ]
    # 知乎把「私信」收在「更多」里，先点更多再找一次
    more_candidates: list[Selector] = [
        {"role": "button", "name": "更多", "exact": True},
        {"css": 'button[aria-label="更多"]'},
        {"css": 'button:has-text("更多")'},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]

    user_card_candidates: list[Selector] = [
        {"css": 'a[href*="/people/"]'},
        {"css": '.UserItem a'},
    ]

    nick_separators = (" - 知乎", " | 知乎", " — ", "_知乎")
    nick_suffixes = (" - 知乎", "- 知乎", "_知乎")
    site_titles = ("知乎", "首页 - 知乎", "知乎 - 有问题，就会有答案")

    def build_profile_url(self, target: str) -> str:
        tid = (target or "").strip().strip("/")
        if not _TOKEN_RE.match(tid):
            return ""
        return f"https://www.zhihu.com/people/{quote(tid, safe='')}"

    def build_search_url(self, target: str) -> str:
        return f"https://www.zhihu.com/search?type=people&q={quote(target, safe='')}"
