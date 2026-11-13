"""平台适配器基础接口。

约定：
- `health()` 只做只读探测，绝不弹窗、绝不点击。
- `execute()` 执行单个动作，任何异常都要吞掉并返回 ExecResult(ok=False)，不允许抛出。
- 返回的 detail 会直接展示在界面与审计日志里，因此必须是给人看的中文说明。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..settings import SHOT_DIR


@dataclass
class ExecResult:
    ok: bool
    detail: str = ""
    screenshot: str | None = None
    simulated: bool = False
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "screenshot": self.screenshot,
            "simulated": self.simulated,
            "retryable": self.retryable,
        }


@dataclass
class Ctx:
    """执行上下文：一次批量任务内共享的配置快照。"""

    settings: dict[str, Any]
    job_id: str = ""

    @property
    def simulation(self) -> bool:
        return bool(self.settings.get("simulation", True))


def safe_slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "_", text or "")
    return (s[:limit] or "target").strip("_") or "target"


def shot_path(platform: str, tag: str) -> Path:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return SHOT_DIR / f"{ts}_{platform}_{safe_slug(tag)}.png"


class BaseAdapter:
    # 桌面端没有「站内找陌生人」：无限模式改为按启动时给的名单轮发。
    # 名单挂在实例上，discover() 原样返回，挑选/去重仍由白循环统一处理。
    _pool: list[str] = []

    def set_pool(self, targets: list[str]) -> None:
        self._pool = [str(t).strip() for t in (targets or []) if str(t).strip()]

    async def discover(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        """桌面端的「发现」：有名单用名单，没名单就让视觉模型看界面自己挑人。"""
        pool = list(getattr(self, "_pool", []) or [])
        if pool:
            cands = [{"url": t, "name": t, "snippet": "名单目标"} for t in pool[: max(1, limit)]]
            return {"ok": True, "candidates": cands, "keyword": keyword, "pool": True}

        import asyncio

        from .. import vision_agent

        key = getattr(self, "key", "")
        if not key:
            return {"ok": False, "detail": "这个平台还不支持自动找人"}

        cands = await asyncio.to_thread(vision_agent.propose_targets, key, keyword or "任意好友", limit)
        if not cands:
            return {
                "ok": False,
                "detail": "视觉没有从界面上找到可用的联系人（可能是列表收起了，或窗口不在前台）",
            }
        return {"ok": True, "candidates": cands, "keyword": keyword, "vision": True}
    platform: str = ""
    kind: str = "generic"
    actions: set[str] = set()

    async def health(self) -> dict[str, Any]:
        return {"platform": self.platform, "ready": False, "detail": "尚未实现"}

    async def execute(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        raise NotImplementedError

    async def probe(self) -> dict[str, Any]:
        """返回可诊断信息（控件树、页面标题等），供人工校准选择器。"""
        return {"error": "该平台不支持探测"}

    async def close(self) -> None:
        return None

    # --- 演练 ---
    def simulate(self, action: str, target: str, text: str, extra: dict[str, Any]) -> ExecResult:
        verb = {
            "send_message": "发送消息",
            "add_friend": "发送好友申请",
            "join_group": "申请加群",
            "follow": "关注",
            "comment": "发表留言",
        }.get(action, action)
        time.sleep(0.05)
        if extra.get("auto_follow") and action == "send_message":
            detail = f"【演练】已关注并{verb} → {target}"
        else:
            detail = f"【演练】已{verb} → {target}"
        return ExecResult(ok=True, simulated=True, detail=detail)
