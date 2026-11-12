"""MCP 冒烟测试：以真实 stdio 客户端身份调用 social-console 的工具。

用法：python scripts/mcp_smoke.py
前置：控制台服务已在 config/settings.json 指定的端口运行。
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


class Client:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [PY, str(ROOT / "scripts" / "run_mcp_social.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.responses: dict[int, dict] = {}
        self._next = 1
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg:
                self.responses[msg["id"]] = msg

    def send(self, method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        mid = None
        if not notify:
            mid = self._next
            self._next += 1
            payload["id"] = mid
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        deadline = time.time() + 40
        while time.time() < deadline and mid not in self.responses:
            time.sleep(0.05)
        return self.responses.get(mid)

    def call(self, name: str, args: dict) -> dict:
        resp = self.send("tools/call", {"name": name, "arguments": args}) or {}
        return resp.get("result", {})

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def text_of(result: dict) -> str:
    parts = result.get("content") or []
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict))


def main() -> int:
    c = Client()
    try:
        init = c.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1"},
        })
        assert init and "result" in init, f"initialize 失败: {init}"
        print("✓ initialize:", init["result"]["serverInfo"]["name"])
        c.send("notifications/initialized", notify=True)

        tools = (c.send("tools/list") or {}).get("result", {}).get("tools", [])
        print(f"✓ tools/list: {len(tools)} 个工具 -> {[t['name'] for t in tools]}")
        assert len(tools) >= 8

        status = c.call("platform_status", {})
        print("✓ platform_status:")
        print("   " + text_of(status).replace("\n", "\n   ")[:600])

        plan = c.call("plan_social_task", {
            "platform": "wechat",
            "action": "send_message",
            "targets": ["文件传输助手", "测试联系人A"],
            "message": "冒烟测试，请忽略 {nick}",
        })
        print("✓ plan_social_task:")
        plan_text = text_of(plan)
        print("   " + plan_text.replace("\n", "\n   ")[:500])
        job_id = json.loads(plan_text).get("job_id")

        # 未批准就执行必须被拒绝
        bad = c.call("run_task", {"job_id": job_id})
        print("✓ run_task（未批准，应失败）:", bad.get("isError"), "|", text_of(bad)[:120])
        assert bad.get("isError") is True, "未批准的任务竟然可以执行，安全约束失效"

        approve = c.call("approve_task", {"job_id": job_id})
        print("✓ approve_task（人工审批模式，应被拒）:", approve.get("isError"), "|", text_of(approve)[:120])
        assert approve.get("isError") is True, "MCP 竟然可以自行批准，安全约束失效"

        print("\n全部断言通过")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
