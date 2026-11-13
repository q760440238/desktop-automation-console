"""确定性加好友/加群流程：用 OCR 找字定位，按固定顺序点击。

为什么不用视觉代理：QQ 的「+」菜单、资料卡、验证弹窗层级太多，
模型容易在里面打转。这里把步骤写死，只让 OCR 负责"东西在哪"。
"""
from __future__ import annotations

import time
from typing import Any

from . import vision as vis


def _click_text(hwnd: int, words: tuple[str, ...], timeout: float = 8.0) -> str | None:
    """在窗口里找这些词，找到就点，返回点到的词。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            els = vis.look(hwnd)
        except Exception:
            els = []
        for w in words:
            el = vis.find(els, w)
            if el is not None:
                vis.click(el)
                return w
        time.sleep(0.8)
    return None


def _click_point(hwnd: int, dx: int, dy: int) -> None:
    import win32api
    import win32con

    r = vis.window_rect(hwnd)
    win32api.SetCursorPos((r[0] + dx, r[1] + dy))
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def add_friend(hwnd: int, target: str, text: str) -> tuple[bool, str]:
    """搜人 → 开资料卡 → 加好友 → 填验证 → 提交。"""
    from . import uia

    vis.activate(hwnd)
    time.sleep(0.6)

    # 1) 搜索框（QQ 主界面固定在左上）
    r = vis.window_rect(hwnd)
    import win32api
    import win32con

    win32api.SetCursorPos((r[0] + 140, r[1] + 62))
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.6)
    uia.send_keys("^a")
    if not uia.type_unicode(target):
        return False, "无法输入搜索内容"
    time.sleep(1.8)

    # 2) 点搜索结果里的这个人
    if _click_text(hwnd, (target,), timeout=6) is None:
        return False, f"搜索结果里没看到「{target}」"

    # 3) 资料卡上点「加好友」
    hit = _click_text(hwnd, ("加好友", "添加好友", "加为好友"), timeout=5)
    if hit is None:
        # 点搜索结果进的是「临时会话」，得先点会话头部的昵称/头像打开资料卡
        _click_point(hwnd, 360, 66)
        time.sleep(1.6)
        hit = _click_text(hwnd, ("加好友", "添加好友", "加为好友"), timeout=8)
    if hit is None:
        seen = " / ".join(vis.texts(vis.look(hwnd))[:8])
        return False, f"资料卡上没找到「加好友」按钮（当前：{seen}）"
    time.sleep(1.5)

    # 4) 填验证消息（有输入框才填）
    if text:
        try:
            if uia.type_unicode(text):
                time.sleep(0.5)
        except Exception:
            pass

    # 5) 提交
    sent = _click_text(hwnd, ("发送", "确定", "完成", "下一步"), timeout=8)
    time.sleep(1.2)
    if sent is None:
        return False, "没找到提交按钮，申请未发出"

    # 6) 硬证据
    els = vis.look(hwnd)
    proofs = ("申请已发送", "请求已发送", "好友申请已发送", "等待对方验证", "已发送好友申请", "已添加")
    got = [w for w in proofs if vis.find(els, w)]
    if got:
        return True, f"已提交好友申请（证据：{got[0]}）"
    return False, "点击了提交，但没看到「申请已发送」提示"


def join_group(hwnd: int, target: str, text: str) -> tuple[bool, str]:
    # 优先走「加好友/群」独立窗口（更稳），面板没开再退回主窗口搜索
    from . import panel_flow

    if panel_flow.find_panel() is not None:
        return panel_flow.join_group_via_panel(target, text)
    """搜群 → 开群资料 → 申请加群 → 填验证 → 提交。"""
    from . import uia

    vis.activate(hwnd)
    time.sleep(0.6)
    r = vis.window_rect(hwnd)
    import win32api
    import win32con

    win32api.SetCursorPos((r[0] + 140, r[1] + 62))
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.6)
    uia.send_keys("^a")
    if not uia.type_unicode(target):
        return False, "无法输入搜索内容"
    time.sleep(1.8)

    if _click_text(hwnd, (target,), timeout=6) is None:
        return False, f"搜索结果里没看到「{target}」"

    hit = _click_text(hwnd, ("加群", "申请加群", "加入群聊"), timeout=8)
    if hit is None:
        seen = " / ".join(vis.texts(vis.look(hwnd))[:8])
        return False, f"群资料里没找到「加群」按钮（当前：{seen}）"
    time.sleep(1.5)

    if text:
        try:
            uia.type_unicode(text)
            time.sleep(0.5)
        except Exception:
            pass

    sent = _click_text(hwnd, ("发送", "确定", "完成", "提交"), timeout=8)
    time.sleep(1.2)
    if sent is None:
        return False, "没找到提交按钮，申请未发出"

    els = vis.look(hwnd)
    proofs = ("申请已发送", "已提交申请", "等待管理员审核", "已申请加群", "申请已提交")
    got = [w for w in proofs if vis.find(els, w)]
    if got:
        return True, f"已提交加群申请（证据：{got[0]}）"
    return False, "点击了提交，但没看到「申请已发送」提示"
