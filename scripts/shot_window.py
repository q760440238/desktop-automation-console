"""抓取 Flutter 窗口截图：只把窗口提到最上层（不改焦点、不模拟任何输入）。

为什么不用 SetForegroundWindow：它会抢走用户正在用的窗口的键盘焦点。
这里只用 TOPMOST 改 z 序，截完立刻还原，对用户干扰最小。
"""
from __future__ import annotations

import sys
import time

import win32con
import win32gui
from PIL import ImageGrab


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "桌面自动化控制台"
    out = sys.argv[2] if len(sys.argv) > 2 else "data/screenshots/flutter_plan.png"

    found: list[int] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and title in win32gui.GetWindowText(hwnd):
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not found:
        print("没找到窗口")
        return 1
    hwnd = found[0]

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(0.3)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
    )
    time.sleep(1.2)
    rect = win32gui.GetWindowRect(hwnd)
    img = ImageGrab.grab(bbox=rect, all_screens=True)
    img.save(out)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )
    print(f"saved {out} rect={rect} size={img.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
