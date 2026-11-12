"""任务引擎：生成计划 → 人工审批 → 限速执行 → 审计留痕。

安全边界（硬编码，不随配置放宽）：
1. 未审批的步骤永不执行。
2. 每一步执行前再查一次小时/日上限，防止审批期间配额已被其它任务用掉。
3. 急停开关一旦打开，所有任务立即在下一步之前中止。
"""
from __future__ import annotations

import asyncio
import json
import random
from typing import Any

from . import guard, store
from .adapters import get_adapter
from .adapters.base import Ctx, ExecResult
from .schemas import ACTION_LABELS, PLATFORMS, PlanRequest
from .settings import limits_for, load_settings

TERMINAL = {"ok", "failed", "rejected", "skipped"}


class Engine:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancel: dict[str, asyncio.Event] = {}
        self._panic = False
        self._run_lock = asyncio.Lock()

    # ------------------------------------------------------------ 状态
    @property
    def panic(self) -> bool:
        return self._panic

    def set_panic(self, on: bool) -> bool:
        self._panic = bool(on)
        store.add_event("error" if on else "info", "急停已触发，所有任务正在中止" if on else "急停已解除")
        if on:
            for ev in self._cancel.values():
                ev.set()
        return self._panic

    def running_count(self) -> int:
        return sum(1 for t in self._tasks.values() if not t.done())

    def pending_count(self) -> int:
        total = 0
        for j in store.list_jobs(limit=50):
            total += int(j.get("stats", {}).get("pending", 0))
        return total

    # ------------------------------------------------------------ 计划
    def plan(self, req: PlanRequest) -> dict[str, Any]:
        cfg = load_settings()
        targets = guard.clean_targets(req.targets)
        safety = cfg.get("safety", {})
        max_batch = int(safety.get("max_batch", 50))

        if not targets:
            raise ValueError("没有可用目标：请每行填写一个链接或账号")
        if len(targets) > max_batch:
            raise ValueError(f"单批最多 {max_batch} 个目标，当前 {len(targets)} 个")

        action = req.action
        supported = PLATFORMS.get(req.platform, {}).get("actions", [])
        if action not in supported:
            raise ValueError(f"{PLATFORMS.get(req.platform, {}).get('name', req.platform)} 不支持「{ACTION_LABELS.get(action, action)}」")

        if action == "send_message":
            ok, why = guard.message_health(req.platform, req.message)
            if not ok:
                raise ValueError(why)

        mode = req.mode or cfg.get("mode", "confirm")
        plan_rows: list[dict[str, Any]] = []
        step_rows: list[dict[str, Any]] = []
        for t in targets:
            allowed, reason, risk = guard.evaluate(req.platform, action, t, cfg)
            text = guard.render_message(req.message, t, keep_nick=True) if action == "send_message" else ""
            plan_rows.append(
                {"target": t, "action": action, "risk": risk, "allowed": allowed, "reason": reason, "text": text}
            )
            if allowed:
                step_rows.append({"target": t, "text": text, "risk": risk, "reason": reason})

        if not step_rows:
            reasons = "；".join(sorted({r["reason"] for r in plan_rows}))
            raise ValueError(f"全部目标都被安全策略拦截：{reasons}")

        status = "planned"
        if mode == "auto" and not cfg.get("safety", {}).get("require_approval", True):
            status = "queued"

        extra = dict(req.extra or {})
        support_follow = "follow" in PLATFORMS.get(req.platform, {}).get("actions", [])
        if req.auto_follow and support_follow and action == "send_message":
            extra["auto_follow"] = True
        job_id = store.insert_job(req.platform, action, mode, status, req.message, extra)
        store.insert_steps(job_id, step_rows)
        store.add_event(
            "info",
            f"生成计划：{PLATFORMS.get(req.platform, {}).get('name', req.platform)} · "
            f"{ACTION_LABELS.get(action, action)} · {len(step_rows)} 条可执行 / {len(plan_rows) - len(step_rows)} 条被拦截",
            platform=req.platform,
            job_id=job_id,
        )
        return {"job": self.view(job_id), "plan": plan_rows}

    # ------------------------------------------------------------ 审批
    def approve(self, job_id: str, step_ids: list[str] | None = None, all_steps: bool = False) -> dict[str, Any]:
        job = store.get_job_row(job_id)
        if not job:
            raise ValueError("任务不存在")
        steps = store.job_steps(job_id)
        chosen = [s for s in steps if (all_steps or (step_ids and s["id"] in step_ids))]
        if not chosen:
            raise ValueError("没有选中任何步骤")
        n = 0
        for s in chosen:
            if s["status"] == "pending":
                store.update_step(s["id"], status="approved")
                n += 1
        store.add_event("info", f"已批准 {n} 条步骤", platform=job["platform"], job_id=job_id)
        self._refresh_job_status(job_id)
        return self.view(job_id)

    def reject(self, job_id: str, step_ids: list[str] | None = None, all_steps: bool = False) -> dict[str, Any]:
        job = store.get_job_row(job_id)
        if not job:
            raise ValueError("任务不存在")
        steps = store.job_steps(job_id)
        chosen = [s for s in steps if (all_steps or (step_ids and s["id"] in step_ids))]
        n = 0
        for s in chosen:
            if s["status"] in ("pending", "approved"):
                store.update_step(s["id"], status="rejected", detail="人工拒绝", finished_at=store.now_iso())
                n += 1
        store.add_event("warn", f"已拒绝 {n} 条步骤", platform=job["platform"], job_id=job_id)
        self._refresh_job_status(job_id)
        return self.view(job_id)

    def _refresh_job_status(self, job_id: str) -> str:
        steps = store.job_steps(job_id)
        counts: dict[str, int] = {}
        for s in steps:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        if counts.get("approved") or counts.get("running"):
            status = "approved"
        elif counts.get("pending"):
            status = "planned"
        elif counts.get("ok"):
            status = "done"
        else:
            status = "cancelled"
        store.set_job_status(job_id, status)
        return status

    # ------------------------------------------------------------ 执行
    async def run(self, job_id: str) -> dict[str, Any]:
        job = store.get_job_row(job_id)
        if not job:
            raise ValueError("任务不存在")
        if self._panic:
            raise ValueError("急停中，无法启动新任务")
        if load_settings().get("mode") == "dry_run":
            raise ValueError("当前是「只出计划」模式，不会执行任何动作；请切换到「确认后执行」")
        if job_id in self._tasks and not self._tasks[job_id].done():
            raise ValueError("该任务正在执行")

        steps = store.job_steps(job_id)
        if not any(s["status"] == "approved" for s in steps):
            raise ValueError("没有已批准的步骤，请先批准再执行")

        ev = asyncio.Event()
        self._cancel[job_id] = ev
        task = asyncio.create_task(self._run_job(job_id, ev))
        self._tasks[job_id] = task
        return self.view(job_id)

    async def stop(self, job_id: str) -> dict[str, Any]:
        ev = self._cancel.get(job_id)
        if ev:
            ev.set()
        t = self._tasks.get(job_id)
        if t and not t.done():
            t.cancel()
        store.add_event("warn", "收到停止指令", job_id=job_id)
        return self.view(job_id)

    async def _run_job(self, job_id: str, ev: asyncio.Event) -> None:
        job = store.get_job_row(job_id)
        if not job:
            return
        platform = job["platform"]
        action = job["action"]
        cfg = load_settings()
        ctx = Ctx(settings=cfg, job_id=job_id)
        adapter = get_adapter(platform)
        lim = limits_for(platform, cfg)
        simulated = ctx.simulation or adapter is None

        try:
            job_extra = json.loads(job["extra"] or "{}")
        except (json.JSONDecodeError, TypeError):
            job_extra = {}

        store.set_job_status(job_id, "running", started=True)
        store.add_event(
            "info",
            f"开始执行：{PLATFORMS.get(platform, {}).get('name', platform)} · "
            f"{ACTION_LABELS.get(action, action)}（{'演练模式' if simulated else '真实执行'}）",
            platform=platform,
            job_id=job_id,
        )

        steps = [s for s in store.job_steps(job_id) if s["status"] == "approved"]
        if not steps:
            store.set_job_status(job_id, "done", finished=True)
            return

        results = {"ok": 0, "failed": 0, "skipped": 0}
        try:
            for idx, s in enumerate(steps):
                if self._panic or ev.is_set():
                    store.update_step(s["id"], status="skipped", detail="任务已中止", finished_at=store.now_iso())
                    results["skipped"] += 1
                    continue

                # 执行前二次核对配额
                if not simulated and store.usage_count(platform, 1) >= int(lim.get("per_hour", 15)):
                    store.update_step(
                        s["id"], status="skipped",
                        detail=f"小时配额已用尽（{int(lim.get('per_hour', 15))}/小时）",
                        finished_at=store.now_iso(),
                    )
                    results["skipped"] += 1
                    continue

                store.update_step(s["id"], status="running", started_at=store.now_iso())
                send_text = s["text"]
                if platform in ("wechat", "qq") and "{nick}" in send_text:
                    # 桌面端读不到对方昵称，用目标名兜底，避免把 {nick} 原样发出去
                    send_text = send_text.replace("{nick}", s["target"])
                try:
                    if adapter is None:
                        res = ExecResult(ok=False, detail=f"平台 {platform} 适配器缺失")
                    elif ctx.simulation:
                        res = adapter.simulate(action, s["target"], send_text, job_extra)
                    else:
                        res = await adapter.execute(action, s["target"], send_text, job_extra, ctx)
                except Exception as exc:  # 适配器异常不应中断整批
                    res = ExecResult(ok=False, detail=f"适配器异常：{exc}")

                store.update_step(
                    s["id"],
                    status="ok" if res.ok else "failed",
                    detail=res.detail,
                    screenshot=res.screenshot,
                    finished_at=store.now_iso(),
                )
                store.touch_contact(platform, s["target"], action, "ok" if res.ok else "failed")
                results["ok" if res.ok else "failed"] += 1
                store.add_event(
                    "info" if res.ok else "error",
                    f"{'✓' if res.ok else '✗'} {s['target']} — {res.detail}",
                    platform=platform,
                    job_id=job_id,
                )

                if idx < len(steps) - 1 and not ev.is_set():
                    if simulated:
                        delay = random.uniform(0.25, 0.7)
                    else:
                        lo, hi = float(lim.get("delay_min", 5)), float(lim.get("delay_max", 12))
                        if job_extra.get("auto_follow"):
                            lo, hi = lo * 1.5, hi * 1.5
                        delay = random.uniform(lo, hi)
                    try:
                        await asyncio.wait_for(ev.wait(), timeout=min(delay, 60))
                    except asyncio.TimeoutError:
                        pass
        finally:
            cancelled = self._panic or ev.is_set()
            final = "cancelled" if cancelled else ("failed" if results["ok"] == 0 and results["failed"] else "done")
            store.set_job_status(job_id, final, finished=True)
            store.add_event(
                "warn" if cancelled else "info",
                f"任务结束：成功 {results['ok']} / 失败 {results['failed']} / 跳过 {results['skipped']}",
                platform=platform,
                job_id=job_id,
            )
            self._cancel.pop(job_id, None)

    # ------------------------------------------------------------ 视图
    def view(self, job_id: str) -> dict[str, Any]:
        job = store.get_job_row(job_id)
        if not job:
            raise ValueError("任务不存在")
        steps = store.job_steps(job_id)
        stats = {"total": len(steps), "pending": 0, "approved": 0, "ok": 0, "failed": 0, "rejected": 0, "skipped": 0}
        for s in steps:
            stats[s["status"]] = stats.get(s["status"], 0) + 1
        stats.setdefault("running", 0)
        meta = PLATFORMS.get(job["platform"], {})
        return {
            "id": job["id"],
            "platform": job["platform"],
            "platform_name": meta.get("name", job["platform"]),
            "action": job["action"],
            "action_label": ACTION_LABELS.get(job["action"], job["action"]),
            "mode": job["mode"],
            "status": job["status"],
            "message": job["message"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
            "stats": stats,
            "steps": [
                {
                    "id": s["id"],
                    "index": s["idx"],
                    "target": s["target"],
                    "text": s["text"],
                    "risk": s["risk"],
                    "reason": s["reason"],
                    "status": s["status"],
                    "detail": s["detail"],
                    "screenshot": s["screenshot"],
                    "started_at": s["started_at"],
                    "finished_at": s["finished_at"],
                }
                for s in steps
            ],
        }

    def job_summary(self, job_id: str) -> dict[str, Any]:
        v = self.view(job_id)
        v.pop("steps", None)
        return v


engine = Engine()
