"""QQ NT 适配器：加好友、加群、发消息。

QQ NT 是 Electron 应用，UI Automation 暴露的控件较少，因此以「键盘 + 剪贴板 + 文本按钮点击」
为主，控件树仅用于定位搜索框与输入框。所有动作都要求 QQ 已登录且主窗口可见。
"""
from __future__ import annotations

import time
from typing import Any

from ..settings import detect_qq_exe
from . import uia, vision
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
    # 剪贴板经常被占用，优先直接输入字符
    if uia.type_unicode(text):
        time.sleep(0.3)
        uia.send_keys("{ENTER}")
        return
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
                # 发之前用「看」确认会话标题确实是这个人：看错了宁可不发
                try:
                    ok_title, seen = vision.header_has(info.hwnd, target)
                except Exception as exc:
                    ok_title, seen = True, f"视觉校验异常：{exc}"
                if not ok_title and seen and "异常" not in seen:
                    return ExecResult(
                        False,
                        f"会话标题里没看到「{target}」（当前顶部文字：{seen}），已中止，避免发错人",
                        screenshot=uia.capture(info.hwnd, shot_path("qq", f"mismatch_{target}")),
                    )
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
            from .. import vision_agent

            task = (
                f"在 QQ 里加好友。步骤：1) 点击顶部的搜索框；2) 输入 QQ 号 {target} 并回车；"
                f"3) 在搜索结果里点开这个人；4) 找到并点击「加好友」按钮；"
                f"5) 如果要填验证消息，填「{text or '你好'}」；6) 点击发送/确定提交申请。"
            )
            res = vision_agent.run(info.hwnd, task, max_steps=10)
            shot2 = uia.capture(info.hwnd, shot_path("qq", f"addfriend_{target}"))
            if res.get("ok"):
                return ExecResult(True, f"已通过视觉操作向 {target} 提交好友申请", screenshot=shot2)
            return ExecResult(
                False,
                f"加好友未完成：{res.get('detail') or '未知原因'}（{len(res.get('steps') or [])} 步）",
                screenshot=shot2,
            )
        if action == "join_group":
            from .. import vision_agent

            task = (
                f"在 QQ 里加群。步骤：1) 点击顶部的搜索框；2) 输入群号 {target} 并回车；"
                f"3) 在搜索结果里点开这个群；4) 找到并点击「加群」或「申请加群」；"
                f"5) 如果要填验证信息，填「{text or '你好，想加入'}」；6) 点击发送/确定提交申请。"
            )
            res = vision_agent.run(info.hwnd, task, max_steps=10)
            shot2 = uia.capture(info.hwnd, shot_path("qq", f"joingroup_{target}"))
            if res.get("ok"):
                return ExecResult(True, f"已通过视觉操作申请加入群 {target}", screenshot=shot2)
            return ExecResult(
                False,
                f"加群未完成：{res.get('detail') or '未知原因'}（{len(res.get('steps') or [])} 步）",
                screenshot=shot2,
            )


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
    key = "qq"
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

    def see(self) -> dict[str, Any]:
        return vision.see_window(_window)

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
