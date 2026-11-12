"""百度贴吧适配器。

贴吧和别的平台不太一样：
- 「关注」的对象是**吧**（不是人），目标是吧名或吧链接，关注后显示「已关注」。
- 「私信」依赖百度账号的站内信，部分账号没有入口，失败会如实说明。
"""
from __future__ import annotations

from urllib.parse import quote

from .web_common import Selector, WebAdapter


class TiebaAdapter(WebAdapter):
    platform = "tieba"
    kind = "web"
    actions = {"follow", "send_message"}

    # 按方向找人：搜索结果页里哪些链接算「人」
    discover_patterns = ("/f?kw=",)

    display_name = "贴吧"
    home_url = "https://tieba.baidu.com"

    login_candidates: list[Selector] = [
        {"role": "link", "name": "登录", "exact": True},
        {"role": "button", "name": "登录", "exact": True},
        {"css": 'a:has-text("登录")'},
    ]

    follow_candidates: list[Selector] = [
        {"text": "+关注", "exact": True},
        {"text": "+ 关注", "exact": True},
        {"role": "button", "name": "关注", "exact": True},
        {"text": "关注", "exact": True},
        {"css": '.forum_head .focus_btn'},
        {"css": 'a:has-text("关注")'},
    ]
    followed_texts = ("已关注", "取消关注")

    message_candidates: list[Selector] = [
        {"role": "button", "name": "私信", "exact": True},
        {"text": "私信", "exact": True},
        {"css": 'a:has-text("私信")'},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]

    # 贴吧的关注对象是吧，不需要在搜索结果里点用户卡片
    user_card_candidates: list[Selector] = []

    nick_separators = ("吧-百度贴吧", "_百度贴吧", "吧_百度贴吧", " - ")
    nick_suffixes = ("吧",)

    def build_profile_url(self, target: str) -> str:
        """贴吧没有「用户主页」概念，这里不做 profile 拼接。"""
        return ""

    def build_search_url(self, target: str) -> str:
        """把目标当成吧名，直接打开该吧首页。"""
        name = (target or "").strip().strip("/")
        if "tieba.baidu.com/f" in name:
            return name
        return f"https://tieba.baidu.com/f?kw={quote(name, safe='')}"

    def build_discover_url(self, keyword: str) -> str:
        """按方向找「吧」：用贴吧的全局搜索，结果里是 /f?kw= 这类链接。"""
        return f"https://tieba.baidu.com/f/search/res?ie=utf-8&qw={quote(keyword, safe='')}"
