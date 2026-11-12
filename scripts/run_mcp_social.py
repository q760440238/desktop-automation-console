"""Claude Code 的 MCP 入口：把项目目录加入 sys.path 后启动社交自动化 MCP 服务。

这样注册 MCP 时不需要依赖「当前工作目录」，在任何目录启动 Claude Code 都能用。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
