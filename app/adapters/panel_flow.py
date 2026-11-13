"""接管「加好友/群」独立窗口完成加群/加好友。

为什么这样做：这个面板是 QQ 的独立窗口（标题就叫「加好友/群」），
用坐标去点主窗口的「+」时灵时不灵。改成按窗口标题找到它，
再用 OCR 定位里面的标签、输入框和按钮，稳定性高得多。
"""
from __future__ import annotations

import time

from . import vision as vis

PANEL_TITLE = "加好友/群"


def find_panel() -> int | None:
    import win32gui

    found: list[int] = []

    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if t and PANEL_TITLE in t and win32gui.IsWindowVisible(h):
            found.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def _click_word(hwnd: int, words: tuple[str, ...], timeout: float = 6.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        els = vis.look(hwnd)
        for w in words:
            el = vis.find(els, w)
            if el is not None:
                vis.click(el)
                return w
        time.sleep(0.6)
    return None


def _click_point(hwnd: int, dx: int, dy: int) -> None:
    import win32api
    import win32con

    r = vis.window_rect(hwnd)
    win32api.SetCursorPos((r[0] + dx, r[1] + dy))
    time.sleep(0.25)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def join_group_via_panel(keyword: str, message: str = "你好") -> tuple[bool, str]:
    """在已经打开的面板里：切到找群 → 搜关键词 → 选群 → 申请 → 填验证 → 提交。"""
    from . import uia

    hwnd = find_panel()
    if hwnd is None:
        return False, "没找到「加好友/群」窗口，请先在 QQ 里点 + → 加好友/群 打开它"

    vis.activate(hwnd)
    time.sleep(0.8)

    # 1) 切到「找群」
    if _click_word(hwnd, ("找群", "群聊", "查找群"), timeout=5) is None:
        return False, "面板里没找到「找群」标签"
    time.sleep(1.2)

    # 2) 输入关键词（面板顶部通常有搜索框）
    r = vis.window_rect(hwnd)
    _click_point(hwnd, max(80, (r[2] - r[0]) // 2), 40)
    time.sleep(0.5)
    uia.send_keys("^a")
    if not uia.type_unicode(keyword):
        return False, "无法在面板里输入关键词"
    time.sleep(0.8)
    uia.send_keys("{ENTER}")
    time.sleep(2.5)

    els = vis.look(hwnd)
    seen = " / ".join(vis.texts(els)[:8])

    # 3) 点开一个名字里带关键词的群
    hit = vis.find(els, keyword)
    if hit is None:
        return False, f"没搜到含「{keyword}」的群（当前：{seen}）"
    vis.click(hit)
    time.sleep(2.0)

    # 4) 申请加群
    if _click_word(hwnd, ("申请加群", "加群", "加入群聊"), timeout=6) is None:
        return False, f"群资料里没找到「申请加群」（当前：{seen}）"
    time.sleep(1.5)

    # 5) 填验证并提交
    if message:
        try:
            uia.type_unicode(message)
            time.sleep(0.5)
        except Exception:
            pass
    if _click_word(hwnd, ("发送", "确定", "提交", "完成"), timeout=6) is None:
        return False, "没找到提交按钮"

    time.sleep(1.5)
    els = vis.look(hwnd)
    proofs = ("申请已发送", "已提交", "等待审核", "等待管理员审核", "已申请")
    got = [w for w in proofs if vis.find(els, w)]
    if got:
        return True, f"已提交加群申请（证据：{got[0]}）"
    return False, "点了提交但没看到成功提示"
