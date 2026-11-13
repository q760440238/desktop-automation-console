"""稳健的窗口前置与窗口截图（放在文件末尾覆盖前面的简单实现）。

为什么要覆盖：
- 本机 pywin32 的 `win32gui` 没有 `PrintWindow`，原实现每次都静默失败，
  退回屏幕截图后会抓到遮挡在前面的窗口。
- `SetForegroundWindow` 会被 Windows 的前台抢占保护拦下，
  需要 AttachThreadInput 才能稳定生效。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PIL import Image

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
PW_RENDERFULLCONTENT = 2


def is_locked() -> bool:
    """屏幕是否锁定：锁定时输入事件到不了应用，截图也可能是旧帧。"""
    try:
        DESKTOP_SWITCHDESKTOP = 0x0100
        h = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if h:
            user32.CloseDesktop(h)
            return False
        return True
    except Exception:
        return False


def activate(hwnd: int) -> bool:
    """把窗口真正搬到前台（含 AttachThreadInput，绕过前台抢占限制）。"""
    try:
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, SW_SHOW)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)

        # 先置顶再取消置顶：比单纯 SetForegroundWindow 可靠
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

        fg = user32.GetForegroundWindow()
        if fg != hwnd:
            tid_fg = user32.GetWindowThreadProcessId(fg, None)
            tid_me = kernel32.GetCurrentThreadId()
            attached = False
            try:
                attached = bool(user32.AttachThreadInput(tid_fg, tid_me, True))
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(tid_fg, tid_me, False)

        time.sleep(0.35)
        return bool(user32.GetForegroundWindow() == hwnd or user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def capture_window(hwnd: int):
    """抓窗口画面。

    顺序很重要：
    1. 窗口在前台/可见时优先用屏幕截图（GDI），因为 QQ 这类 Electron 应用
       的 PrintWindow 会返回不更新的缓存帧，拿去 OCR 会一直看到旧画面；
    2. 只在屏幕截图失败（窗口被遮挡、锁屏）时才退回 PrintWindow。
    """
    if is_locked():
        raise RuntimeError("屏幕已锁定，无法获取真实画面（请解锁后重试）")

    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    box = (r.left, r.top, r.right, r.bottom)
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise RuntimeError("窗口尺寸异常")

    from PIL import ImageGrab

    try:
        return ImageGrab.grab(bbox=box, all_screens=True)
    except Exception:
        pass

    # 兜底：PrintWindow
    try:
        import win32gui
        import win32ui

        hdc = win32gui.GetWindowDC(hwnd)
        src = win32ui.CreateDCFromHandle(hdc)
        mem = src.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src, w, h)
        mem.SelectObject(bmp)
        if user32.PrintWindow(hwnd, mem.GetSafeHdc(), PW_RENDERFULLCONTENT):
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1
            ).copy()
            win32gui.DeleteObject(bmp.GetHandle())
            mem.DeleteDC()
            src.DeleteDC()
            win32gui.ReleaseDC(hwnd, hdc)
            return img
    except Exception:
        pass

    raise RuntimeError("拿不到窗口画面")
