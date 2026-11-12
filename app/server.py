"""FastAPI 服务：/api/* 给界面与 MCP 用，/ 托管前端。

启动：python -m app.server
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, guard, setup_tools, store
from .adapters import close_all, get_adapter, health_all
from .autopilot import autopilot
from .engine import engine
from .schemas import ACTION_LABELS, PLATFORMS, ApproveRequest, PlanRequest, Platform, SettingsPatch
from .settings import WEB_DIR, load_settings, save_settings

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.conn()
    yield
    try:
        await autopilot.stop("服务关闭")
    except Exception:
        pass
    await close_all()


class UTF8JSONResponse(JSONResponse):
    """显式声明 charset，避免 PowerShell 等客户端按本地代码页解码导致中文乱码。"""

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="桌面自动化控制台",
    version=VERSION,
    lifespan=lifespan,
    default_response_class=UTF8JSONResponse,
)


class PanicBody(BaseModel):
    on: bool = True


class AISettingsBody(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    thinking: str | None = None
    temperature: float | None = None
    api_key: str | None = None


class AITestBody(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class AIDraftBody(BaseModel):
    brief: str
    platform: str = ""
    action: str = "send_message"
    extra: str = ""


class SetupBody(BaseModel):
    force: bool = False


class DiscoverBody(BaseModel):
    platform: Platform
    brief: str = ""
    limit: int = 10
    keywords: list[str] | None = None


class AutoStartBody(BaseModel):
    platform: Platform
    brief: str
    message: str
    action: str = "send_message"
    interval: int = 120
    limit: int = 5
    max_rounds: int = 0
    auto_follow: bool = False


@app.get("/api/auto/status")
async def auto_status() -> dict[str, Any]:
    return autopilot.status()


@app.post("/api/auto/start")
async def auto_start(body: AutoStartBody) -> dict[str, Any]:
    try:
        state = await autopilot.start(
            platform=body.platform,
            brief=body.brief,
            message=body.message,
            action=body.action,
            interval=body.interval,
            limit=body.limit,
            max_rounds=body.max_rounds,
            auto_follow=body.auto_follow,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **state}


@app.post("/api/auto/stop")
async def auto_stop() -> dict[str, Any]:
    return {"ok": True, **await autopilot.stop()}


@app.post("/api/discover")
async def discover(body: DiscoverBody) -> dict[str, Any]:
    """按方向找人：AI 生成搜索词 → 打开平台搜索页 → 抓候选。

    只读，不点关注、不发消息；返回的候选必须由用户在界面勾选后才会进入计划。
    """
    ad = get_adapter(body.platform)
    if ad is None:
        raise HTTPException(status_code=404, detail="未知平台")
    fn = getattr(ad, "discover", None)
    if fn is None:
        return {"ok": False, "detail": "桌面端平台不支持按方向找人（只能搜索已有联系人）", "candidates": []}

    name = PLATFORMS.get(body.platform, {}).get("name", body.platform)
    plan = ai.build_search_plan(body.brief, name, body.keywords)
    keywords = plan.get("keywords") or []
    limit = max(1, min(int(body.limit or 10), 20))

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    used: list[str] = []
    detail = ""
    for kw in keywords[:3]:
        try:
            res = await fn(kw, limit)
        except Exception as exc:  # 浏览器异常不应炸掉接口
            return {"ok": False, "detail": f"搜索失败：{exc}", "candidates": []}
        detail = res.get("detail") or detail
        if not res.get("ok"):
            if not collected:
                return {
                    "ok": False,
                    "detail": res.get("detail"),
                    "candidates": [],
                    "keywords": keywords,
                    "captcha": bool(res.get("captcha")),
                }
            break
        used.append(kw)
        for c in res.get("candidates") or []:
            url = str(c.get("url") or "")
            if url and url not in seen:
                seen.add(url)
                collected.append(c)
        if len(collected) >= limit:
            break

    for c in collected:
        c["contacted"] = store.last_contact(body.platform, str(c.get("url"))) is not None
    store.add_event(
        "info",
        f"按方向找人：{name} · 「{body.brief[:24]}」→ 关键词 {used or keywords} → {len(collected)} 个候选",
        platform=body.platform,
    )
    return {
        "ok": True,
        "candidates": collected[:limit],
        "keywords": used or keywords,
        "note": plan.get("note", ""),
        "detail": detail,
    }


@app.get("/api/setup/status")
def setup_status() -> dict[str, Any]:
    return setup_tools.status()


@app.post("/api/setup/chrome-mcp")
def setup_chrome_mcp(body: SetupBody) -> dict[str, Any]:
    """一键安装 Chrome MCP：装包 → 注册 → 真握手验证。

    同步执行（可能几十秒到两分钟），FastAPI 会把它放到线程池里跑，不阻塞事件循环。
    """
    result = setup_tools.install(force=body.force)
    level = "info" if result.get("ok") else "error"
    store.add_event(level, f"Chrome MCP 安装：{result.get('detail')}")
    return result


@app.get("/api/ai/settings")
async def ai_settings() -> dict[str, Any]:
    return ai.public_view()


@app.post("/api/ai/settings")
async def ai_settings_save(body: AISettingsBody) -> dict[str, Any]:
    ai.save_ai(body.model_dump(exclude_none=True))
    store.add_event("info", "AI 模型配置已更新")
    return ai.public_view()


@app.post("/api/ai/models")
async def ai_models(body: AITestBody) -> dict[str, Any]:
    return ai.fetch_models(body.base_url, body.api_key)


@app.post("/api/ai/test")
async def ai_test(body: AITestBody) -> dict[str, Any]:
    return ai.test_connection(body.model_dump(exclude_none=True))


@app.post("/api/ai/draft")
async def ai_draft(body: AIDraftBody) -> dict[str, Any]:
    res = ai.draft_message(body.brief, body.platform, body.action, body.extra)
    if res.get("ok"):
        store.add_event("info", f"AI 生成了文案（{res.get('model')}，思考深度 {res.get('thinking')}）")
    else:
        store.add_event("error", f"AI 生成失败：{res.get('detail')}")
    return res


@app.get("/api/health")
async def health() -> dict[str, Any]:
    cfg = load_settings()
    try:
        hs = await asyncio.wait_for(health_all(), timeout=8)
    except asyncio.TimeoutError:
        hs = {}
    platforms = []
    for key, meta in PLATFORMS.items():
        h = hs.get(key, {})
        platforms.append(
            {
                "key": key,
                "name": meta["name"],
                "kind": meta["kind"],
                "actions": meta["actions"],
                "action_labels": {a: ACTION_LABELS[a] for a in meta["actions"]},
                "target_label": meta["target_label"],
                "hint": meta["hint"],
                "color": meta["color"],
                "health": {"ready": bool(h.get("ready")), "detail": h.get("detail", "")},
            }
        )
    return {
        "ok": True,
        "version": VERSION,
        "mode": cfg.get("mode", "confirm"),
        "simulation": bool(cfg.get("simulation", True)),
        "panic": engine.panic,
        "running": engine.running_count(),
        "pending": engine.pending_count(),
        "platforms": platforms,
    }


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return load_settings()


@app.post("/api/settings")
async def patch_settings(body: SettingsPatch) -> dict[str, Any]:
    before = load_settings()
    merged = save_settings(body.patch)
    if before.get("mode") != merged.get("mode"):
        store.add_event("info", f"运行模式切换为 {merged.get('mode')}")
    if before.get("simulation") != merged.get("simulation"):
        store.add_event(
            "warn",
            "已切换到真实执行模式" if not merged.get("simulation") else "已切回演练模式",
        )
    return merged


@app.post("/api/plan")
async def plan(req: PlanRequest) -> dict[str, Any]:
    try:
        return engine.plan(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/jobs")
async def jobs(limit: int = 20) -> dict[str, Any]:
    rows = store.list_jobs(limit=max(1, min(limit, 100)))
    out = []
    for r in rows:
        meta = PLATFORMS.get(r["platform"], {})
        out.append(
            {
                "id": r["id"],
                "platform": r["platform"],
                "platform_name": meta.get("name", r["platform"]),
                "action": r["action"],
                "action_label": ACTION_LABELS.get(r["action"], r["action"]),
                "mode": r["mode"],
                "status": r["status"],
                "message": r["message"],
                "created_at": r["created_at"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "stats": {
                    "total": sum(r["stats"].values()),
                    "pending": r["stats"].get("pending", 0),
                    "approved": r["stats"].get("approved", 0),
                    "ok": r["stats"].get("ok", 0),
                    "failed": r["stats"].get("failed", 0),
                    "rejected": r["stats"].get("rejected", 0),
                    "skipped": r["stats"].get("skipped", 0),
                },
            }
        )
    return {"jobs": out}


@app.get("/api/jobs/{job_id}")
async def job_detail(job_id: str) -> dict[str, Any]:
    try:
        return {"job": engine.view(job_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/approve")
async def approve(job_id: str, body: ApproveRequest) -> dict[str, Any]:
    try:
        job = engine.approve(job_id, body.step_ids, body.all)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cfg = load_settings()
    if cfg.get("mode") == "auto" and job["stats"].get("approved", 0) > 0 and not job["stats"].get("pending"):
        try:
            await engine.run(job_id)
            job = engine.view(job_id)
        except ValueError:
            pass
    return {"job": job}


@app.post("/api/jobs/{job_id}/reject")
async def reject(job_id: str, body: ApproveRequest) -> dict[str, Any]:
    try:
        return {"job": engine.reject(job_id, body.step_ids, body.all)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/run")
async def run(job_id: str) -> dict[str, Any]:
    try:
        return {"job": await engine.run(job_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/stop")
async def stop(job_id: str) -> dict[str, Any]:
    try:
        return {"job": await engine.stop(job_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/panic")
async def panic(body: PanicBody) -> dict[str, Any]:
    return {"panic": engine.set_panic(body.on)}


@app.get("/api/events")
async def events(after: int = 0, limit: int = 200) -> dict[str, Any]:
    rows = store.list_events(after=after, limit=max(1, min(limit, 500)))
    return {"events": rows}


@app.get("/api/audit")
async def audit(limit: int = 100) -> dict[str, Any]:
    return {"rows": store.audit_rows(limit=max(1, min(limit, 500))), "today": store.today_counters()}


@app.post("/api/adapters/{platform}/open")
async def open_platform(platform: str) -> dict[str, Any]:
    ad = get_adapter(platform)
    if ad is None:
        raise HTTPException(status_code=404, detail="未知平台")
    try:
        fn = getattr(ad, "open_login", None)
        if fn is None:
            return {"ok": False, "detail": "该平台不支持打开，请手动启动应用"}
        res = fn()
        if asyncio.iscoroutine(res):
            res = await res
        return res if isinstance(res, dict) else {"ok": True, "detail": "已打开"}
    except Exception as exc:
        return {"ok": False, "detail": f"打开失败：{exc}"}


@app.post("/api/adapters/{platform}/probe")
async def probe(platform: str) -> dict[str, Any]:
    ad = get_adapter(platform)
    if ad is None:
        raise HTTPException(status_code=404, detail="未知平台")
    try:
        data = await ad.probe()
        return {"ok": "error" not in data, "data": data}
    except Exception as exc:
        return {"ok": False, "data": {"error": f"探测失败：{exc}"}}


@app.exception_handler(HTTPException)
async def http_exc(_request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})


# 前端最后挂载，保证 /api 优先匹配
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


def _port_free(host: str, port: int) -> bool:
    import socket

    sock = socket.socket()
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main() -> None:
    """启动控制台。

    --open  启动就绪后自动打开默认浏览器（start.bat 用这个）。
    若端口已被占用，说明控制台已在运行，直接打开浏览器后退出，避免报错吓人。
    """
    import sys
    import threading
    import webbrowser

    import uvicorn

    from .settings import LOG_DIR

    # pythonw 启动时 stdout/stderr 是 None，任何 print 都会抛异常导致静默退出。
    if sys.stdout is None or sys.stderr is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logfile = open(LOG_DIR / "server.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or logfile
        sys.stderr = sys.stderr or logfile

    cfg = load_settings()
    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = int(cfg.get("server", {}).get("port", 18765))
    url = f"http://{host}:{port}/"
    want_open = "--open" in sys.argv

    if not _port_free(host, port):
        print(f"端口 {port} 已被占用，控制台应该已经在运行：{url}")
        if want_open:
            webbrowser.open(url)
        return

    if want_open:
        threading.Timer(1.8, lambda: webbrowser.open(url)).start()

    print(f"桌面自动化控制台：{url}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
