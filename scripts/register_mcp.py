"""把 MCP 服务写入 Claude Code 的全局配置（~/.claude.json）。

为什么要这个脚本：`claude mcp add` 会把 `-m`、`--browser` 这类参数当成自己的选项，
而 .cmd 包装脚本又无法被 CreateProcess 直接启动，所以直接写配置最稳。

用法：
    python scripts/register_mcp.py          # 写入
    python scripts/register_mcp.py --check   # 只检查
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_JSON = Path.home() / ".claude.json"

PYTHON = Path(sys.executable)
NODE = Path(shutil.which("node.exe") or shutil.which("node") or "node.exe")
NPM_PREFIX = Path(os.environ.get("APPDATA", str(Path.home()))) / "npm"
PLAYWRIGHT_CLI = NPM_PREFIX / "node_modules" / "@playwright" / "mcp" / "cli.js"


def desired() -> dict[str, dict]:
    return {
        "windows-desktop": {
            "type": "stdio",
            "command": str(PYTHON),
            "args": ["-m", "windows_mcp", "serve", "--transport", "stdio"],
            "env": {},
        },
        "playwright": {
            "type": "stdio",
            "command": str(NODE),
            "args": [str(PLAYWRIGHT_CLI), "--browser", "chrome"],
            "env": {},
        },
        "social-console": {
            "type": "stdio",
            "command": str(PYTHON),
            "args": [str(ROOT / "scripts" / "run_mcp_social.py")],
            "env": {},
        },
    }


def main() -> int:
    check_only = "--check" in sys.argv
    if not CLAUDE_JSON.exists():
        print(f"找不到 {CLAUDE_JSON}，请先运行一次 claude 完成初始化")
        return 1
    data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    servers = data.setdefault("mcpServers", {})
    want = desired()

    changed = []
    for name, cfg in want.items():
        if servers.get(name) != cfg:
            changed.append(name)
            if not check_only:
                servers[name] = cfg

    if check_only:
        print("需要更新的服务：", changed or "无")
        for name, cfg in want.items():
            print(f"  {name}: {cfg['command']} {' '.join(cfg['args'])}")
        return 0

    if changed:
        backup = CLAUDE_JSON.with_suffix(".json.bak")
        if not backup.exists():
            shutil.copy2(CLAUDE_JSON, backup)
        CLAUDE_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已更新：", changed or "无变化")
    print(f"配置路径：{CLAUDE_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
