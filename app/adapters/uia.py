"""Windows 桌面自动化底层辅助。

两个原则：
1. 只操作目标进程自己的窗口，绝不模拟全局热键去干扰别的程序。
2. 所有 pywinauto / COM 调用都放到单独的工作线程里执行，避免污染 FastAPI 的事件循环。
"""
from __future__ import annotations

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterable

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia")


# ---------------------------------------------------------------- 线程/COM
def _with_com(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    pythoncom = None
    try:
        import pythoncom  # type: ignore

        pythoncom.CoInitialize()
    except Exception:
        pythoncom = None
    try:
        return fn(*args, **kwargs)
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


async def run_sync(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """在线程池中执行同步的桌面操作。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: _with_com(fn, *args, **kwargs))


# ---------------------------------------------------------------- 窗口枚举
@dataclass
class WinInfo:
    hwnd: int
    title: str
    cls: str
    pid: int
    proc: str
    rect: tuple[int, int, int, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "class": self.cls,
            "pid": self.pid,
            "process": self.proc,
            "rect": list(self.rect),
        }


def list_windows(process_names: Iterable[str] | None = None, include_hidden: bool = False) -> list[WinInfo]:
    import psutil
    import win32gui
    import win32process

    wanted = {p.lower() for p in (process_names or [])} if process_names else None
    out: list[WinInfo] = []

    def _cb(hwnd: int, _lparam: Any) -> bool:
        try:
            if not include_hidden and not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title.strip():
                return True
            _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid).name()
            except Exception:
                proc = ""
            if wanted is not None and proc.lower() not in wanted:
                return True
            cls = win32gui.GetClassName(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            out.append(WinInfo(hwnd, title, cls, pid, proc, rect))
        except Exception:
            return True
        return True

    win32gui.EnumWindows(_cb, None)
    out.sort(key=lambda w: (w.rect[2] - w.rect[0]) * (w.rect[3] - w.rect[1]), reverse=True)
    return out


def find_window(process_names: Iterable[str], title_re: str = "", include_hidden: bool = False) -> WinInfo | None:
    wins = list_windows(process_names, include_hidden=include_hidden)
    if not wins:
        return None
    if title_re:
        pat = re.compile(title_re, re.I)
        for w in wins:
            if pat.search(w.title):
                return w
    for w in wins:
        if w.rect[2] - w.rect[0] > 200 and w.rect[3] - w.rect[1] > 200:
            return w
    return wins[0]


def process_running(names: Iterable[str]) -> list[str]:
    import psutil

    running = set()
    for p in psutil.process_iter(["name"]):
        try:
            n = (p.info.get("name") or "").lower()
            for want in names:
                if n == want.lower():
                    running.add(want)
        except Exception:
            continue
    return sorted(running)


def launch(exe: str, timeout: float = 0.0) -> bool:
    import subprocess

    if not exe:
        return False
    try:
        subprocess.Popen([exe], close_fds=True)
        if timeout:
            time.sleep(timeout)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 输入
def type_unicode(text: str, delay: float = 0.01) -> bool:
    """直接把字符作为 Unicode 输入事件发出去，不经过剪贴板。

    剪贴板常被别的程序占着（自动化工具、截图工具、输入法），
    这条路绕开它，中文也能逐字输入。
    """
    import win32api
    import win32con

    if not text:
        return False
    try:
        for ch in text:
            code = ord(ch)
            win32api.keybd_event(0, code, win32con.KEYEVENTF_UNICODE, 0)
            win32api.keybd_event(0, code, win32con.KEYEVENTF_UNICODE | win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(delay)
        return True
    except Exception:
        return False


def set_clipboard(text: str) -> bool:
    """把文本放进剪贴板，用于把中文粘贴进聊天框。"""
    import win32clipboard
    import win32con

    for _ in range(6):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            time.sleep(0.12)
    return False


def send_keys(seq: str, delay: float = 0.05) -> None:
    from pywinauto.keyboard import send_keys as _sk

    _sk(seq, pause=delay, with_spaces=True)


def connect(hwnd: int) -> Any:
    """返回 pywinauto 的 WindowSpecification。UIA 失败时退回 win32。"""
    from pywinauto import Application

    last: Exception | None = None
    for backend in ("uia", "win32"):
        try:
            app = Application(backend=backend).connect(handle=hwnd, timeout=5)
            win = app.window(handle=hwnd)
            _ = win.class_name()  # 触发一次真实调用，确认连得上
            return win
        except Exception as exc:  # 继续尝试下一个 backend
            last = exc
    raise RuntimeError(f"无法连接窗口 {hwnd}：{last}")


def focus_window(hwnd: int) -> None:
    import win32con
    import win32gui

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # SetForegroundWindow 在部分前台锁场景会失败，退化为 Alt 辅助法
        try:
            send_keys("%{TAB}")
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
    time.sleep(0.25)


def capture(hwnd: int, path: Any) -> str | None:
    """截取目标窗口区域，作为审计证据。"""
    try:
        from PIL import ImageGrab

        rect = None
        import win32gui

        rect = win32gui.GetWindowRect(hwnd)
        img = ImageGrab.grab(bbox=rect, all_screens=True)
        img.save(str(path))
        return str(path)
    except Exception:
        return None


def activate(hwnd: int) -> bool:
    """把窗口从托盘/最小化状态真正唤到前台，返回是否可见。"""
    import win32con
    import win32gui

    try:
        if not win32gui.IsWindowVisible(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:
        pass
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    try:
        win32gui.BringWindowToTop(hwnd)
    except Exception:
        pass
    focus_window(hwnd)
    time.sleep(0.4)
    try:
        return bool(win32gui.IsWindowVisible(hwnd))
    except Exception:
        return False


def dump_tree(win: Any, max_depth: int = 4, max_items: int = 80) -> list[dict[str, Any]]:
    """把控件树的前若干层导出来，供前端「探测」查看并据此校准选择器。"""
    out: list[dict[str, Any]] = []

    def _walk(ctrl: Any, depth: int) -> None:
        if depth > max_depth or len(out) >= max_items:
            return
        try:
            info = {
                "depth": depth,
                "type": ctrl.element_info.control_type,
                "class": ctrl.element_info.class_name,
                "name": (ctrl.element_info.name or "")[:60],
                "auto_id": ctrl.element_info.automation_id,
                "rect": list(ctrl.rectangle()),
            }
        except Exception:
            return
        out.append(info)
        try:
            children = ctrl.children()
        except Exception:
            return
        for ch in children:
            _walk(ch, depth + 1)

    _walk(win, 0)
    return out


def find_edit(win: Any, prefer_large: bool = True) -> Any | None:
    """在窗口里找一个最适合输入的 Edit 控件。"""
    cands: list[Any] = []
    try:
        cands = [c for c in win.descendants(control_type="Edit") if c.is_visible()]
    except Exception:
        try:
            cands = [c for c in win.descendants() if (c.element_info.control_type or "") == "Edit" and c.is_visible()]
        except Exception:
            cands = []
    if not cands:
        return None
    if not prefer_large:
        return cands[0]

    def _area(c: Any) -> int:
        try:
            r = c.rectangle()
            return max(0, r.right - r.left) * max(0, r.bottom - r.top)
        except Exception:
            return 0

    return max(cands, key=_area)
