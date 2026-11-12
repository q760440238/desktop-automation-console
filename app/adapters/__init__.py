"""适配器注册表。

每个平台一个单例；延迟创建，避免启动时就去碰浏览器/微信。
"""
from __future__ import annotations

from typing import Any

from .base import BaseAdapter
from .bilibili import BilibiliAdapter
from .douyin import DouyinAdapter
from .kuaishou import KuaishouAdapter
from .qq import QQAdapter
from .tieba import TiebaAdapter
from .wechat import WechatAdapter
from .wecom import WecomAdapter
from .weibo import WeiboAdapter
from .xiaohongshu import XiaohongshuAdapter
from .zhihu import ZhihuAdapter

_REGISTRY: dict[str, BaseAdapter] = {
    "wechat": WechatAdapter(),
    "wecom": WecomAdapter(),
    "qq": QQAdapter(),
    "douyin": DouyinAdapter(),
    "kuaishou": KuaishouAdapter(),
    "weibo": WeiboAdapter(),
    "bilibili": BilibiliAdapter(),
    "xiaohongshu": XiaohongshuAdapter(),
    "zhihu": ZhihuAdapter(),
    "tieba": TiebaAdapter(),
}


def get_adapter(platform: str) -> BaseAdapter | None:
    return _REGISTRY.get(platform)


def all_adapters() -> dict[str, BaseAdapter]:
    return dict(_REGISTRY)


async def health_all() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, ad in _REGISTRY.items():
        try:
            out[name] = await ad.health()
        except Exception as exc:  # 适配器不允许让探测拖垮接口
            out[name] = {"platform": name, "ready": False, "detail": f"探测异常：{exc}"}
    return out


async def close_all() -> None:
    for ad in _REGISTRY.values():
        try:
            await ad.close()
        except Exception:
            pass
