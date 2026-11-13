"""检测配置的大模型是否支持图片输入（视觉）。"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(r"E:\AI工具\自动加好友发消息工具")


def load_cfg() -> dict:
    cfg = json.loads((ROOT / "config" / "ai.json").read_text(encoding="utf-8"))
    return cfg


def http(url: str, payload: dict | None, key: str, timeout: int = 90) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode(errors="replace")
        return {"__error__": f"HTTP {e.code}", "body": body}
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e)}


def main() -> int:
    cfg = load_cfg()
    base = cfg["base_url"].rstrip("/")
    key = cfg.get("api_key", "")
    model = cfg.get("model", "")

    print(f"base_url = {base}")
    print(f"model    = {model}")

    print("\n=== 可用模型列表 ===")
    models = http(f"{base}/models", None, key)
    if "__error__" in models:
        print("拿不到模型列表:", models)
    else:
        ids = [m.get("id") for m in models.get("data", [])]
        print(f"共 {len(ids)} 个")
        for i in ids[:20]:
            print("   ", i)
        want = "deepseek-v4.1-flash-1017"
        print(f"\n配置里写的 {want!r} 在列表里: {want in ids}")

    img = ROOT / "data" / "screenshots" / "qq_window.png"
    if not img.exists():
        print("\n没有测试图，跳过视觉测试")
        return 0
    b64 = base64.b64encode(img.read_bytes()).decode()
    print(f"\n=== 视觉测试（{img.name}, {len(b64)//1024}KB base64）===")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图里是什么软件？屏幕上能看到哪些中文文字？简短回答。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 200,
    }
    res = http(f"{base}/chat/completions", payload, key)
    if "__error__" in res:
        print("视觉调用失败:", res["__error__"])
        print("响应体:", res.get("body", "")[:300])
        return 1
    msg = res.get("choices", [{}])[0].get("message", {})
    print("模型回复:", (msg.get("content") or "")[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
