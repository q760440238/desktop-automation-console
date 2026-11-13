"""补丁：把窗口激活改得更温和，避免把 QQ 的弹窗弄成"假卡死"。

问题：原实现每次都做 SetWindowPos(TOPMOST) → SetWindowPos(NOTOPMOST) →
SetForegroundWindow，还 AttachThreadInput。当一个模态弹窗开着时，这种强制
抢焦点会让弹窗失去焦点又拿不回来，看起来就像卡死了。

改法：
1. 已经是前台窗口 → 直接返回，什么都不做；
2. 本进程已经有别的窗口在前台（比如弹着对话框）→ 不抢，避免打断它；
3. 只有真的不在前台时才动手，且去掉 TOPMOST 往返，只用 SW_RESTORE + SetForegroundWindow；
4. 同一个窗口 1.5 秒内不重复激活。
"""
from __future__ import annotations

from pathlib import Path

P = Path(r"E:\AI工具\自动加好友发消息工具\app\adapters\win_focus.py")
s = P.read_text(encoding="utf-8")

start = s.index("def activate(hwnd: int)")
end = s.index("def capture_window(")
new = '''_last_activate: dict[int, float] = {}


def activate(hwnd: int) -> bool:
    """温和地把窗口带到前台：已经在前台就不动，避免打断正在显示的对话框。"""
    import time

    try:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return False

        fg = user32.GetForegroundWindow()
        if fg == hwnd:
            return True

        # 同一个进程的另一个窗口在前台（比如正开着对话框）→ 别抢
        try:
            import win32process

            if fg:
                _, fg_pid = win32process.GetWindowThreadProcessId(fg)
                _, my_pid = win32process.GetWindowThreadProcessId(hwnd)
                if fg_pid == my_pid:
                    return True
        except Exception:
            pass

        now = time.time()
        if now - _last_activate.get(hwnd, 0) < 1.5:
            return True
        _last_activate[hwnd] = now

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        # 只用最普通的前台切换，不做 TOPMOST 往返（那是把弹窗弄卡的元凶）
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return True
    except Exception:
        return False


'''
s = s[:start] + new + s[end:]
P.write_text(s, encoding="utf-8")
print("activate 已改为温和模式")
