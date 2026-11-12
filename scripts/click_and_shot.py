"""把应用窗口提到最上层，可选地点击窗口内某个坐标，然后截图。

用法：
    python scripts/click_and_shot.py <输出图片> [dx] [dy] [等待秒数]

不抢键盘焦点（只改 z 序），点击前重新读取窗口矩形，避免点到别的窗口。
"""
from __future__ import annotations

import ctypes
import sys
import time

import win32con
import win32gui
from PIL import ImageGrab

user32 = ctypes.windll.user32
TITLE = "桌面自动化控制台"


def click(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def main() -> int:
    out = sys.argv[1]
    dx = int(sys.argv[2]) if len(sys.argv) > 2 else None
    dy = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    wait = float(sys.argv[4]) if len(sys.argv) > 4 else 1.5

    found: list[int] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and TITLE in win32gui.GetWindowText(hwnd):
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not found:
        raise SystemExit("没找到应用窗口")
    hwnd = found[0]

    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
    )
    time.sleep(0.9)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)

    if dx is not None:
        click(left + dx, top + dy)
        time.sleep(wait)

    ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(out)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
