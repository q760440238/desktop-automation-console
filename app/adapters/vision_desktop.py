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

# 提交成功后界面上必然出现的字样；没有这些就说明没真提交
PROOF_WORDS = {
    "add_friend": (
        "加「{target}」为好友。用顶部搜索框，不要用「+」菜单："
        "1) 点击顶部搜索框，输入「{target}」并回车；"
        "2) 结果里会出现「联系人」分组，点开名字是「{target}」的那个人，进入资料卡；"
        "3) 在资料卡上找到并点击「加好友」按钮；"
        "4) 如果弹出验证消息输入框，填「{text}」；"
        "5) 点击发送/确定提交申请。中途如果冒出别的弹窗，先点取消或关闭。"
    ),
    "join_group": ("申请已发送", "已提交申请", "等待管理员审核", "已申请加群", "申请已提交"),
    "send_message": (),
}

APP_NAMES = {"qq": "QQ", "wechat": "微信", "wecom": "企业微信"}

TASKS = {
    "send_message": (
        "给「{target}」发一条消息。步骤：1) 点击顶部搜索框，输入「{target}」；"
        "2) 在搜索结果里点开这个会话（不要点群）；"
        "3) 如果搜不到（例如「我的手机」「我的电脑」这类设备），"        "改从左侧「联系人」里的「我的设备」分组点开它；"
        "4) 确认右侧聊天标题就是「{target}」；5) 点击底部消息输入框；"
        "6) 输入「{text}」；7) 按回车发送。发送后输入框会变空，这时就返回 done。"
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
    max_steps: int = 20,
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

    # 加好友/加群：走确定性的 OCR 点击流程，比让模型自由导航稳
    if action in ("add_friend", "join_group"):
        from . import scripted_flows

        fn = scripted_flows.add_friend if action == "add_friend" else scripted_flows.join_group
        try:
            ok, detail = fn(info.hwnd, target, text or "你好")
        except Exception as exc:  # noqa: BLE001
            return ExecResult(False, f"{app} 脚本流程异常：{exc}")
        return ExecResult(ok, f"【{app}·脚本流程】{detail}")

    tpl = TASKS.get(action)
    if tpl is None:
        return ExecResult(False, f"{app} 不支持动作 {action}")
    task = tpl.format(target=target, text=text or "你好")

    # 先查经验库：以前做成过的同类任务，把做法作为参考塞进提示
    try:
        from .. import knowledge

        learned = knowledge.render(knowledge.find(platform, action, f"{target} {action}"))
        if learned:
            task = task + "\n\n" + learned
    except Exception:
        pass

    # 会话已经开着了就别再搜索：像「我的手机」「我的电脑」这类设备联系人搜不到
    try:
        from . import vision as win_vision

        already, _ = win_vision.header_has(info.hwnd, target)
    except Exception:
        already = False
    if already:
        task = (
            f"当前右侧已经打开了与「{target}」的会话，标题已确认。"
            f"直接从点击底部消息输入框开始，输入「{text or '你好'}」，然后回车发送。"
        )

    from . import uia

    shot = None
    try:
        res = vision_agent.run(info.hwnd, task, max_steps=max_steps)
        shot = uia.capture(info.hwnd, f"data/screenshots/{platform}_{action}_vision.png")
    except Exception as exc:  # noqa: BLE001
        return ExecResult(False, f"{app} 视觉操作异常：{exc}")

    steps = res.get("steps") or []
    trace = " → ".join(f"{s.get('action')}" for s in steps) or "无动作"

    # 加好友/加群必须有「申请已发送」之类的硬证据，否则视为没做成
    words = PROOF_WORDS.get(action) or ()
    if res.get("ok") and words:
        try:
            from . import vision as win_vision

            els = win_vision.look(info.hwnd)
            hits = [w for w in words if win_vision.find(els, w)]
        except Exception:
            hits = []
        if not hits:
            seen = " / ".join(win_vision.texts(els)[:6]) if els else "（没识别到文字）"
            return ExecResult(
                False,
                f"【{app}·视觉执行】没有看到「申请已发送」这类提示，判定未成功（当前界面：{seen}）",
                screenshot=shot,
            )

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
