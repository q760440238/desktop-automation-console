"""本机 MCP 服务：把「自动加好友/发消息」引擎暴露成 Claude Code 可调用的工具。

传输：stdio，逐行 JSON-RPC 2.0。
设计取向：MCP 只负责「出计划 / 查状态 / 触发已批准的执行」，审批动作留在图形界面，
这样 Claude 不能绕过人工确认去群发。
启动：python -m app.mcp_server
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

from .settings import load_settings

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "auto-social-console", "version": "1.0.0"}


def _base() -> str:
    cfg = load_settings().get("server", {})
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8765))
    return f"http://{host}:{port}"


def _http(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = _base() + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"detail": str(exc)}
        return {"ok": False, "detail": payload.get("detail", str(exc))}
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "detail": f"控制台服务未启动（{_base()}）：{exc.reason}。请先运行 python -m app.server",
        }


# ---------------------------------------------------------------- 工具定义
TOOLS: list[dict[str, Any]] = [
    {
        "name": "platform_status",
        "description": "查看六个平台（微信/QQ/抖音/微博/B站/小红书）的连接状态、当前模式、急停状态与待审批数量。任何自动化开始前先调用它。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "plan_social_task",
        "description": (
            "生成一份执行计划（不会执行任何操作）。会按平台限流、去重窗口、禁用词、域名白名单逐条校验目标，"
            "返回可执行与被拦截的条目。生成后必须把计划原样展示给用户，等待用户在控制台里批准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat", "wecom", "qq", "douyin", "kuaishou", "weibo", "bilibili", "xiaohongshu", "zhihu", "tieba"],
                    "description": "目标平台",
                },
                "action": {
                    "type": "string",
                    "enum": ["send_message", "add_friend", "join_group", "follow"],
                    "description": "动作；微信只支持 send_message，QQ 支持 add_friend/join_group/send_message，其余平台支持 follow/send_message",
                },
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "目标列表：好友备注/群名、QQ 号/群号、或平台主页链接/账号",
                },
                "message": {
                    "type": "string",
                    "description": "消息内容，支持 {nick} 占位符；follow 动作可留空",
                },
            },
            "required": ["platform", "action", "targets"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_tasks",
        "description": "列出最近的自动化任务及其状态统计。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_task",
        "description": "读取单个任务的完整步骤状态（含每条目标的成败与截图路径）。",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_task",
        "description": "执行一个【已被人工批准】的任务。若仍有待审批步骤会直接拒绝。执行过程受频率限制约束，可用 cancel_task 中止。",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel_task",
        "description": "中止正在运行的任务；剩余步骤标记为跳过。",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "approve_task",
        "description": (
            "批准任务的全部待审步骤。仅在 settings.safety.require_approval 为 false（自动模式）时可用；"
            "默认配置下会被拒绝，必须由用户在图形界面里点击批准。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "open_platform",
        "description": "打开某平台：网页平台会启动带本地登录态的浏览器，桌面平台会启动对应客户端。用于首次登录或掉线重连。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["wechat", "wecom", "qq", "douyin", "kuaishou", "weibo", "bilibili", "xiaohongshu", "zhihu", "tieba"],
                }
            },
            "required": ["platform"],
            "additionalProperties": False,
        },
    },
    {
        "name": "panic",
        "description": "急停开关：立刻中止所有正在运行的任务并阻止新任务启动。on=false 解除。",
        "inputSchema": {
            "type": "object",
            "properties": {"on": {"type": "boolean", "default": True}},
            "additionalProperties": False,
        },
    },
]


def _text(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}


def _err(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}], "isError": True}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "platform_status":
        data = _http("/api/health")
        if data.get("ok") is False:
            return _err(str(data.get("detail", "无法读取状态")))
        rows = [
            {
                "平台": p["name"],
                "key": p["key"],
                "就绪": p["health"]["ready"],
                "状态": p["health"]["detail"],
                "可用动作": list(p["actions"]),
            }
            for p in data.get("platforms", [])
        ]
        return _text(
            {
                "模式": data.get("mode"),
                "演练模式": data.get("simulation"),
                "急停": data.get("panic"),
                "运行中": data.get("running"),
                "待审批步骤": data.get("pending"),
                "平台": rows,
            }
        )

    if name == "plan_social_task":
        body = {
            "platform": args.get("platform"),
            "action": args.get("action"),
            "targets": args.get("targets", []),
            "message": args.get("message", ""),
        }
        data = _http("/api/plan", "POST", body)
        if data.get("ok") is False:
            return _err(str(data.get("detail", "生成计划失败")))
        job = data.get("job", {})
        plan = data.get("plan", [])
        blocked = [p for p in plan if not p.get("allowed")]
        return _text(
            {
                "job_id": job.get("id"),
                "平台": job.get("platform_name"),
                "动作": job.get("action_label"),
                "可执行": len(plan) - len(blocked),
                "被拦截": [{"target": p["target"], "原因": p["reason"]} for p in blocked],
                "提示": "计划已入库，需用户在控制台审批后才能执行。",
            }
        )

    if name == "list_tasks":
        data = _http(f"/api/jobs?limit={int(args.get('limit', 10))}")
        return _text(data.get("jobs", data))

    if name == "get_task":
        data = _http(f"/api/jobs/{args.get('job_id', '')}")
        return _text(data)

    if name == "run_task":
        data = _http(f"/api/jobs/{args.get('job_id', '')}/run", "POST", {})
        if data.get("ok") is False:
            return _err(str(data.get("detail")))
        return _text({"job_id": args.get("job_id"), "状态": "已开始执行", "详情": data.get("job", {}).get("status")})

    if name == "cancel_task":
        data = _http(f"/api/jobs/{args.get('job_id', '')}/stop", "POST", {})
        if data.get("ok") is False:
            return _err(str(data.get("detail")))
        return _text({"job_id": args.get("job_id"), "状态": "已请求中止"})

    if name == "approve_task":
        cfg = load_settings()
        if cfg.get("safety", {}).get("require_approval", True):
            return _err(
                f"当前为人工审批模式，MCP 不允许自行批准。请在控制台 {_base().rstrip('/')} 中点击「全部批准」。"
            )
        data = _http(f"/api/jobs/{args.get('job_id', '')}/approve", "POST", {"all": True})
        if data.get("ok") is False:
            return _err(str(data.get("detail")))
        return _text({"job_id": args.get("job_id"), "状态": "已批准"})

    if name == "open_platform":
        data = _http(f"/api/adapters/{args.get('platform', '')}/open", "POST", {})
        if data.get("ok") is False:
            return _err(str(data.get("detail", "打开失败")))
        return _text({"平台": args.get("platform"), "结果": data.get("detail", "已打开")})

    if name == "panic":
        data = _http("/api/panic", "POST", {"on": bool(args.get("on", True))})
        return _text({"急停": data.get("panic")})

    return _err(f"未知工具：{name}")


# ---------------------------------------------------------------- 协议
def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    mid = msg.get("id")
    is_notification = "id" not in msg

    if method == "initialize":
        req_version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        result = {
            "protocolVersion": req_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "这是本机「社交自动化控制台」的桥接服务。使用规则："
                "1) 先 platform_status 看连接状态；2) plan_social_task 只生成计划，绝不自动执行；"
                "3) 把计划与拦截原因如实告诉用户，等待用户在控制台审批；4) 只有用户明确要求时才 run_task；"
                "5) 遇到验证码、风控提示、账号异常立即 panic 并停下来告知用户；6) 不要对陌生人批量群发。"
            ),
        }
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if is_notification:
        return None  # notifications/initialized 等无需响应

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            result = call_tool(name, args)
        except Exception as exc:  # 工具异常必须转成 MCP 错误内容，不能让服务退出
            result = _err(f"工具执行异常：{exc}")
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": mid, "result": {key: []}}

    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    # MCP 的 stdio 传输约定是 UTF-8。Windows 下默认用 GBK(cp936) 编码，
    # 中文 JSON 会变成非 UTF-8 字节，客户端直接解析失败，所以必须先强制改编码。
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    stdin, stdout = sys.stdin, sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


if __name__ == "__main__":
    main()
