"""无限模式：自动「找目标 → 生成计划 → 审批 → 执行 → 冷却」的循环。

设计边界（这些不是可选项，写死在代码里）：
1. 频率上限照常生效：小时额度用完就等着，日额度用完就停。
2. 同一个人不会被发第二次（内存集合 + 数据库去重窗口双重保障）。
3. 急停、连续失败、平台未登录都会立刻熔断。
4. 每一轮都写审计事件，事后能完整复盘。
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from . import ai, store
from .adapters import get_adapter
from .engine import engine
from .schemas import ACTION_LABELS, PLATFORMS, PlanRequest
from .settings import limits_for, load_settings

TERMINAL = {"done", "cancelled", "failed"}


class AutoPilot:
    def __init__(self) -> None:
        self._task: asyncio.Task[Any] | None = None
        self._stop = asyncio.Event()
        self.state: dict[str, Any] = self._blank_state()

    @staticmethod
    def _blank_state() -> dict[str, Any]:
        return {
            "running": False,
            "platform": "",
            "platform_name": "",
            "brief": "",
            "message": "",
            "action": "send_message",
            "round": 0,
            "max_rounds": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "phase": "空闲",
            "detail": "",
            "stop_reason": "",
            "next_at": 0.0,
            "started_at": "",
            "recent": [],
        }

    # ------------------------------------------------------------------ 状态
    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        s = dict(self.state)
        s["running"] = self.running
        s["remain"] = max(0, int(s.get("next_at", 0) - time.time())) if s.get("next_at") else 0
        return s

    def _note(self, msg: str, level: str = "info") -> None:
        recent = self.state.setdefault("recent", [])
        recent.append({"ts": time.strftime("%H:%M:%S"), "msg": msg, "level": level})
        del recent[:-8]
        store.add_event(level, f"[无限模式] {msg}", platform=self.state.get("platform", ""))

    # ------------------------------------------------------------------ 控制
    async def start(
        self,
        platform: str,
        brief: str,
        message: str,
        action: str = "send_message",
        interval: int = 120,
        limit: int = 5,
        max_rounds: int = 0,
    ) -> dict[str, Any]:
        if self.running:
            raise ValueError("无限模式已经在运行了")
        if engine.panic:
            raise ValueError("当前处于急停状态，无法启动")
        if platform not in PLATFORMS:
            raise ValueError("未知平台")
        if action not in PLATFORMS[platform]["actions"]:
            raise ValueError(f"{PLATFORMS[platform]['name']} 不支持「{ACTION_LABELS.get(action, action)}」")
        if not (brief or "").strip():
            raise ValueError("请写一句要寻找什么方向的目标")
        if not (message or "").strip():
            raise ValueError("请填写要发送的文案")

        self._stop.clear()
        cfg = load_settings()
        if cfg.get("mode") == "dry_run":
            raise ValueError("当前是「只出计划」模式，无限模式不会执行；请先切到「确认后执行」")
        self.state = self._blank_state()
        self.state.update({
            "running": True,
            "platform": platform,
            "platform_name": PLATFORMS[platform]["name"],
            "brief": brief.strip(),
            "message": message,
            "action": action,
            "max_rounds": int(max_rounds or 0),
            "interval": max(30, min(int(interval or 120), 3600)),
            "limit": max(1, min(int(limit or 5), 10)),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "phase": "启动中",
            "simulation": bool(cfg.get("simulation", True)),
        })
        self._note(f"启动：{self.state['platform_name']} · 方向「{brief.strip()[:30]}」")
        if self.state["simulation"]:
            self._note("当前是演练模式，不会真实发送", "warn")
        else:
            self._note("当前是真实执行模式，会给找到的人实际发消息", "warn")

        # 先把方向拆成 2-3 个搜索词，每轮轮换，避免反复搜到同一批人
        try:
            plan_kw = await asyncio.to_thread(
                ai.build_search_plan, brief.strip(), self.state["platform_name"]
            )
            self.state["keywords"] = plan_kw.get("keywords") or [brief.strip()]
            if plan_kw.get("note"):
                self._note(f"搜索策略：{plan_kw['note']}")
        except Exception:
            self.state["keywords"] = [brief.strip()]
        self._note("本轮关键词：" + " / ".join(self.state["keywords"][:3]))

        self._task = asyncio.create_task(self._loop())
        return self.status()

    async def stop(self, reason: str = "用户手动停止") -> dict[str, Any]:
        if not self.running:
            self.state["running"] = False
            return self.status()
        self._stop.set()
        self.state["phase"] = "正在停止"
        self._note(reason)
        try:
            await asyncio.wait_for(self._task, timeout=10)  # type: ignore[arg-type]
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        self.state["running"] = False
        self.state["phase"] = "已停止"
        self.state["stop_reason"] = self.state.get("stop_reason") or reason
        return self.status()

    async def _sleep(self, seconds: float) -> None:
        self.state["next_at"] = time.time() + seconds
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
        self.state["next_at"] = 0.0

    # ------------------------------------------------------------------ 主循环
    async def _loop(self) -> None:
        s = self.state
        platform = s["platform"]
        adapter = get_adapter(platform)
        lim = limits_for(platform)
        per_hour = int(lim.get("per_hour", 15))
        per_day = int(lim.get("per_day", 50))
        seen: set[str] = set()
        empty_rounds = 0
        fails = 0

        try:
            while not self._stop.is_set():
                if engine.panic:
                    s["stop_reason"] = "急停触发"
                    break
                if s["max_rounds"] and s["round"] >= s["max_rounds"]:
                    s["stop_reason"] = f"已完成 {s['max_rounds']} 轮"
                    break
                if adapter is None:
                    s["stop_reason"] = "平台适配器缺失"
                    break

                used_day = store.usage_count(platform, 24)
                if used_day >= per_day:
                    s["stop_reason"] = f"今日额度已用尽（{used_day}/{per_day}）"
                    break
                used_hour = store.usage_count(platform, 1)
                if used_hour >= per_hour:
                    s["phase"] = "等待小时额度"
                    s["detail"] = f"本小时已发 {used_hour}/{per_hour}，等 5 分钟再看"
                    self._note(s["detail"], "warn")
                    await self._sleep(300)
                    continue

                # 1) 找目标（每轮换一个关键词，并且多抓一些再挑没发过的）
                s["round"] = int(s["round"]) + 1
                kws = s.get("keywords") or [s["brief"]]
                keyword = kws[(int(s["round"]) - 1) % len(kws)]
                s["phase"] = "寻找目标"
                s["detail"] = f"搜索「{keyword[:24]}」"
                fetch = min(30, max(10, int(s.get("limit", 5)) * 4))
                res = await adapter.discover(keyword, fetch)
                if not res.get("ok"):
                    s["detail"] = str(res.get("detail") or "搜索失败")
                    self._note(f"搜索失败：{s['detail']}", "error")
                    empty_rounds += 1
                    if empty_rounds >= 3:
                        s["stop_reason"] = "连续 3 轮搜索失败，已停止"
                        break
                    await self._sleep(60)
                    continue

                picked: list[str] = []
                for c in res.get("candidates") or []:
                    url = str(c.get("url") or "")
                    if not url or url in seen:
                        continue
                    if store.last_contact(platform, url) is not None:
                        continue
                    picked.append(url)
                    if len(picked) >= int(s.get("limit", 5)):
                        break
                if not picked:
                    empty_rounds += 1
                    s["detail"] = "这一轮没有新的候选"
                    self._note(f"第 {s['round']} 轮没有新候选", "warn")
                    if empty_rounds >= 5:
                        s["stop_reason"] = "连续 5 轮没有新目标，可能方向太窄，已停止"
                        break
                    await self._sleep(s.get("interval", 120))
                    continue

                empty_rounds = 0
                s["phase"] = "生成计划"
                s["detail"] = f"{len(picked)} 个新目标"
                try:
                    plan = engine.plan(
                        PlanRequest(
                            platform=platform,
                            action=s["action"],
                            targets=picked,
                            message=s["message"],
                            mode="auto",
                        )
                    )
                except ValueError as exc:
                    s["detail"] = str(exc)
                    self._note(f"生成计划失败：{exc}", "error")
                    await self._sleep(s.get("interval", 120))
                    continue

                job = plan["job"]
                job_id = job["id"]
                for step in job.get("steps", []):
                    seen.add(step["target"])
                engine.approve(job_id, all_steps=True)
                self._note(f"第 {s['round']} 轮：{len(job.get('steps', []))} 条已自动批准，开始执行")

                # 2) 执行并等待结束
                s["phase"] = "执行中"
                try:
                    await engine.run(job_id)
                except ValueError as exc:
                    s["detail"] = str(exc)
                    self._note(f"启动执行失败：{exc}", "error")
                    fails += 1
                    await self._sleep(s.get("interval", 120))
                    continue

                deadline = time.time() + 900
                while time.time() < deadline and not self._stop.is_set():
                    row = store.get_job_row(job_id)
                    if row and row["status"] in TERMINAL:
                        break
                    await asyncio.sleep(2)

                row = store.get_job_row(job_id) or {}
                stats = self._job_stats(job_id)
                s["sent"] = int(s["sent"]) + stats["ok"]
                s["failed"] = int(s["failed"]) + stats["failed"]
                s["skipped"] = int(s["skipped"]) + stats["skipped"]
                s["detail"] = f"成功 {stats['ok']} · 失败 {stats['failed']} · 跳过 {stats['skipped']}"
                self._note(f"第 {s['round']} 轮结束：{s['detail']}")

                if stats["ok"] == 0 and stats["failed"] > 0:
                    fails += 1
                    if fails >= 3:
                        s["stop_reason"] = "连续 3 轮全部失败，已停止（检查登录态或页面是否改版）"
                        break
                else:
                    fails = 0

                s["phase"] = "冷却"
                s["detail"] = f"{s.get('interval', 120)} 秒后进入下一轮"
                await self._sleep(s.get("interval", 120))
        except asyncio.CancelledError:
            s["stop_reason"] = s.get("stop_reason") or "任务被取消"
            raise
        except Exception as exc:  # 兜底：任何异常都要落状态，不能让前端看到「运行中」
            s["stop_reason"] = f"异常停止：{exc}"
            self._note(s["stop_reason"], "error")
        finally:
            s["running"] = False
            s["phase"] = "已停止"
            s["next_at"] = 0.0
            if s.get("stop_reason"):
                self._note(f"停止：{s['stop_reason']}")

    @staticmethod
    def _job_stats(job_id: str) -> dict[str, int]:
        steps = store.job_steps(job_id)
        out = {"ok": 0, "failed": 0, "skipped": 0}
        for s in steps:
            if s["status"] in out:
                out[s["status"]] += 1
        return out


autopilot = AutoPilot()
