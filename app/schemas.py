"""请求/响应数据模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Platform = Literal[
    "wechat", "wecom", "qq", "douyin", "kuaishou",
    "weibo", "bilibili", "xiaohongshu", "zhihu", "tieba",
]
ActionType = Literal["send_message", "add_friend", "join_group", "follow"]
JobMode = Literal["dry_run", "confirm", "auto"]

PLATFORMS: dict[str, dict[str, Any]] = {
    "wechat": {
        "name": "微信",
        "kind": "desktop",
        "actions": ["send_message"],
        "target_label": "好友备注 / 群名",
        "hint": "需要微信 PC 端已登录并保持窗口可访问（4.x 为 Weixin.exe）。",
        "color": "#07C160",
    },
    "wecom": {
        "name": "企业微信",
        "kind": "desktop",
        "actions": ["send_message"],
        "target_label": "联系人 / 群名",
        "hint": "需要企业微信 PC 端已登录，且主窗口可访问。",
        "color": "#2E7CF6",
    },
    "qq": {
        "name": "QQ",
        "kind": "desktop",
        "actions": ["add_friend", "join_group", "send_message"],
        "target_label": "QQ 号 / 群号 / 昵称",
        "hint": "QQ NT 已登录前提下，通过界面搜索完成加好友、加群与发消息。",
        "color": "#12B7F5",
    },
    "douyin": {
        "name": "抖音",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "用户主页链接 / 抖音号",
        "hint": "网页版需先手动登录一次，登录态保存在本地浏览器配置目录。",
        "color": "#FE2C55",
    },
    "kuaishou": {
        "name": "快手",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "用户主页链接 / 快手号",
        "hint": "网页版需先手动登录一次；私信入口在对方主页，部分账号未开放。",
        "color": "#FF4906",
    },
    "weibo": {
        "name": "微博",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "用户主页链接 / 微博 UID",
        "hint": "网页版私信需要双方互相关注或对方开启接收，失败会如实记录。",
        "color": "#E6162D",
    },
    "bilibili": {
        "name": "B站",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "空间链接 / UID",
        "hint": "私信入口在消息页，部分账号关闭了陌生人私信。",
        "color": "#FB7299",
    },
    "xiaohongshu": {
        "name": "小红书",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "用户主页链接 / 小红书号",
        "hint": "网页版风控较严，建议降低频率并开启人工确认。",
        "color": "#FF2442",
    },
    "zhihu": {
        "name": "知乎",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "用户主页链接 / 知乎ID",
        "hint": "私信入口常藏在「更多」菜单里，系统会自动展开再试一次。",
        "color": "#0084FF",
    },
    "tieba": {
        "name": "贴吧",
        "kind": "web",
        "actions": ["follow", "send_message"],
        "target_label": "贴吧名 / 吧链接",
        "hint": "「关注」的对象是吧（如「显卡吧」）；私信依赖百度站内信，部分账号不可用。",
        "color": "#3385FF",
    },
}

ACTION_LABELS: dict[str, str] = {
    "send_message": "发消息",
    "add_friend": "加好友",
    "join_group": "加群",
    "follow": "关注",
}


class PlanRequest(BaseModel):
    platform: Platform
    action: ActionType
    targets: list[str] = Field(default_factory=list)
    message: str = ""
    mode: JobMode | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
    # 勾选后：先关注该用户，再发送消息（仅网页平台且该平台支持关注）
    auto_follow: bool = False


class ApproveRequest(BaseModel):
    step_ids: list[str] | None = None
    all: bool = False


class SettingsPatch(BaseModel):
    patch: dict[str, Any]


class RunRequest(BaseModel):
    dry_run: bool = False
