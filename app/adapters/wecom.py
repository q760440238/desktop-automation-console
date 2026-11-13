"""企业微信（WeCom）桌面端适配器。

流程与微信一致：激活窗口 → 搜索联系人/群 → 进会话 → 聚焦输入框 → 粘贴 → 回车。
企业微信 4.x 的控件树与微信同源，但类名和标题不同，所以单独一份、独立校准。
"""
from __future__ import annotations

import time
from typing import Any

from ..settings import detect_wecom_exe
from . import uia
from .base import BaseAdapter, Ctx, ExecResult, shot_path

PROCS = ["WXWork.exe"]
TITLE_RE = r"企业微信|WeCom|WXWork"


def _window() -> Any:
    return uia.find_window(PROCS, TITLE_RE, include_hidden=True)


def _health() -> dict[str, Any]:
    running = uia.process_running(PROCS)
    if not running:
        exe = detect_wecom_exe()
        return {
            "ready": False,
            "detail": "企业微信未运行" + ("（已找到安装路径，可点「启动应用」）" if exe else "（未检测到 WXWork.exe，请先安装）"),
        }
    win = _window()
    if win is None:
        return {"ready": False, "detail": "进程在运行但没找到主窗口（可能在托盘，点一下图标）"}
    return {"ready": True, "detail": f"已连接「{win.title}」"}


def _search_edit(win: Any) -> Any | None:
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
        return None
    except Exception:
        return None


def _send(target: str, text: str) -> ExecResult:
    win_info = _window()
    if win_info is None:
        return ExecResult(False, "企业微信未启动或主窗口不可见，请先登录")

    shot = shot_path("wecom", target)
    try:
        uia.focus_window(win_info.hwnd)
        win = uia.connect(win_info.hwnd)

        edit = _search_edit(win)
        if edit is not None:
            try:
                edit.click_input()
            except Exception:
                uia.send_keys("^f")
        else:
            uia.send_keys("^f")
        time.sleep(0.4)
        uia.send_keys("^a")
        if not uia.set_clipboard(target):
            return ExecResult(False, "无法写入剪贴板，可能是剪贴板被其它程序占用")
        uia.send_keys("^v")
        time.sleep(1.2)
        uia.send_keys("{ENTER}")
        time.sleep(1.1)

        # 校验：搜索框里还留着关键字 = 没真正进入会话
        try:
            if edit is not None:
                remain = (edit.window_text() or "").strip()
                if remain and remain == target.strip():
                    uia.send_keys("{ESC}")
                    p = uia.capture(win_info.hwnd, shot)
                    return ExecResult(False, f"没有找到联系人/群「{target}」，已中止（未发送）", screenshot=p)
        except Exception:
            pass

        input_box = uia.find_edit(win, prefer_large=True)
        if input_box is None:
            p = uia.capture(win_info.hwnd, shot)
            return ExecResult(False, "没定位到消息输入框，请点「探测」查看控件树后校准", screenshot=p)
        try:
            input_box.click_input()
        except Exception:
            pass
        time.sleep(0.25)

        if not uia.set_clipboard(text):
            return ExecResult(False, "无法写入剪贴板，消息未发送")
        uia.send_keys("^v")
        time.sleep(0.35)
        uia.send_keys("{ENTER}")
        time.sleep(0.5)

        p = uia.capture(win_info.hwnd, shot)
        return ExecResult(True, f"已向「{target}」发送 {len(text)} 字消息（已留存截图，建议核对一次）", screenshot=p)
    except Exception as exc:
        p = uia.capture(win_info.hwnd, shot)
        return ExecResult(False, f"企业微信操作异常：{exc}", screenshot=p)


def _probe() -> dict[str, Any]:
    info = _window()
    if info is None:
        return {"error": "企业微信未运行", "windows": [w.as_dict() for w in uia.list_windows(PROCS)]}
    try:
        uia.focus_window(info.hwnd)
    except Exception:
        pass
    win = uia.connect(info.hwnd)
    return {
        "window": info.as_dict(),
        "controls": uia.dump_tree(win, max_depth=4, max_items=60),
        "hint": "企业微信版本差异较大，若发送失败请把这份控件树发给开发者校准。",
    }


class WecomAdapter(BaseAdapter):
    platform = "wecom"
    kind = "desktop"
    actions = {"send_message"}

    async def health(self) -> dict[str, Any]:
        try:
            return await uia.run_sync(_health)
        except Exception as exc:
            return {"ready": False, "detail": f"探测失败：{exc}"}

    async def execute(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        if action != "send_message":
            return ExecResult(False, f"企业微信暂不支持「{action}」")
        return await uia.run_sync(_send, target, text)

    def open_login(self) -> dict[str, Any]:
        info = _window()
        if info is not None and uia.activate(info.hwnd):
            return {"ok": True, "detail": f"已唤起企业微信窗口：{info.title}"}

        exe = detect_wecom_exe()
        if not exe:
            return {
                "ok": False,
                "detail": "本机未检测到企业微信，请先安装（安装后在 config/settings.json 的 desktop.wecom_exe 填路径）",
            }
        uia.launch(exe)
        time.sleep(4.0)
        info2 = _window()
        if info2 is not None and uia.activate(info2.hwnd):
            return {"ok": True, "detail": "已启动企业微信并唤起窗口，请扫码登录"}
        return {"ok": False, "detail": "启动命令已发出，但仍未检测到企业微信窗口，请手动打开"}

    async def probe(self) -> dict[str, Any]:
        return await uia.run_sync(_probe)
