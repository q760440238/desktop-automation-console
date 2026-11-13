"""契约矩阵测试：每个平台声明的每个动作，都要能生成计划。

用法：python scripts/contract_check.py
前置：控制台服务在 18765 运行。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18765"

# 每个平台用自己域名的样例，避免被域名白名单拦掉（拦掉是正确行为，但测不到动作本身）
SAMPLE = {
    "douyin": "https://www.douyin.com/user/MS4wLjABAAAA_test",
    "kuaishou": "https://www.kuaishou.com/profile/3xtest123",
    "weibo": "https://weibo.com/u/1234567890",
    "bilibili": "https://space.bilibili.com/123456",
    "xiaohongshu": "https://www.xiaohongshu.com/user/profile/abc123",
    "zhihu": "https://www.zhihu.com/people/test-user",
    "tieba": "https://tieba.baidu.com/f?kw=test",
}


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return {"ok": False, "detail": json.loads(exc.read()).get("detail")}
        except Exception:
            return {"ok": False, "detail": str(exc)}


def main() -> int:
    with urllib.request.urlopen(BASE + "/api/health", timeout=20) as resp:
        health = json.loads(resp.read())

    post("/api/settings", {"patch": {"simulation": True}})
    created: list[str] = []
    failures: list[tuple[str, str, str]] = []
    total = 0
    try:
        for plat in health["platforms"]:
            for action in plat["actions"]:
                total += 1
                if action == "join_group":
                    target = "123456"
                elif action == "add_friend":
                    target = "10001"
                else:
                    target = SAMPLE.get(plat["key"], "测试目标")
                if action == "comment":
                    target = SAMPLE.get(plat["key"], "测试目标")
                elif plat["kind"] == "web":
                    target = SAMPLE.get(plat["key"], "测试目标")
                else:
                    target = "测试目标"
                res = post(
                    "/api/plan",
                    {"platform": plat["key"], "action": action, "targets": [target], "message": "契约测试"},
                )
                ok = bool(res.get("job"))
                if ok:
                    created.append(res["job"]["id"])
                detail = str(res.get("detail", ""))
                print(f"{plat['name']:<6} {action:<12} {'OK' if ok else 'FAIL ' + detail[:40]}")
                if not ok:
                    failures.append((plat["key"], action, detail))
    finally:
        # 用例产生的计划必须自己清掉，否则会在真实模式里留下一堆「测试目标」待审任务
        for job_id in created:
            post(f"/api/jobs/{job_id}/reject", {"all": True})
        post("/api/settings", {"patch": {"simulation": False}})
        print(f"已清理 {len(created)} 条测试计划")

    print("-" * 40)
    print(f"共 {total} 个 平台×动作 组合，失败 {len(failures)}")
    for f in failures:
        print("  ", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
