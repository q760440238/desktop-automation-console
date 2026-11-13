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
    """老路径的搜索；失败不抛异常，交给后续视觉判断。"""
    _focus_search(win)
    time.sleep(0.3)
    uia.send_keys("^a")
    if uia.type_unicode(keyword):
        time.sleep(1.2)
        return
    if uia.set_clipboard(keyword):
        uia.send_keys("^v")
        time.sleep(1.2)


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
        # 全部动作走视觉执行（UIA 在 QQ 上不可用，三个应用统一逻辑）
        from . import vision_desktop

        return vision_desktop.run_task(
            "qq", action, target, text, max_steps=20, window_fn=_window
        )
        uia.focus_window(info.hwnd)
        win = uia.connect(info.hwnd)
        # 三个动作都由视觉代理自己搜索，这里不再统一预搜

        if action == "send_message":
            from .. import vision_agent

            # 第一步：用视觉打开聊天（不发送），随后用程序校验标题，防止发错人
            nav = (
                f"在 QQ 里打开与「{target}」的聊天窗口。步骤：点击顶部搜索框，输入「{target}」，"
                f"回车或点击搜索结果里的这个人，进入和他的聊天。只打开聊天，绝对不要发送任何消息。"
            )
            r1 = vision_agent.run(info.hwnd, nav, max_steps=6)
            shot2 = uia.capture(info.hwnd, shot)

            ok_title, seen = vision.header_has(info.hwnd, target)
            if not ok_title:
                return ExecResult(
                    False,
                    f"没能打开与「{target}」的聊天（顶部文字：{seen}；导航 {len(r1.get('steps') or [])} 步）",
                    screenshot=shot2,
                )

            # 第二步：输入并发送（直接用 Unicode 输入，不依赖剪贴板）
            sent = None
            if uia.type_unicode(text):
                sent = "直接输入"
            elif uia.set_clipboard(text):
                uia.send_keys("^v")
                sent = "粘贴"
            if not sent:
                return ExecResult(False, "无法把消息写入输入框（剪贴板与直接输入都失败）", screenshot=shot2)

            time.sleep(0.4)
            uia.send_keys("{ENTER}")
            time.sleep(0.9)
            after = uia.capture(info.hwnd, shot_path("qq", f"sent_{target}"))
            return ExecResult(
                True,
                f"已通过视觉操作向「{target}」发送（{sent}，已校验会话标题，截图见附件）",
                screenshot=after,
            )

        if action == "add_friend":
            from .. import vision_agent

            task = (
                f"在 QQ 里加好友。步骤：1) 点击顶部的搜索框；2) 输入 QQ 号 {target} 并回车；"
                f"3) 在搜索结果里点开这个人；4) 找到并点击「加好友」按钮；"
                f"5) 如果要填验证消息，填「{text or '你好'}」；6) 点击发送/确定提交申请。"
            )
            res = vision_agent.run(info.hwnd, task, max_steps=20)
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
            res = vision_agent.run(info.hwnd, task, max_steps=20)
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
