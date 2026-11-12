"""环境自检与一键集成（目前是 Chrome MCP）。

「一键安装 Chrome MCP」实际做四件事：
    1. 探测 Node.js / Chrome / Edge
    2. 全局安装 @playwright/mcp（已装则跳过）
    3. 把浏览器 MCP 写进 Claude Code 的 ~/.claude.json
    4. 真起一次 stdio 握手，确认 tools/list 能返回工具（不是「装完就算完」）

所有步骤都返回结构化的中文说明，界面直接展示。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .settings import ROOT

CLAUDE_JSON = Path.home() / ".claude.json"
NPM_PREFIX = Path(os.environ.get("APPDATA", str(Path.home()))) / "npm"
PLAYWRIGHT_CLI = NPM_PREFIX / "node_modules" / "@playwright" / "mcp" / "cli.js"
PKG = "@playwright/mcp"

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"),
]
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def _first_existing(paths: list[str]) -> str:
    for p in paths:
        if p and Path(p).is_file():
            return p
    return ""


def node_path() -> str:
    # 显式要 .exe，避免 shutil.which 返回 node.EXE 这种大小写差异导致配置反复被判定为「已变更」
    return shutil.which("node.exe") or shutil.which("node") or ""


def npm_path() -> str:
    return shutil.which("npm.cmd") or shutil.which("npm") or ""


def chrome_path() -> str:
    return _first_existing(CHROME_CANDIDATES)


def edge_path() -> str:
    return _first_existing(EDGE_CANDIDATES)


def load_claude_config() -> dict[str, Any]:
    if not CLAUDE_JSON.exists():
        return {}
    try:
        return json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def registered_servers() -> dict[str, Any]:
    return (load_claude_config().get("mcpServers") or {})


def status() -> dict[str, Any]:
    cfg = registered_servers()
    reg = cfg.get("playwright") or {}
    return {
        "node": {"ok": bool(node_path()), "detail": node_path() or "未找到 node"},
        "npm": {"ok": bool(npm_path()), "detail": npm_path() or "未找到 npm"},
        "chrome": {
            "ok": bool(chrome_path()),
            "detail": chrome_path() or (f"未装 Chrome，将回退 Edge：{edge_path()}" if edge_path() else "未找到 Chrome / Edge"),
        },
        "package": {
            "ok": PLAYWRIGHT_CLI.is_file(),
            "detail": str(PLAYWRIGHT_CLI) if PLAYWRIGHT_CLI.is_file() else "尚未安装 @playwright/mcp",
        },
        "registered": {
            "ok": bool(reg),
            "detail": f"已注册到 {CLAUDE_JSON}" if reg else "尚未写入 Claude Code 配置",
        },
        "servers": sorted(cfg.keys()),
    }


def _run(cmd: list[str], timeout: int = 240) -> tuple[bool, str]:
    env = dict(os.environ)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(k, None)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return False, f"命令超时（{timeout}s）"
    except OSError as exc:
        return False, f"命令无法执行：{exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()[-1500:]


def _npm_install() -> tuple[bool, str]:
    node_dir = Path(node_path()).parent if node_path() else None
    npm = npm_path()
    if not npm:
        return False, "未找到 npm，请先安装 Node.js"
    # 官方源在国内经常卡住，先试镜像再回退官方
    registries = [
        "https://registry.npmmirror.com",
        "https://registry.npmjs.org",
    ]
    last = ""
    for reg in registries:
        ok, out = _run(
            ["cmd", "/c", npm, "install", "-g", f"{PKG}@latest",
             "--registry", reg, "--no-fund", "--no-audit"],
            timeout=300,
        )
        if ok:
            return True, f"已从 {reg} 安装 {PKG}"
        last = out
        if "EACCES" in out or "EPERM" in out:
            break
    return False, last or "安装失败"


def _write_claude_config() -> tuple[bool, str]:
    if not CLAUDE_JSON.exists():
        return False, f"找不到 {CLAUDE_JSON}，请先运行一次 claude 完成初始化"
    node = node_path()
    if not node:
        return False, "缺少 node，无法写入启动命令"
    if not PLAYWRIGHT_CLI.is_file():
        return False, "缺少 cli.js，安装未完成"

    data = load_claude_config()
    servers = data.setdefault("mcpServers", {})
    entry = {
        "type": "stdio",
        "command": node,
        "args": [str(PLAYWRIGHT_CLI), "--browser", "chrome"],
        "env": {},
    }

    def _same(old: Any, new: dict[str, Any]) -> bool:
        if not isinstance(old, dict):
            return False
        if (old.get("type") or "stdio") != new["type"]:
            return False
        if (old.get("command") or "").lower() != new["command"].lower():
            return False
        return [str(a).lower() for a in (old.get("args") or [])] == [
            str(a).lower() for a in new["args"]
        ]

    if _same(servers.get("playwright"), entry):
        return True, "配置已是最新，无需改动"
    servers["playwright"] = entry
    try:
        if not CLAUDE_JSON.with_suffix(".json.bak").exists():
            shutil.copy2(CLAUDE_JSON, CLAUDE_JSON.with_suffix(".json.bak"))
        CLAUDE_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return False, f"写入失败：{exc}"
    return True, "已写入 Claude Code 配置（mcpServers.playwright）"


def _probe_mcp(timeout: int = 75) -> tuple[bool, str, int]:
    """真起一次 stdio 握手，返回 (成功, 说明, 工具数)。"""
    node = node_path()
    if not node or not PLAYWRIGHT_CLI.is_file():
        return False, "缺少 node 或 cli.js", 0
    try:
        proc = subprocess.Popen(
            [node, str(PLAYWRIGHT_CLI), "--browser", "chrome"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        return False, f"启动失败：{exc}", 0

    tools: list[Any] = []
    done = threading.Event()

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2:
                tools.extend((msg.get("result") or {}).get("tools") or [])
                done.set()
                break

    threading.Thread(target=reader, daemon=True).start()
    try:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "setup-check", "version": "1"}},
        }) + "\n")
        proc.stdin.flush()
        time.sleep(1.5)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
        proc.stdin.flush()
        done.wait(timeout)
    except (OSError, ValueError) as exc:
        return False, f"握手失败：{exc}", 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    if not tools:
        return False, "没有返回工具列表，可能被安全软件拦截", 0
    return True, f"握手成功，可用浏览器工具 {len(tools)} 个", len(tools)


def install(force: bool = False) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    t0 = time.time()

    def add(name: str, ok: bool, detail: str) -> None:
        steps.append({"name": name, "ok": ok, "detail": detail})

    node = node_path()
    if not node:
        add("检查 Node.js", False, "未找到 node，请先安装 Node.js 18+")
        return {"ok": False, "steps": steps, "detail": "缺少 Node.js"}
    add("检查 Node.js", True, node)

    chrome = chrome_path()
    if chrome:
        add("检查 Chrome", True, chrome)
    elif edge_path():
        add("检查 Chrome", True, f"未装 Chrome，将使用 Edge：{edge_path()}")
    else:
        add("检查 Chrome", False, "未找到 Chrome 或 Edge")
        return {"ok": False, "steps": steps, "detail": "缺少浏览器"}

    if PLAYWRIGHT_CLI.is_file() and not force:
        add("安装 @playwright/mcp", True, "已安装，跳过（勾选「重新安装」可强制覆盖）")
    else:
        ok, detail = _npm_install()
        add("安装 @playwright/mcp", ok, detail)
        if not ok:
            return {"ok": False, "steps": steps, "detail": "npm 安装失败"}

    ok, detail = _write_claude_config()
    add("注册到 Claude Code", ok, detail)
    if not ok:
        return {"ok": False, "steps": steps, "detail": "写入配置失败"}

    ok, detail, n = _probe_mcp()
    add("连通性验证", ok, detail)

    total = round(time.time() - t0, 1)
    return {
        "ok": all(s["ok"] for s in steps),
        "steps": steps,
        "tools": n,
        "elapsed": total,
        "detail": "Chrome MCP 已就绪，重启 Claude Code 后生效" if ok else "安装完成但验证未通过",
    }
