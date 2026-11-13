"""QQ NT 适配器：加好友、加群、发消息。

QQ NT 是 Electron 应用，UI Automation 暴露的控件较少，因此以「键盘 + 剪贴板 + 文本按钮点击」
为主，控件树仅用于定位搜索框与输入框。所有动作都要求 QQ 已登录且主窗口可见。
"""
from __future__ import annotations

import time
from typing import Any

from ..settings import detect_qq_exe
from . import uia
from .base import BaseAdapter, Ctx, ExecResult, shot_path

PROCS = ["QQ.exe", "QQNT.exe"]
TITLE_RE = r"QQ"


def _window() -> Any:
    return uia.find_window(PROCS, TITLE_RE, include_hidden=True)


def _health() -> dict[str, Any]:
    running = uia.process_running(PROCS)
    if not running:
        exe = detect_qq_exe()
        return {
            "ready": False,
            "detail": "QQ 未运行" + ("（已找到 QQ.exe，可点「启动应用」）" if exe else "（未找到 QQ.exe）"),
        }
    win = _window()
    if win is None:
        return {"ready": False, "detail": "QQ 进程在运行但主窗口不可见，请从托盘打开"}
    return {"ready": True, "detail": f"已连接「{win.title}」"}


def _click_text(win: Any, needles: list[str], timeout: float = 6.0) -> str | None:
    """在窗口里找到名字包含 needles 的可点击控件并点击，返回命中的文案。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            candidates = win.descendants()
        except Exception:
            candidates = []
        for c in candidates:
            try:
                if not c.is_visible():
                    continue
                name = (c.element_info.name or "").strip()
                if not name:
                    continue
                if any(n in name for n in needles) and len(name) <= 20:
                    c.click_input()
                    return name
            except Exception:
                continue
        time.sleep(0.4)
    return None


def _focus_search(win: Any) -> None:
    edits = []
    try:
        edits = [c for c in win.descendants(control_type="Edit") if c.is_visible()]
    except Exception:
        edits = []
    if edits:
        try:
            edits[0].click_input()
            return
        except Exception:
            pass
    uia.send_keys("^f")


def _search(win: Any, keyword: str) -> None:
    _focus_search(win)
    time.sleep(0.3)
    uia.send_keys("^a")
    if not uia.set_clipboard(keyword):
        raise RuntimeError("无法写入剪贴板")
    uia.send_keys("^v")
    time.sleep(1.4)


def _paste_and_enter(text: str) -> None:
    if not uia.set_clipboard(text):
        raise RuntimeError("无法写入剪贴板，消息未发送")
    uia.send_keys("^v")
    time.sleep(0.35)
    uia.send_keys("{ENTER}")


def _do(action: str, target: str, text: str) -> ExecResult:
    info = _window()
    if info is None:
        return ExecResult(False, "QQ 未启动或主窗口不可见，请先登录 QQ")
    shot = shot_path("qq", f"{action}_{target}")
    try:
        uia.focus_window(info.hwnd)
        win = uia.connect(info.hwnd)
        _search(win, target)

        if action == "send_message":
            uia.send_keys("{ENTER}")
            time.sleep(1.0)
            box = uia.find_edit(win)
            if box is None:
                # QQ NT 是 Electron，UIA 控件树为空，找不到输入框。
                # 此时搜索→回车后焦点已在聊天输入框，直接键盘粘贴发送。
                before = uia.capture(info.hwnd, shot)
                if not uia.set_clipboard(text):
                    return ExecResult(False, "无法写入剪贴板，消息未发送", screenshot=before)
                uia.send_keys("^v")
                time.sleep(0.6)
                uia.send_keys("{ENTER}")
                time.sleep(1.0)
                after = uia.capture(info.hwnd, shot_path("qq", f"sent_{target}"))
                return ExecResult(
                    True,
                    f"已通过 QQ 向「{target}」发送 {len(text)} 字（键盘模式，已留发送前后截图，建议核对）",
                    screenshot=after,
                )
            try:
                box.click_input()
            except Exception:
                pass
            _paste_and_enter(text)
            time.sleep(0.5)
            return ExecResult(
                True,
                f"已向「{target}」发送 {len(text)} 字消息（已留截图）",
                screenshot=uia.capture(info.hwnd, shot),
            )

        if action == "add_friend":
            hit = _click_text(win, ["加好友", "添加好友", "加为好友"])
            if not hit:
                p = uia.capture(info.hwnd, shot)
                return ExecResult(
                    False,
                    f"搜索结果里没有「加好友」入口，可能号码不存在或对方已是你好友（目标：{target}）",
                    screenshot=p,
                )
            time.sleep(1.2)
            if text:
                box = uia.find_edit(win)
                if box is not None:
                    try:
                        box.click_input()
                        _paste_and_enter(text)
                    except Exception:
                        pass
            done = _click_text(win, ["发送", "确定", "完成", "下一步"], timeout=4.0)
            p = uia.capture(info.hwnd, shot)
            if done:
                return ExecResult(True, f"已向 {target} 发送好友申请（点了「{done}」）", screenshot=p)
            return ExecResult(False, "已打开加好友面板但没有点到提交按钮，请手动确认", screenshot=p)

        if action == "join_group":
            hit = _click_text(win, ["加群", "申请加群", "加入群聊", "查看群资料"])
            if not hit:
                p = uia.capture(info.hwnd, shot)
                return ExecResult(False, f"搜索结果里没有加群入口，群号可能不存在（目标：{target}）", screenshot=p)
            time.sleep(1.2)
            if text:
                box = uia.find_edit(win)
                if box is not None:
                    try:
                        box.click_input()
                        _paste_and_enter(text)
                    except Exception:
                        pass
            done = _click_text(win, ["发送", "确定", "申请", "提交"], timeout=4.0)
            p = uia.capture(info.hwnd, shot)
            if done:
                return ExecResult(True, f"已提交加入群 {target} 的申请（点了「{done}」）", screenshot=p)
            return ExecResult(False, "已打开群资料但没有点到申请按钮，请手动确认", screenshot=p)

        return ExecResult(False, f"QQ 不支持动作 {action}")
    except Exception as exc:
        return ExecResult(False, f"QQ 操作异常：{exc}", screenshot=uia.capture(info.hwnd, shot))


def _probe() -> dict[str, Any]:
    info = _window()
    if info is None:
        return {"error": "QQ 未运行", "windows": [w.as_dict() for w in uia.list_windows(PROCS)]}
    win = uia.connect(info.hwnd)
    return {
        "window": info.as_dict(),
        "controls": uia.dump_tree(win, max_depth=3, max_items=50),
        "hint": "QQ NT 控件较少属于正常现象；搜索依赖 Ctrl+F 与剪贴板粘贴。",
    }


class QQAdapter(BaseAdapter):
    platform = "qq"
    kind = "desktop"
    actions = {"add_friend", "join_group", "send_message"}

    async def health(self) -> dict[str, Any]:
        try:
            return await uia.run_sync(_health)
        except Exception as exc:
            return {"ready": False, "detail": f"探测失败：{exc}"}

    async def execute(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        return await uia.run_sync(_do, action, target, text)

    def open_login(self) -> dict[str, Any]:
        """把 QQ 召到前台：托盘里的隐藏窗口也能唤出来，实在没有就重新拉起。"""
        info = _window()
        if info is not None and uia.activate(info.hwnd):
            return {"ok": True, "detail": f"已唤起 QQ 窗口：{info.title}"}

        exe = detect_qq_exe()
        if not exe:
            return {"ok": False, "detail": "没找到 QQ.exe，请在 config/settings.json 里填写 desktop.qq_exe"}
        # 进程还在托盘里时，再启动一次会唤回已有实例
        uia.launch(exe)
        time.sleep(3.0)
        info2 = _window()
        if info2 is not None and uia.activate(info2.hwnd):
            return {"ok": True, "detail": "已启动 QQ 并唤起窗口"}
        return {"ok": False, "detail": "启动命令已发出，但仍未检测到 QQ 窗口，请手动从托盘打开"}

    async def probe(self) -> dict[str, Any]:
        return await uia.run_sync(_probe)
