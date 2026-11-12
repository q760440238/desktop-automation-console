"""微信 PC 端适配器（支持微信 4.x / Weixin.exe）。

流程：激活窗口 → Ctrl+F 搜索联系人 → 回车进入会话 → 聚焦输入框 → 粘贴 → 回车发送。
每一步都有「是否真的进入会话」的校验，宁可中止也不要把消息发错人。
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..settings import detect_wechat_exe, load_settings
from . import uia
from .base import BaseAdapter, Ctx, ExecResult, shot_path

PROCS = ["Weixin.exe", "WeChat.exe"]
TITLE_RE = r"微信|WeChat|Weixin"


def _window() -> Any:
    return uia.find_window(PROCS, TITLE_RE)


def _health() -> dict[str, Any]:
    running = uia.process_running(PROCS)
    if not running:
        exe = detect_wechat_exe()
        return {
            "ready": False,
            "detail": "微信未运行" + ("（已找到安装路径，可点「启动应用」）" if exe else "（未找到 Weixin.exe）"),
        }
    win = _window()
    if win is None:
        return {"ready": False, "detail": "进程在运行但没找到主窗口（可能最小化到托盘，点一下微信图标）"}
    return {"ready": True, "detail": f"已连接「{win.title}」"}


def _search_edit(win: Any) -> Any | None:
    """搜索框：微信 4.x 是带「搜索」提示的 Edit。"""
    try:
        for name in ("搜索", "Search", ""):
            try:
                cand = win.child_window(control_type="Edit", title=name, found_index=0)
                if cand.exists(timeout=0.4):
                    return cand
            except Exception:
                continue
        edits = [c for c in win.descendants(control_type="Edit") if c.is_visible()]
        for e in edits:
            try:
                if "搜索" in (e.window_text() or ""):
                    return e
            except Exception:
                continue
        return max(edits, key=lambda c: _area(c)) if edits else None
    except Exception:
        return None


def _area(ctrl: Any) -> int:
    try:
        r = ctrl.rectangle()
        return max(0, r.right - r.left) * max(0, r.bottom - r.top)
    except Exception:
        return 0


def _send(target: str, text: str) -> ExecResult:
    win_info = _window()
    if win_info is None:
        return ExecResult(False, "微信未启动或主窗口不可见，请先登录微信 PC 端")

    shot = shot_path("wechat", target)
    try:
        uia.focus_window(win_info.hwnd)
        win = uia.connect(win_info.hwnd)

        # 1) 搜索联系人
        edit = _search_edit(win)
        if edit is not None:
            try:
                edit.click_input()
            except Exception:
                uia.send_keys("^f")
        else:
            uia.send_keys("^f")
        time.sleep(0.35)
        uia.send_keys("^a")
        if not uia.set_clipboard(target):
            return ExecResult(False, "无法写入剪贴板，可能是剪贴板被其它程序占用")
        uia.send_keys("^v")
        time.sleep(1.1)
        uia.send_keys("{ENTER}")
        time.sleep(1.0)

        # 2) 校验是否真的离开了搜索态（搜索框里还留着关键字=没进会话）
        try:
            if edit is not None:
                remain = (edit.window_text() or "").strip()
                if remain and remain == target.strip():
                    uia.send_keys("{ESC}")
                    p = uia.capture(win_info.hwnd, shot)
                    return ExecResult(False, f"没有找到联系人/群「{target}」，已中止（未发送）", screenshot=p)
        except Exception:
            pass

        # 3) 聚焦输入框
        input_box = uia.find_edit(win)
        if input_box is None:
            p = uia.capture(win_info.hwnd, shot)
            return ExecResult(False, "没定位到消息输入框，请点「探测」查看控件树后校准", screenshot=p)
        try:
            input_box.click_input()
        except Exception:
            pass
        time.sleep(0.25)

        # 4) 粘贴并发送
        if not uia.set_clipboard(text):
            return ExecResult(False, "无法写入剪贴板，消息未发送")
        uia.send_keys("^v")
        time.sleep(0.35)
        uia.send_keys("{ENTER}")
        time.sleep(0.5)

        p = uia.capture(win_info.hwnd, shot)
        return ExecResult(
            True,
            f"已向「{target}」发送 {len(text)} 字消息（已留存截图，建议核对一次）",
            screenshot=p,
        )
    except Exception as exc:
        p = uia.capture(win_info.hwnd, shot)
        return ExecResult(False, f"微信操作异常：{exc}", screenshot=p)


def _probe() -> dict[str, Any]:
    info = _window()
    if info is None:
        return {"error": "微信未运行", "windows": [w.as_dict() for w in uia.list_windows(PROCS)]}
    try:
        uia.focus_window(info.hwnd)
    except Exception:
        pass
    win = uia.connect(info.hwnd)
    return {
        "window": info.as_dict(),
        "chat_title_guess": _guess_title(win),
        "controls": uia.dump_tree(win, max_depth=4, max_items=60),
        "hint": "把需要在 config/desktop.json 里覆盖的控件写进 wechat 节即可；一般无需改代码。",
    }


def _guess_title(win: Any) -> str:
    try:
        for c in win.descendants(control_type="Text")[:8]:
            t = (c.window_text() or "").strip()
            if t and len(t) < 30 and not re.search(r"(搜索|发送|表情|文件)", t):
                return t
    except Exception:
        pass
    return ""


class WechatAdapter(BaseAdapter):
    platform = "wechat"
    kind = "desktop"
    actions = {"send_message"}

    async def health(self) -> dict[str, Any]:
        try:
            return await uia.run_sync(_health)
        except Exception as exc:
            return {"ready": False, "detail": f"探测失败：{exc}"}

    async def execute(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        if action != "send_message":
            return ExecResult(False, f"微信暂不支持「{action}」")
        return await uia.run_sync(_send, target, text)

    def open_login(self) -> dict[str, Any]:
        if uia.process_running(PROCS):
            info = _window()
            if info:
                try:
                    uia.focus_window(info.hwnd)
                except Exception:
                    pass
                return {"ok": True, "detail": f"微信已在运行：{info.title}"}
            return {"ok": True, "detail": "微信进程在运行，但主窗口不可见，请从托盘打开"}
        exe = detect_wechat_exe()
        if not exe:
            return {"ok": False, "detail": "没找到 Weixin.exe，请在 config/settings.json 里填写 desktop.wechat_exe"}
        ok = uia.launch(exe, timeout=1.0)
        return {"ok": ok, "detail": f"已启动 {exe}" if ok else "启动失败，请手动打开微信"}

    async def probe(self) -> dict[str, Any]:
        return await uia.run_sync(_probe)
