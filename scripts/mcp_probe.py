"""一次性探测：启动某个 MCP server，取回 tools/list。"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time

PY = sys.executable


def probe(cmd: list[str], timeout: float = 90.0) -> list[dict]:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    result: dict[str, object] = {}
    err_buf: list[str] = []

    def _reader() -> None:
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
                result["tools"] = msg.get("result", {}).get("tools", [])
                break

    def _err_reader() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            err_buf.append(line.rstrip())

    threading.Thread(target=_reader, daemon=True).start()
    threading.Thread(target=_err_reader, daemon=True).start()

    assert proc.stdin is not None
    proc.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "0.1"},
                },
            }
        )
        + "\n"
    )
    proc.stdin.flush()
    time.sleep(2.0)
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
    proc.stdin.flush()

    deadline = time.time() + timeout
    while time.time() < deadline and "tools" not in result:
        time.sleep(0.4)
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    if "tools" not in result:
        print("NO TOOLS. stderr tail:", file=sys.stderr)
        for line in err_buf[-25:]:
            print("  ", line, file=sys.stderr)
        return []
    return result["tools"]  # type: ignore[return-value]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1:]
        if cmd[0].lower().endswith(".json"):
            cmd = json.loads(cmd[0])
    else:
        cmd = [PY, "-m", "windows_mcp", "serve", "--transport", "stdio"]
    print("CMD:", cmd)
    tools = probe(cmd)
    print(f"共 {len(tools)} 个工具")
    for t in tools:
        schema = t.get("inputSchema") or {}
        props = list((schema.get("properties") or {}).keys())
        print(f"- {t['name']}: {(t.get('description') or '')[:110]}")
        if props:
            print(f"    参数: {props}")
