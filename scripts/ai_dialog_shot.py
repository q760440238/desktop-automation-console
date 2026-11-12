"""打开 Flutter 应用的 AI 设置弹窗并截图（含模型下拉展开）。

安全措施：只用 TOPMOST 调整 z 序，不抢键盘焦点；点击前重新取一次窗口矩形，
确保坐标是当前真实位置，避免误点到别的窗口。
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


def find() -> int:
    found: list[int] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and TITLE in win32gui.GetWindowText(hwnd):
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not found:
        raise SystemExit("没找到应用窗口")
    return found[0]


def main() -> int:
    hwnd = find()
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
    )
    time.sleep(1.2)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    print("rect", (l, t, r, b))

    # 1) 右上角 AI 按钮
    click(l + 1460, t + 61)
    time.sleep(3.2)
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save(
        "data/screenshots/flutter_ai_models.png"
    )

    # 2) 模型下拉箭头：展开候选列表
    click(l + 1086, t + 610)
    time.sleep(1.6)
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save(
        "data/screenshots/flutter_ai_models_open.png"
    )

    win32gui.SetWindowPos(
        hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
