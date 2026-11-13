"""桌面视觉：截窗口 → OCR → 按文字定位与点击。

用途：
1. UIA 拿不到控件时（QQ NT 是 Electron），靠"看字"定位搜索框、按钮、会话标题；
2. 发送前校验当前会话标题是不是目标人，避免把消息发错人；
3. 发送后确认消息真的出现在会话里。

不依赖任何模型，用的是 Windows 自带 OCR（winsdk + Windows.Media.Ocr）。
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

try:  # Windows 才有
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover
    win32gui = None


@dataclass
class Element:
    text: str
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


def _norm(s: str) -> str:
    """OCR 会在汉字之间加空格，匹配前先抹掉空白和标点差异。"""
    return re.sub(r"[\s\u3000]+", "", s or "")


def _capture(rect: tuple[int, int, int, int]) -> Image.Image:
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=rect, all_screens=True)


async def _ocr_file(path: str) -> list[Element]:
    """用 Windows 自带 OCR 识别一张图（走 StorageFile，内存流解码不可靠）。"""
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage import FileAccessMode, StorageFile

    file = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return []
    result = await engine.recognize_async(bitmap)

    out: list[Element] = []
    for line in result.lines:
        words = list(line.words)
        if not words:
            continue
        x0 = int(min(w.bounding_rect.x for w in words))
        y0 = int(min(w.bounding_rect.y for w in words))
        x1 = int(max(w.bounding_rect.x + w.bounding_rect.width for w in words))
        y1 = int(max(w.bounding_rect.y + w.bounding_rect.height for w in words))
        out.append(Element(line.text, x0, y0, x1 - x0, y1 - y0))
    return out

def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    return win32gui.GetWindowRect(hwnd)


def look(hwnd: int, save_to: str | Path | None = None) -> list[Element]:
    """看这个窗口：截图 → 落盘 → OCR，返回屏幕坐标下的文字块。"""
    import tempfile

    rect = window_rect(hwnd)
    img = capture_window(hwnd)
    p = Path(save_to) if save_to else Path(tempfile.gettempdir()) / "dac_vision.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    els = asyncio.run(_ocr_file(str(p)))
    # OCR 坐标是相对截图的，换算成屏幕坐标方便点击
    ox, oy = rect[0], rect[1]
    for e in els:
        e.x += ox
        e.y += oy
    return els


def find(els: list[Element], needle: str, exact: bool = False) -> Element | None:
    """在 OCR 结果里找一段文字：先精确，再包含，最后取最短的包含匹配。"""
    key = _norm(needle)
    if not key:
        return None
    hits = []
    for e in els:
        t = _norm(e.text)
        if not t:
            continue
        if exact and t == key:
            return e
        if key in t:
            hits.append((len(t), e))
    if not hits:
        return None
    hits.sort(key=lambda p: p[0])
    return hits[0][1]


def post_click(hwnd: int, screen_x: int, screen_y: int) -> bool:
    """用 PostMessage 投递一次点击（客户区坐标）。

    当系统输入队列被卡住、mouse_event 落空时，这条路径往往还能生效。
    """
    import time as _t
    import win32gui

    r = win32gui.GetWindowRect(hwnd)
    cx, cy = int(screen_x - r[0]), int(screen_y - r[1])
    lp = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
    try:
        win32gui.PostMessage(hwnd, 0x0200, 0, lp)  # WM_MOUSEMOVE
        _t.sleep(0.03)
        win32gui.PostMessage(hwnd, 0x0201, 0x0001, lp)  # WM_LBUTTONDOWN
        _t.sleep(0.05)
        win32gui.PostMessage(hwnd, 0x0202, 0, lp)  # WM_LBUTTONUP
        return True
    except Exception:
        return False


def click(el: Element, hwnd: int | None = None, fallback: bool = False) -> None:
    """把鼠标挪过去点一下；fallback=True 时改用 PostMessage 投递。"""
    if fallback and hwnd:
        post_click(hwnd, el.cx, el.cy)
        return
    win32api.SetCursorPos((el.cx, el.cy))
    time.sleep(0.15)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def click_text(hwnd: int, text: str, save_to: str | Path | None = None) -> bool:
    """看窗口 → 找到这段字 → 点它。找不到返回 False。"""
    els = look(hwnd, save_to)
    el = find(els, text)
    if el is None:
        return False
    click(el)
    return True


def texts(els: list[Element]) -> list[str]:
    return [_norm(e.text) for e in els if _norm(e.text)]


def header_has(hwnd: int, name: str, header_ratio: float = 0.16) -> tuple[bool, str]:
    """会话标题栏里有没有这个名字：取窗口顶部一条区域做 OCR。

    发送前的最后一道闸——标题不对就不发，宁可不发也不发错人。
    """
    els = look(hwnd)
    if not els:
        return False, "OCR 没有识别到任何文字"
    rect = window_rect(hwnd)
    top = rect[1] + int((rect[3] - rect[1]) * header_ratio)
    area = [e for e in els if e.y <= top]
    key = _norm(name)
    for e in area:
        if key and key in _norm(e.text):
            return True, e.text
    return False, " / ".join(texts(area))[:80]
def see_window(window_fn) -> dict:
    """给适配器用：看当前窗口，返回看到的文字块和关键控件在不在。"""
    info = window_fn()
    if info is None:
        return {"ok": False, "detail": "窗口不可见（可能最小化或在托盘）"}
    els = look(info.hwnd)
    return {
        "ok": True,
        "title": getattr(info, "title", ""),
        "count": len(els),
        "elements": [{"text": e.text, "x": e.cx, "y": e.cy} for e in els],
        "labels": {k: bool(find(els, k)) for k in ("搜索", "发送", "输入", "加好友", "加群")},
    }

def capture_window(hwnd: int):
    """优先用 PrintWindow 直接抓窗口位图（被别的窗口遮挡也能抓到），
    失败再退回屏幕区域截图。"""
    rect = win32gui.GetWindowRect(hwnd)
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    try:
        activate(hwnd)  # 先提到前台，否则退回屏幕截图会抓到别的窗口
    except Exception:
        pass
    if w <= 0 or h <= 0:
        raise RuntimeError("窗口尺寸异常")
    try:
        import win32ui

        hdc = win32gui.GetWindowDC(hwnd)
        src = win32ui.CreateDCFromHandle(hdc)
        mem = src.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src, w, h)
        mem.SelectObject(bmp)
        ok = win32gui.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
        if ok:
            info = bmp.GetInfo()
            bits = bmp.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1
            )
            win32gui.DeleteObject(bmp.GetHandle())
            mem.DeleteDC()
            src.DeleteDC()
            win32gui.ReleaseDC(hwnd, hdc)
            return img.copy()
    except Exception:
        pass
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=rect, all_screens=True)


# ---- 稳健实现覆盖上面的简单版本（本机 win32gui 没有 PrintWindow）----
from .win_focus import activate, capture_window  # noqa: E402,F811
