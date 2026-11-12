"""演示并验证「按方向找人」的界面链路。

流程：切到 B 站 → 点「按方向找」→ 输入方向描述 → 点「AI 找候选人」→ 截图。
注意：调用方应先把 web.headless 设为 true，避免测试时弹出浏览器窗口。
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

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def click(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.18)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.25)


def type_unicode(text: str) -> None:
    for ch in text:
        for flags in (0x0004, 0x0004 | 0x0002):
            inp = INPUT(type=1)
            inp.u.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.012)


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
    time.sleep(1.0)
    l, t, r, b = win32gui.GetWindowRect(hwnd)

    # 1) 选中 B 站
    click(l + 170, t + 714)
    time.sleep(1.0)

    # 2) 切到「按方向找」
    click(l + 460, t + 269)
    time.sleep(0.8)
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save("data/screenshots/_step1.png")

    # 3) 输入方向描述
    click(l + 658, t + 310)
    time.sleep(0.4)
    type_unicode("效率工具 独立开发")
    time.sleep(0.8)
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save("data/screenshots/_step2.png")

    # 4) 点「AI 找候选人」
    click(l + 482, t + 374)
    time.sleep(28)
    ImageGrab.grab(bbox=(l, t, r, b), all_screens=True).save("data/screenshots/flutter_discover.png")

    win32gui.SetWindowPos(
        hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
