"""用 SendInput 驱动 Flutter 窗口，做一次真实的界面端到端验证。

为什么不用剪贴板：Flutter 的 Windows 文本输入走 TSF/IMM，剪贴板注入经常不生效，
逐字符 SendInput(KEYEVENTF_UNICODE) 更可靠。
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

import win32gui
from PIL import ImageGrab

user32 = ctypes.windll.user32
ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


def focus_window(title_part: str = "桌面自动化控制台"):
    found: list[int] = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and title_part in win32gui.GetWindowText(hwnd):
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    if not found:
        raise SystemExit(f"没找到标题包含「{title_part}」的窗口")
    hwnd = found[0]
    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(0.2)
    for attempt in range(3):
        try:
            win32gui.SetForegroundWindow(hwnd)
            break
        except Exception:
            # 前台锁：先模拟一次 ALT 键再抢焦点，是 Windows 上通用的做法
            key(0x12)
            try:
                win32gui.BringWindowToTop(hwnd)
            except Exception:
                pass
            time.sleep(0.3)
    time.sleep(0.7)
    return hwnd, win32gui.GetWindowRect(hwnd)


def click(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.3)


def _key(vk: int, up: bool) -> None:
    inp = INPUT(type=1)
    inp.u.ki = KEYBDINPUT(vk, 0, 2 if up else 0, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def key(vk: int) -> None:
    _key(vk, False)
    time.sleep(0.04)
    _key(vk, True)
    time.sleep(0.06)


def type_unicode(text: str) -> None:
    for ch in text:
        if ch == "\n":
            key(0x0D)  # Enter：Flutter 多行输入框里就是换行
            continue
        for flags in (0x0004, 0x0004 | 0x0002):  # KEYDOWN / KEYUP + UNICODE
            inp = INPUT(type=1)
            inp.u.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.012)


def main() -> int:
    targets = sys.argv[1] if len(sys.argv) > 1 else (
        "https://www.douyin.com/user/MS4wLjABAAAA_alpha01\n"
        "https://www.douyin.com/user/MS4wLjABAAAA_beta02\n"
        "https://evil.example.com/not-allowed"
    )
    hwnd, rect = focus_window()
    # 点击目标输入框（窗口内坐标 660,300）
    click(rect[0] + 660, rect[1] + 300)
    time.sleep(0.4)
    type_unicode(targets)
    time.sleep(0.9)
    ImageGrab.grab(bbox=rect, all_screens=True).save("data/screenshots/_typed.png")

    # 点击「生成执行计划」
    click(rect[0] + 405, rect[1] + 665)
    time.sleep(3.2)
    ImageGrab.grab(bbox=rect, all_screens=True).save("data/screenshots/flutter_plan.png")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
