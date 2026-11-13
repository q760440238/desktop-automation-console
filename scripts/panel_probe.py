"""打开「加好友/群」独立窗口，截取并 OCR，看看它的布局。"""
from __future__ import annotations

import sys
import time
import win32api
import win32con
import win32gui
import win32process
import psutil
from PIL import ImageGrab
from pathlib import Path

ROOT = Path(r"E:\AI工具\自动加好友发消息工具")
sys.path.insert(0, str(ROOT))

from app.adapters import uia, win_focus  # noqa: E402


def find_panel() -> int | None:
    found = []

    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if t and "加好友" in t and win32gui.IsWindowVisible(h):
            found.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def main() -> int:
    info = uia.find_window(["QQ.exe"], "QQ", include_hidden=True)
    if info is None:
        print("QQ 未运行")
        return 1
    win_focus.activate(info.hwnd)
    time.sleep(0.6)

    panel = find_panel()
    if panel is None:
        r = win32gui.GetWindowRect(info.hwnd)
        for dx, dy in [(280, 63), (300, 130)]:
            win32api.SetCursorPos((r[0] + dx, r[1] + dy))
            time.sleep(0.3)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(1.2)
        panel = find_panel()

    if panel is None:
        print("没打开加好友/群窗口")
        return 1

    print("面板 hwnd =", panel, "标题 =", win32gui.GetWindowText(panel))
    print("rect =", win32gui.GetWindowRect(panel))
    win_focus.activate(panel)
    time.sleep(0.8)
    r = win32gui.GetWindowRect(panel)
    img = ImageGrab.grab(bbox=r, all_screens=True)
    out = ROOT / "data" / "screenshots" / "panel_main.png"
    img.save(out)
    print("截图:", out, img.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
