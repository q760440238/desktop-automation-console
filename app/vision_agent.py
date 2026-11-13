"""视觉代理：让多模态大模型看窗口截图，直接决定点哪里/输入什么。

和 OCR 的区别：OCR 只能定位文字，这个能理解界面结构、判断当前状态、
决定下一步动作，并且每步都能重新看一遍（闭环）。

模型只负责「看 + 决策」，执行由本机完成（点击/粘贴/按键），动作集合是封闭的。
"""
from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any

from PIL import Image, ImageGrab

try:
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover
    win32gui = None

from . import ai

ALLOWED = {"click", "type", "key", "scroll", "done", "fail"}

SYSTEM = """你是桌面操作助手。每一步你只会看到目标应用当前窗口的截图。
任务：{task}

只能输出一个 JSON 对象，不要 markdown，不要多余文字：
{{"thought":"一句话说明你看到的和打算做什么","action":"click|type|key|scroll|done|fail",
  "x":整数,"y":整数,"text":"要输入的文字","key":"enter|esc|tab|ctrl+f|ctrl+a|ctrl+v","dy":整数}}

规则：
- 坐标是截图像素，左上角是 (0,0)，右下角是 ({w},{h})。
- 一次只做一个动作，做完会再给你新的截图。
- 要输入中文时用 type，不要逐字模拟按键。
- 找不到目标、界面不对、或者任务已经完成：用 done 或 fail，并在 thought 里说明。
- 不要点击与任务无关的东西。"""


def _capture(rect: tuple[int, int, int, int]) -> Image.Image:
    return ImageGrab.grab(bbox=rect, all_screens=True)


def _b64(img: Image.Image, max_side: int = 1280) -> str:
    im = img.convert("RGB")
    if max(im.size) > max_side:
        ratio = max_side / max(im.size)
        im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    for pattern in (r"\{.*\}", r"\{[\s\S]*"):
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _ask(img: Image.Image, system: str, user: str, timeout: int = 180) -> str:
    """把截图丢给多模态模型，返回原始文本。"""
    cfg = ai.load_ai()
    base = (cfg.get("base_url") or "").rstrip("/")
    model = cfg.get("model") or ""
    key = cfg.get("api_key") or ""
    if not base or not model:
        raise RuntimeError("没有配置 AI 模型")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system + "\n\n" + user},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(img)}"}},
                ],
            }
        ],
        # 视觉模型会先"想"再答，预算给小了只会返回空内容
        "max_tokens": 1500,
    }
    res = ai._request  # noqa: F841  (保持函数引用，便于测试替换)
    resp = ai._request(f"{base}/chat/completions", payload, key, timeout)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("detail") or "模型调用失败")
    return resp["data"]["choices"][0]["message"].get("content") or ""


def _do(action: dict[str, Any], rect: tuple[int, int, int, int]) -> str:
    kind = str(action.get("action") or "").lower()
    if kind not in ALLOWED:
        return f"忽略未知动作 {kind!r}"

    if kind == "click":
        x = rect[0] + int(action.get("x") or 0)
        y = rect[1] + int(action.get("y") or 0)
        win32api.SetCursorPos((x, y))
        time.sleep(0.2)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return f"点击 ({action.get('x')},{action.get('y')})"

    if kind == "type":
        text = str(action.get("text") or "")
        if not text:
            return "要输入的内容为空"
        from .adapters import uia

        if not uia.set_clipboard(text):
            return "剪贴板被占用"
        uia.send_keys("^v")
        return f"输入 {text[:24]}"

    if kind == "key":
        from .adapters import uia

        k = str(action.get("key") or "").lower()
        mapping = {
            "enter": "{ENTER}",
            "esc": "{ESC}",
            "tab": "{TAB}",
            "ctrl+f": "^f",
            "ctrl+a": "^a",
            "ctrl+v": "^v",
        }
        if k not in mapping:
            return f"不支持的按键 {k!r}"
        uia.send_keys(mapping[k])
        return f"按键 {k}"

    if kind == "scroll":
        win32api.SetCursorPos((rect[0] + rect[2] // 2, rect[1] + rect[3] // 2))
        dy = int(action.get("dy") or -3)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, dy * 120, 0)
        return f"滚动 {dy}"

    return f"结束：{kind}"


def run(hwnd: int, task: str, max_steps: int = 8, dry: bool = False) -> dict[str, Any]:
    """看一步、做一步，最多 max_steps 步。dry=True 只让模型看一步，不动手。"""
    rect = win32gui.GetWindowRect(hwnd)
    trace: list[dict[str, Any]] = []
    history = ""

    for step in range(1, max_steps + 1):
        img = _capture(rect)
        system = SYSTEM.format(task=task, w=img.width, h=img.height)
        user = (history or "这是第一步。") + "\n请给出下一步动作。"
        try:
            raw = _ask(img, system, user)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"模型调用失败：{exc}", "steps": trace}

        act = _extract_json(raw)
        if act is None:
            return {"ok": False, "detail": f"模型没有返回 JSON：{raw[:120]}", "steps": trace}

        kind = str(act.get("action") or "").lower()
        trace.append({"step": step, "thought": act.get("thought"), "action": kind})

        if dry:
            return {"ok": True, "dry": True, "first": act, "steps": trace}

        if kind in ("done", "fail"):
            return {
                "ok": kind == "done",
                "detail": act.get("thought") or "",
                "steps": trace,
            }

        result = _do(act, rect)
        trace[-1]["result"] = result
        history = f"第 {step} 步你执行了：{result}。"
        time.sleep(1.2)

    return {"ok": False, "detail": f"{max_steps} 步内没完成", "steps": trace}
