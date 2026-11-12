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
        self._recovery_cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _blank_state() -> dict[str, Any]:
        return {
            "running": False,
            "platform": "",
            "platform_name": "",
            "brief": "",
            "message": "",
            "action": "send_message",
            "auto_follow": False,
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
            "updated_at": 0.0,
            "current_job": "",
            "empty_rounds": 0,
            "ai_decisions": 0,
            "ai_fail_streak": 0,
            "last_ai": None,
            "tried_keywords": [],
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
        # 心跳：界面据此判断是「在冷却」还是「真卡住了」
        s["idle_seconds"] = int(time.time() - s["updated_at"]) if s.get("updated_at") else 0
        # 冷却期本来就不动，不算卡住
        s["stalled"] = bool(s["running"] and s["idle_seconds"] > 180 and s["remain"] == 0)
        return s

    def _touch(self) -> None:
        self.state["updated_at"] = time.time()

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
        auto_follow: bool = False,
    ) -> dict[str, Any]:
        if self.running:
            raise ValueError("无限模式已经在运行了")
        if engine.panic:
            raise ValueError("当前处于急停状态，无法启动")
        if platform not in PLATFORMS:
            raise ValueError("未知平台")
        if PLATFORMS[platform]["kind"] == "desktop":
            raise ValueError("无限模式只支持网页平台（桌面端只能搜到已有联系人，没有「找新人」的概念）")
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
            "auto_follow": bool(auto_follow),
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
        self.state["tried_keywords"] = list(self.state["keywords"])

        self._task = asyncio.create_task(self._loop())
        return self.status()

    async def stop(self, reason: str = "用户手动停止") -> dict[str, Any]:
        if not self.running:
            self.state["running"] = False
            return self.status()
        self._stop.set()
        self.state["phase"] = "正在停止"
        self._note(reason)

        # 先把正在跑的 job 停掉，避免「点了停止但还在发」
        job_id = self.state.get("current_job") or ""
        if job_id:
            try:
                await engine.stop(job_id)
            except Exception:
                pass

        task = self._task
        if task is not None:
            try:
                # shield：等它自己收尾，超时再强杀
                await asyncio.wait_for(asyncio.shield(task), timeout=8)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=6)
                except BaseException:
                    pass

        self.state["running"] = False
        self.state["phase"] = "已停止"
        self.state["next_at"] = 0.0
        self.state["stop_reason"] = self.state.get("stop_reason") or reason
        return self.status()

    async def _recover(self, stage: str, detail: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """让 AI 判断这次没进展的原因，并给出下一步动作。

        AI 不可用时返回 retry，由调用方的确定性计数器兜底，保证永远不会因为
        「模型没配」而卡死。
        """
        s = self.state
        if int(s.get("ai_decisions", 0)) >= 30:
            return {"action": "stop", "reason": "AI 决策已达 30 次，为避免失控自动停止"}

        ctx = {
            "platform": s.get("platform_name"),
            "brief": s.get("brief"),
            "round": s.get("round"),
            "stage": stage,
            "detail": detail[:400],
            "keywords": s.get("keywords"),
            "tried_keywords": s.get("tried_keywords") or [],
            "sent": s.get("sent"),
            "failed": s.get("failed"),
            "no_progress_count": s.get("empty_rounds", 0),
            "simulation": s.get("simulation"),
            "recent": [r.get("msg") for r in (s.get("recent") or [])[-5:]],
        }
        if extra:
            ctx.update(extra)

        try:
            d = await asyncio.to_thread(ai.decide_recovery, ctx)
        except Exception as exc:  # 模型调用异常不能影响主循环
            d = {"ok": False, "detail": str(exc)}
        s["ai_decisions"] = int(s.get("ai_decisions", 0)) + 1

        if d.get("ok"):
            s["ai_fail_streak"] = 0
            s["last_ai"] = {
                "diagnosis": d.get("diagnosis"),
                "action": d.get("action"),
                "reason": d.get("reason"),
                "ts": time.strftime("%H:%M:%S"),
            }
            self._note(
                f"AI 诊断：{d.get('diagnosis') or '-'} → 动作 {d.get('action')}"
                + (f"（{d.get('reason')}）" if d.get("reason") else "")
            )
            out = d
        else:
            streak = int(s.get("ai_fail_streak", 0)) + 1
            s["ai_fail_streak"] = streak
            if streak >= 2:
                # AI 连续给不出决策时，继续重试就是盲目空转，直接停
                return {
                    "action": "stop",
                    "reason": f"AI 连续 {streak} 次无法给出有效决策（{d.get('detail')}），为避免空转已停止",
                }
            out = {"action": "retry", "reason": f"AI 这次没给出有效决策（{d.get('detail')}），先重试一次"}
            self._note(out["reason"], "warn")

        self._touch()
        return out

    async def _handle_dead_end(
        self, adapter: Any, stage: str, detail: str, extra: dict[str, Any] | None = None
    ) -> bool:
        """处理一次「没进展」。返回 True 表示应该停止整个循环。"""
        s = self.state
        s["empty_rounds"] = int(s.get("empty_rounds", 0)) + 1
        act = await self._recover(stage, detail, extra)
        action = act.get("action")

        if action == "stop":
            s["stop_reason"] = act.get("reason") or "AI 判断需要人工介入"
            s["detail"] = act.get("reason") or detail
            return True

        if action == "reload":
            try:
                await adapter.close()
            except Exception:
                pass
            s["detail"] = "已重置浏览器，准备重试"
            await self._sleep(20)
            return False

        if action == "wait":
            seconds = int(act.get("wait_seconds") or 120)
            s["phase"] = "AI 建议等待"
            s["detail"] = f"等 {seconds} 秒（{act.get('reason') or '冷却'}）"
            await self._sleep(seconds)
            return False

        if action == "switch_keyword":
            tried = {k.lower() for k in (s.get("tried_keywords") or [])}
            current = {k.lower() for k in (s.get("keywords") or [])}
            proposed = [k for k in (act.get("keywords") or []) if k]
            fresh = [k for k in proposed if k.lower() not in tried and k.lower() not in current]
            if not fresh:
                # AI 给不出新词 = 这个方向确实试到头了，不能无限换词
                s["empty_rounds"] = int(s["empty_rounds"]) + 1
                s["detail"] = "AI 给的关键词都已经试过了"
                self._note("AI 没有给出新关键词，判定该方向已试尽", "warn")
                if int(s["empty_rounds"]) >= 2:
                    s["stop_reason"] = "多个关键词都搜不到目标，方向可能不可行，建议换平台或换更具体的描述"
                    return True
                await self._sleep(60)
                return False
            s["tried_keywords"] = list(tried | current)
            s["keywords"] = fresh
            s["empty_rounds"] = 0
            s["detail"] = "换关键词：" + " / ".join(fresh)
            self._note("换关键词：" + " / ".join(fresh))
            await self._sleep(10)
            return False

        # retry：确定性兜底，连续太多次仍然要停
        if int(s["empty_rounds"]) >= 4:
            s["stop_reason"] = f"连续 {s['empty_rounds']} 次没有进展，已停止"
            return True
        s["detail"] = f"重试中（第 {s['empty_rounds']} 次）"
        await self._sleep(min(int(s.get("interval", 120)), 90))
        return False

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
        plan_fails = 0

        try:
            while not self._stop.is_set():
                self._touch()
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
                try:
                    # 浏览器调用必须有超时兜底：页面卡死时不能让整个循环一起卡住
                    res = await asyncio.wait_for(adapter.discover(keyword, fetch), timeout=150)
                except asyncio.TimeoutError:
                    s["detail"] = "搜索超时（150 秒）"
                    self._note("搜索超时", "error")
                    try:
                        await adapter.close()
                    except Exception:
                        pass
                    if await self._handle_dead_end(adapter, "timeout", s["detail"]):
                        break
                    continue
                if not res.get("ok"):
                    s["detail"] = str(res.get("detail") or "搜索失败")
                    self._note(f"搜索失败：{s['detail']}", "error")
                    if res.get("captcha"):
                        # 验证码是确定性阻断，且任何模型都绕不过去：直接停，不交给 AI 赌
                        s["stop_reason"] = "触发人机验证，已停止（请在浏览器里手动完成验证后再启动）"
                        break
                    if await self._handle_dead_end(adapter, "search", s["detail"]):
                        break
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
                    s["detail"] = "这一轮没有新的候选"
                    self._note(f"第 {s['round']} 轮没有新候选", "warn")
                    if await self._handle_dead_end(
                        adapter,
                        "empty",
                        s["detail"],
                        {
                            "found": len(res.get("candidates") or []),
                            "page_url": res.get("url"),
                            "page_title": res.get("title"),
                        },
                    ):
                        break
                    continue

                empty_rounds = 0
                s["phase"] = "生成计划"
                s["detail"] = f"{len(picked)} 个新目标"
                self._touch()
                try:
                    plan = engine.plan(
                        PlanRequest(
                            platform=platform,
                            action=s["action"],
                            targets=picked,
                            message=s["message"],
                            mode="auto",
                            auto_follow=bool(s.get("auto_follow")),
                        )
                    )
                except ValueError as exc:
                    # 计划失败是「确定性失败」：同样的目标重试也不会成功，必须计数熔断，
                    # 否则会变成每轮失败一次、永远停不下来的空转（曾经的真实 bug）。
                    plan_fails += 1
                    s["detail"] = str(exc)
                    self._note(f"生成计划失败（连续 {plan_fails} 次）：{exc}", "error")
                    if await self._handle_dead_end(adapter, "plan", str(exc)):
                        break
                    continue
                plan_fails = 0

                job = plan["job"]
                job_id = job["id"]
                for step in job.get("steps", []):
                    seen.add(step["target"])
                engine.approve(job_id, all_steps=True)
                self._note(f"第 {s['round']} 轮：{len(job.get('steps', []))} 条已自动批准，开始执行")

                # 2) 执行并等待结束
                s["phase"] = "执行中"
                s["current_job"] = job_id
                self._touch()
                try:
                    await engine.run(job_id)
                except ValueError as exc:
                    s["current_job"] = ""
                    s["detail"] = str(exc)
                    self._note(f"启动执行失败：{exc}", "error")
                    fails += 1
                    if await self._handle_dead_end(adapter, "run", str(exc)):
                        break
                    continue

                deadline = time.time() + 900
                last_job_status = ""
                while time.time() < deadline and not self._stop.is_set():
                    row = store.get_job_row(job_id)
                    last_job_status = (row or {}).get("status", "")
                    if row and row["status"] in TERMINAL:
                        break
                    self._touch()
                    await asyncio.sleep(2)

                # 看门狗：超时还没结束，说明这一轮卡住了，停掉 job 并记一次失败
                if last_job_status not in TERMINAL:
                    try:
                        await engine.stop(job_id)
                    except Exception:
                        pass
                    fails += 1
                    self._note(f"第 {s['round']} 轮执行超过 15 分钟未结束，已强制停止", "error")
                    s["current_job"] = ""
                    if fails >= 3:
                        s["stop_reason"] = "连续 3 轮执行超时/失败，已停止"
                        break
                    await self._sleep(30)
                    continue
                s["current_job"] = ""

                row = store.get_job_row(job_id) or {}
                stats = self._job_stats(job_id)
                s["sent"] = int(s["sent"]) + stats["ok"]
                s["failed"] = int(s["failed"]) + stats["failed"]
                s["skipped"] = int(s["skipped"]) + stats["skipped"]
                s["detail"] = f"成功 {stats['ok']} · 失败 {stats['failed']} · 跳过 {stats['skipped']}"
                self._note(f"第 {s['round']} 轮结束：{s['detail']}")
                s["empty_rounds"] = 0

                if stats["ok"] == 0 and stats["failed"] > 0:
                    fails += 1
                    if fails >= 3:
                        s["stop_reason"] = "连续 3 轮全部失败，已停止（检查登录态或页面是否改版）"
                        break
                else:
                    fails = 0

                s["phase"] = "冷却"
                s["detail"] = f"{s.get('interval', 120)} 秒后进入下一轮"
                self._touch()
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
            s["current_job"] = ""
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
