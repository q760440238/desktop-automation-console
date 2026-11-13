"""QQ 全链路自测：发消息 / 加好友 / 加群。

只用安全目标：
- 发消息 → 「我的电脑」（发给自己）
- 加好友 / 加群 → 用不存在的号码，验证搜索与视觉路径能正确走完并给出结论
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"E:\AI工具\自动加好友发消息工具")
BASE = "http://127.0.0.1:18765"


def post(path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "detail": json.loads(e.read()).get("detail")}


def get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def clear_contact(platform: str, target: str) -> int:
    c = sqlite3.connect(ROOT / "data" / "agent.db")
    n = c.execute(
        "DELETE FROM contacts WHERE platform=? AND target=?", (platform, target)
    ).rowcount
    c.commit()
    return n


def run_case(name: str, platform: str, action: str, target: str, message: str = "") -> None:
    print(f"\n=== {name} ===")
    plan = post(
        "/api/plan",
        {"platform": platform, "action": action, "targets": [target], "message": message},
    )
    if not plan.get("job"):
        print("  计划失败:", plan.get("detail"))
        return
    job_id = plan["job"]["id"]
    post(f"/api/jobs/{job_id}/approve", {"all": True})
    run = post(f"/api/jobs/{job_id}/run", {})
    if not run.get("ok", True) and run.get("detail"):
        print("  执行被拒:", run["detail"])
        return
    for _ in range(24):
        time.sleep(5)
        d = get(f"/api/jobs/{job_id}")["job"]
        if d["status"] not in ("running", "approved"):
            break
    print(f"  状态={d['status']} ok={d['stats']['ok']} failed={d['stats']['failed']}")
    for s in d["steps"]:
        print(f"  [{s['status']}] {s['detail']}")


def main() -> int:
    print("清理测试用的去重记录:", clear_contact("qq", "我的电脑"))
    run_case("发消息 → 我的电脑（发给自己）", "qq", "send_message", "我的电脑", "自测消息，请忽略")
    run_case("加好友 → 不存在的号码", "qq", "add_friend", "99999999999", "你好")
    run_case("加群 → 不存在的群号", "qq", "join_group", "999999999", "你好")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
