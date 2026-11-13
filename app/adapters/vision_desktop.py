"""桌面端统一入口：所有动作都交给视觉代理执行。

为什么不用 UI Automation：
- QQ NT 是 Electron，控件树是空的（探测到 0 个控件）；
- 微信/企业微信 4.x 虽然暴露部分控件，但不同版本差异大，靠控件名找按钮很脆；
- 视觉代理看的是真实画面，不依赖控件树，三个应用用同一套逻辑。
"""
from __future__ import annotations

from typing import Any

from .. import vision_agent
from .base import ExecResult

APP_NAMES = {"qq": "QQ", "wechat": "微信", "wecom": "企业微信"}

TASKS = {
    "send_message": (
        "给「{target}」发一条消息。步骤：1) 点击顶部的搜索框；2) 输入「{target}」；"
        "3) 在搜索结果里点开这个人的会话（不要点群）；4) 确认打开的聊天标题就是「{target}」；"
        "5) 点击底部的消息输入框；6) 输入「{text}」；7) 按回车或点发送按钮发出去。"
    ),
    "add_friend": (
        "加「{target}」为好友。步骤：1) 点击顶部搜索框；2) 输入 {target} 并回车；"
        "3) 点开搜索结果里的这个人；4) 找到并点击「加好友」；"
        "5) 如果有验证消息输入框，填「{text}」；6) 点击发送/确定提交申请。"
    ),
    "join_group": (
        "申请加入群 {target}。步骤：1) 点击顶部搜索框；2) 输入群号 {target} 并回车；"
        "3) 点开搜索结果里的这个群；4) 找到并点击「加群」或「申请加群」；"
        "5) 如有验证信息输入框，填「{text}」；6) 点击发送/确定提交申请。"
    ),
}




def desktop_locked() -> bool:
    """屏幕是否已锁定：锁定时鼠标键盘事件不会到达应用，必须先告诉用户。"""
    import ctypes

    DESKTOP_SWITCHDESKTOP = 0x0100
    try:
        h = ctypes.windll.user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if h:
            ctypes.windll.user32.CloseDesktop(h)
            return False
        return True
    except Exception:
        return False


def run_task(
    platform: str,
    action: str,
    target: str,
    text: str = "",
    max_steps: int = 10,
    window_fn: Any = None,
) -> ExecResult:
    """看屏幕 → 操作 → 再看，直到模型认为完成。返回统一的结果对象。"""
    app = APP_NAMES.get(platform, platform)
    if desktop_locked():
        return ExecResult(
            False,
            f"屏幕已锁定，无法操作{app}。请解锁电脑后重试（锁定状态下点击不会生效）。",
        )
    if window_fn is None:
        return ExecResult(False, "内部错误：没有提供取窗口的方法")
    info = window_fn()
    if info is None:
        return ExecResult(False, f"{app} 未启动或主窗口不可见，请先登录")

    tpl = TASKS.get(action)
    if tpl is None:
        return ExecResult(False, f"{app} 不支持动作 {action}")
    task = tpl.format(target=target, text=text or "你好")

    from . import uia

    shot = None
    try:
        res = vision_agent.run(info.hwnd, task, max_steps=max_steps)
        shot = uia.capture(info.hwnd, f"data/screenshots/{platform}_{action}_vision.png")
    except Exception as exc:  # noqa: BLE001
        return ExecResult(False, f"{app} 视觉操作异常：{exc}")

    steps = res.get("steps") or []
    trace = " → ".join(f"{s.get('action')}" for s in steps) or "无动作"
    if res.get("ok"):
        return ExecResult(
            True,
            f"【{app}·视觉执行】已完成 {action}（{len(steps)} 步：{trace}）",
            screenshot=shot,
        )
    return ExecResult(
        False,
        f"【{app}·视觉执行】未完成：{res.get('detail') or '未知原因'}（{len(steps)} 步：{trace}）",
        screenshot=shot,
    )
