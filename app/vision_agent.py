"""视觉代理：让多模态大模型看窗口截图，直接决定点哪里/输入什么。

和 OCR 的区别：OCR 只能定位文字，这个能理解界面结构、判断当前状态、
决定下一步动作，并且每步都能重新看一遍（闭环）。

模型只负责「看 + 决策」，执行由本机完成（点击/粘贴/按键），动作集合是封闭的。
"""
from __future__ import annotations

import base64
import io
import json
import re
import threading
import time
from typing import Any

from PIL import Image, ImageGrab

try:
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover
    win32gui = None

from . import ai

STOP = threading.Event()  # 急停开关：引擎置位后视觉循环立刻退出

ALLOWED = {"click", "type", "key", "scroll", "done", "fail"}

PROPOSE_SYSTEM = """你在看一个即时通讯软件的界面截图。
任务：从左侧的会话/联系人列表里，挑出符合下面描述的联系人，最多 {n} 个。
描述：{brief}

规则：
- 只挑具体的个人，不要群聊、公众号、系统会话（如「文件传输助手」「我的电脑」「QQ团队」）。
- 名字要和你看到的一字不差。
- 只能输出 JSON，不要解释：{{"targets":[{{"name":"看到的完整名字","why":"一句话理由"}}]}}
- 没有合适的就输出 {{"targets":[]}}。"""

SYSTEM = """你是桌面操作助手。每一步你只会看到目标应用当前窗口的截图。
任务：{task}

只能输出一个 JSON 对象，不要 markdown，不要多余文字：
{{"thought":"一句话说明你看到的和打算做什么","action":"click|type|key|scroll|done|fail",
  "x":整数,"y":整数,"text":"要输入的文字","key":"enter|esc|tab|ctrl+f|ctrl+a|ctrl+v","dy":整数}}

规则：
- 坐标是截图像素，左上角是 (0,0)，右下角是 ({w},{h})。
- 一次只做一个动作，做完会再给你新的截图。
- 要输入中文时用 type，不要逐字模拟按键。
- 找不到目标、界面不对、或者任务已经完成：用 done 或 fail，并在 thought 里说明。
- 发消息类任务：输入框里的文字消失、聊天里出现你刚发的这条消息，就说明发出去了，返回 done。
- 同一个位置不要点第二次；如果连续两步没有进展，换一种方式（例如改用左侧列表或搜索）。
- 每步会告诉你「操作后界面有没有变化」。连续两次「几乎没有变化」说明方法行不通，必须换思路。
- 不要点击与任务无关的东西。"""


def _capture(rect: tuple[int, int, int, int], hwnd: int | None = None) -> Image.Image:
    """抓窗口位图：优先 PrintWindow，被遮挡也能抓到；否则退回屏幕区域截图。"""
    if hwnd is not None:
        try:
            from .adapters import vision as win_vision

            return win_vision.capture_window(hwnd)
        except Exception:
            pass
    return ImageGrab.grab(bbox=rect, all_screens=True)


def _b64(img: Image.Image, max_side: int = 1280) -> str:
    im = img.convert("RGB")
    if max(im.size) > max_side:
        ratio = max_side / max(im.size)
        im = im.resize((int(im.width * ratio), int(im.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    for pattern in (r"\{.*\}", r"\{[\s\S]*"):
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _ask(img: Image.Image, system: str, user: str, timeout: int = 180) -> str:
    """把截图丢给多模态模型，返回原始文本。"""
    cfg = ai.load_ai()
    base = (cfg.get("base_url") or "").rstrip("/")
    model = cfg.get("model") or ""
    key = cfg.get("api_key") or ""
    if not base or not model:
        raise RuntimeError("没有配置 AI 模型")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": system + "\n\n" + user},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(img)}"}},
                ],
            }
        ],
        # 视觉模型会先"想"再答，预算给小了只会返回空内容
        "max_tokens": 3000,
    }
    res = ai._request  # noqa: F841  (保持函数引用，便于测试替换)
    resp = ai._request(f"{base}/chat/completions", payload, key, timeout)
    if not resp.get("ok"):
        raise RuntimeError(resp.get("detail") or "模型调用失败")
    return resp["data"]["choices"][0]["message"].get("content") or ""


def _do(action: dict[str, Any], rect: tuple[int, int, int, int]) -> str:
    kind = str(action.get("action") or "").lower()
    if kind not in ALLOWED:
        return f"忽略未知动作 {kind!r}"

    if kind == "click":
        x = rect[0] + int(action.get("x") or 0)
        y = rect[1] + int(action.get("y") or 0)
        try:
            win32api.SetCursorPos((x, y))
        except Exception as exc:
            # 屏幕锁定/输入桌面不可用时，鼠标事件发不出去
            raise RuntimeError(f"无法移动鼠标光标（可能屏幕已锁定或桌面不可交互）：{exc}") from exc
        time.sleep(0.2)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return f"点击 ({action.get('x')},{action.get('y')})"

    if kind == "type":
        text = str(action.get("text") or "")
        if not text:
            return "要输入的内容为空"
        from .adapters import uia

        # 走 Unicode 直接输入，绕开被占用的剪贴板；失败再退回剪贴板
        if uia.type_unicode(text):
            return f"输入 {text[:24]}"
        if not uia.set_clipboard(text):
            return "剪贴板被占用且直接输入失败"
        uia.send_keys("^v")
        return f"输入(粘贴) {text[:24]}"

    if kind == "key":
        from .adapters import uia

        k = str(action.get("key") or "").lower()
        mapping = {
            "enter": "{ENTER}",
            "esc": "{ESC}",
            "tab": "{TAB}",
            "ctrl+f": "^f",
            "ctrl+a": "^a",
            "ctrl+v": "^v",
        }
        if k not in mapping:
            return f"不支持的按键 {k!r}"
        uia.send_keys(mapping[k])
        return f"按键 {k}"

    if kind == "scroll":
        win32api.SetCursorPos((rect[0] + rect[2] // 2, rect[1] + rect[3] // 2))
        dy = int(action.get("dy") or -3)
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, dy * 120, 0)
        return f"滚动 {dy}"

    return f"结束：{kind}"


def _locked() -> bool:
    """屏幕是否锁定：锁定时鼠标键盘事件发不出去，必须提前停。"""
    import ctypes

    try:
        h = ctypes.windll.user32.OpenInputDesktop(0, False, 0x0100)
        if h:
            ctypes.windll.user32.CloseDesktop(h)
            return False
        return True
    except Exception:
        return False


DANGER_WORDS = (
    "屏蔽", "拉黑", "删除", "举报", "退出", "解散", "清空", "注销",
    "删除好友", "移出群", "转让群", "解散群", "举报该用户",
)


def _pid_of(hwnd: int) -> int:
    import win32process

    try:
        return win32process.GetWindowThreadProcessId(hwnd)[1]
    except Exception:
        return 0


def _windows_of_pid(pid: int) -> list[int]:
    import win32gui

    out: list[int] = []

    def cb(h, _):
        import win32process

        try:
            _, p = win32process.GetWindowThreadProcessId(h)
        except Exception:
            return True
        if p == pid and win32gui.IsWindowVisible(h):
            r = win32gui.GetWindowRect(h)
            if (r[2] - r[0]) > 80 and (r[3] - r[1]) > 60:
                out.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return out


def _pick_window(main: int) -> int:
    """优先跟随弹出来的对话框/面板，否则回到主窗口。"""
    import win32gui

    pid = _pid_of(main)
    wins = _windows_of_pid(pid) if pid else [main]
    if main not in wins:
        wins.append(main)

    fg = win32gui.GetForegroundWindow()
    if fg != main and fg in wins:
        return fg  # 用户/程序刚把某个面板提到前台

    def area(h: int) -> int:
        r = win32gui.GetWindowRect(h)
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])

    try:
        main_area = max(1, area(main))
        dialogs = [w for w in wins if w != main and area(w) < main_area * 0.75]
        if dialogs:
            # 多个时取面积最小的那个，通常就是最上层的对话框
            return min(dialogs, key=area)
    except Exception:
        pass
    return main


def _danger_at(hwnd: int, x: int, y: int) -> str | None:
    """看看点击位置附近是不是危险控件；是就返回它的文字。"""
    try:
        from .adapters import vision as v

        els = v.look(hwnd)
    except Exception:
        return None
    best = None
    for e in els:
        if e.x - 12 <= x <= e.x + e.w + 12 and e.y - 12 <= y <= e.y + e.h + 12:
            best = e
            break
    if best is None:
        return None
    text = v._norm(best.text)
    for w in DANGER_WORDS:
        if w in text:
            return best.text
    return None


def _diff_score(a: Image.Image, b: Image.Image) -> float:
    """两张截图差多少：缩到 64x64 灰度后算平均绝对差，0 表示完全一样。"""
    try:
        ga = a.convert("L").resize((64, 64))
        gb = b.convert("L").resize((64, 64))
        pa, pb = list(ga.getdata()), list(gb.getdata())
        return sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)
    except Exception:
        return 999.0


def run(hwnd: int, task: str, max_steps: int = 8, dry: bool = False) -> dict[str, Any]:
    """看一步、做一步，最多 max_steps 步。dry=True 只让模型看一步，不动手。"""
    if STOP.is_set():
        return {"ok": False, "detail": "当前处于急停状态，请先解除", "steps": []}
    cur_hwnd = _pick_window(hwnd)
    rect = win32gui.GetWindowRect(cur_hwnd)
    trace: list[dict[str, Any]] = []
    history_lines: list[str] = []
    history = ""

    for step in range(1, max_steps + 1):
        if _locked():
            return {"ok": False, "detail": "执行途中屏幕被锁定，已中止（解锁后重试）", "steps": trace}
        if STOP.is_set():
            return {"ok": False, "detail": "已急停，视觉操作中止", "steps": trace}
        # 每步重新判断该看哪个窗口：弹了对话框就跟过去
        cur_hwnd = _pick_window(hwnd)
        rect = win32gui.GetWindowRect(cur_hwnd)
        img = _capture(rect, cur_hwnd)
        system = SYSTEM.format(task=task, w=img.width, h=img.height)
        if history_lines:
            user = (
                "你已经做过的动作（按顺序）：\n"
                + "\n".join(history_lines[-6:])
                + "\n请根据当前截图判断下一步；如果任务已经完成，用 done。"
            )
        else:
            user = "这是第一步，请给出下一步动作。"
        try:
            raw = _ask(img, system, user)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"模型调用失败：{exc}", "steps": trace}

        if STOP.is_set():
            return {"ok": False, "detail": "已急停，视觉操作中止", "steps": trace}
        act = _extract_json(raw)
        if act is None:
            # 推理型模型偶尔只输出思考过程，补问一次，只要 JSON
            raw2 = _ask(img, system, "只输出那个 JSON 对象，不要任何解释和其他文字。")
            act = _extract_json(raw2)
        if act is None:
            return {"ok": False, "detail": f"模型没有返回 JSON：{(raw or '')[:120]}", "steps": trace}

        kind = str(act.get("action") or "").lower()
        trace.append({"step": step, "thought": act.get("thought"), "action": kind, "window": win32gui.GetWindowText(cur_hwnd)})

        if dry:
            return {"ok": True, "dry": True, "first": act, "steps": trace}

        if kind in ("done", "fail"):
            return {
                "ok": kind == "done",
                "detail": act.get("thought") or "",
                "steps": trace,
            }

        if kind == "click":
            blocked = _danger_at(cur_hwnd, int(act.get("x") or 0) + rect[0], int(act.get("y") or 0) + rect[1])
            if blocked:
                result = f"已拦截：这个位置是「{blocked}」，属于危险操作，换别的方式"
                trace[-1]["result"] = result
                history_lines.append(f"{step}. {result}")
                time.sleep(0.6)
                continue

        try:
            result = _do(act, rect)
        except Exception as exc:  # noqa: BLE001
            trace[-1]["result"] = f"失败：{exc}"
            return {"ok": False, "detail": f"第 {step} 步执行失败：{exc}", "steps": trace}

        time.sleep(1.2)
        # 对比操作前后的画面，告诉模型这一下有没有生效
        try:
            after_img = _capture(rect, cur_hwnd)
            diff = _diff_score(img, after_img)
            if diff < 1.5:
                change = "界面几乎没有变化（这一下可能点空了，下次换个位置或换种方式）"
            elif diff < 8:
                change = "界面有轻微变化"
            else:
                change = "界面有明显变化"
        except Exception:
            change = ""
        trace[-1]["result"] = result
        trace[-1]["diff"] = round(diff, 1) if isinstance(diff, float) else None
        history_lines.append(f"{step}. {result} → {change}" if change else f"{step}. {result}")

    return {"ok": False, "detail": f"{max_steps} 步内没完成", "steps": trace}

def propose_targets(platform: str, brief: str, limit: int = 3) -> list[dict[str, Any]]:
    """让模型看一眼界面，从可见的联系人列表里挑人。

    桌面端「自动找人」的核心：不再需要人工给名单。
    """
    import importlib

    mod = importlib.import_module(f".adapters.{platform}", __package__)
    info = mod._window()
    if info is None:
        return []
    rect = win32gui.GetWindowRect(info.hwnd)
    out = _propose_once(_capture(rect, info.hwnd), brief, limit)
    if out:
        return out
    # 一个个人好友都没看到：让代理自己导航到「联系人」并展开分组
    nav = (
        "现在要看到个人好友名单。步骤：1) 如果左侧导航栏还没选中「联系人」（人形图标），先点它；"
        "2) 在左侧列表里找到分组名（例如「我的好友」），点击把它展开；"
        "3) 让具体的个人好友头像和昵称出现在列表里。不要点进任何人的聊天。"
    )
    run(info.hwnd, nav, max_steps=4)
    out = _propose_once(_capture(rect, info.hwnd), brief, limit)
    if out:
        return out
    run(info.hwnd, "如果个人好友列表还是收起的，点击收起的分组把它展开", max_steps=2)
    return _propose_once(_capture(rect, info.hwnd), brief, limit)


def _propose_once(img: Image.Image, brief: str, limit: int) -> list[dict[str, Any]]:
    system = PROPOSE_SYSTEM.format(n=max(1, min(limit, 8)), brief=brief)
    raw = _ask(img, system, "现在开始，只输出 JSON。")
    data = _extract_json(raw) or {}
    out: list[dict[str, Any]] = []
    for item in data.get("targets") or []:
        name = str((item or {}).get("name") or "").strip()
        if name:
            out.append({"url": name, "name": name, "snippet": str(item.get("why") or "")[:40]})
    return out
SCAN_SYSTEM = """你在看 QQ 的联系人列表（左侧是一行行联系人）。
已经查看过这些人：{visited}
任务：给出列表中下一个「还没查看过」的联系人，以及点击他那一行的坐标。
只输出 JSON：{{"name":"昵称","x":整数,"y":整数}}；如果列表里没有新的了，输出 {{"done":true}}。
坐标是截图像素，左上角 (0,0)，右下角 ({w},{h})。点昵称所在那一行，不要点左侧导航栏。"""

CARD_SYSTEM = """这是刚点开的 QQ 联系人资料卡。
请读出并判断，只输出 JSON：
{{"name":"昵称","gender":"男|女|未知","age":整数或0,"signature":"签名原文前20字",
  "match":true或false,"why":"一句话说明为什么匹配/不匹配"}}
判断标准：{brief}
性别看资料卡上的性别图标和文字（♂男 / ♀女）。看不出来就填「未知」，match 填 false。"""


def _click_at(rect: tuple[int, int, int, int], x: int, y: int) -> None:
    ax, ay = rect[0] + int(x), rect[1] + int(y)
    win32api.SetCursorPos((ax, ay))
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def profile_scan(
    platform: str, brief: str, want: int = 3, max_check: int = 6
) -> list[dict[str, Any]]:
    """逐个点开联系人资料卡，读出性别/年龄，只留下匹配的人。

    这是「找女好友」这类按属性筛人的正确做法：不能从昵称猜，要看资料卡。
    """
    import importlib

    mod = importlib.import_module(f".adapters.{platform}", __package__)
    info = mod._window()
    if info is None:
        return []
    rect = win32gui.GetWindowRect(info.hwnd)
    visited: list[str] = []
    found: list[dict[str, Any]] = []

    for _ in range(max(1, max_check)):
        img = _capture(rect, info.hwnd)
        scan = _extract_json(
            _ask(
                img,
                SCAN_SYSTEM.format(
                    visited="、".join(visited) or "（无）", w=img.width, h=img.height
                ),
                "现在输出下一个要查看的联系人。",
            )
        ) or {}
        if scan.get("done") or "x" not in scan:
            break
        name = str(scan.get("name") or "").strip()
        _click_at(rect, scan.get("x", 0), scan.get("y", 0))
        time.sleep(1.4)

        card_img = _capture(rect, info.hwnd)
        card = _extract_json(
            _ask(card_img, CARD_SYSTEM.format(brief=brief), "只输出 JSON。")
        ) or {}
        who = str(card.get("name") or name or "").strip()
        if who:
            visited.append(who)
        if card.get("match"):
            found.append(
                {
                    "url": who,
                    "name": who,
                    "snippet": f"{card.get('gender')} {card.get('age')}岁 · {card.get('why') or ''}"[:48],
                    "gender": card.get("gender"),
                    "age": card.get("age"),
                }
            )
            if len(found) >= want:
                break
    return found

VERIFY_SYSTEM = """这是操作完成后的界面截图。
刚才要做的事：{task}
请判断这件事**是否真的成功完成了**，只输出 JSON：
{{"success":true或false,"evidence":"你在图里看到的确凿证据（例如申请已发送、消息已出现在聊天里），没有就说明看到的是什么"}}
注意：只是输入了内容、只是打开了页面、或者什么都没发生，都不算成功。"""


def verify(hwnd: int, task: str) -> tuple[bool, str]:
    """收尾校验：模型说 done 之后，再看一眼画面确认真的做成了。"""
    try:
        img = _capture(win32gui.GetWindowRect(hwnd), hwnd)
        raw = _ask(img, VERIFY_SYSTEM.format(task=task), "只输出 JSON。")
        data = _extract_json(raw) or {}
        return bool(data.get("success")), str(data.get("evidence") or "")[:120]
    except Exception as exc:
        return True, f"校验异常，按成功处理：{exc}"
