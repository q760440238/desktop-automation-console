"""输入恢复：QQ 的输入队列卡住时，重启应用再继续。

症状：窗口响应 WM_NULL（没死）、Z 序也对（没被挡），但合成的鼠标/键盘事件
全部落空——点哪都没反应，看起来像"卡死"。重启应用可以恢复。
"""
from __future__ import annotations

import subprocess
import time
from typing import Any


def restart_app(
    proc_names: list[str], exe: str, window_matcher: Any, wait: float = 20.0
) -> dict[str, Any]:
    """杀掉进程并用 explorer 重新拉起（等同用户手动双击），等主窗口出现。"""
    import psutil

    killed = 0
    for p in psutil.process_iter(["pid", "name"]):
        name = (p.info["name"] or "").lower()
        if any(name.startswith(n.lower()) for n in proc_names):
            try:
                p.kill()
                killed += 1
            except Exception:
                pass

    time.sleep(3.0)
    try:
        subprocess.Popen(["explorer.exe", exe])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"重新启动失败：{exc}", "killed": killed}

    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(2.0)
        try:
            if window_matcher() is not None:
                return {
                    "ok": True,
                    "detail": f"已重启应用（结束 {killed} 个进程）并找到主窗口",
                    "killed": killed,
                }
        except Exception:
            pass
    return {
        "ok": False,
        "detail": f"已重启但 {int(wait)} 秒内没等到主窗口（可能需要手机确认登录）",
        "killed": killed,
    }


def input_seems_dead(before: Any, after: Any) -> bool:
    """连点两次画面都没变，多半是输入没送达。"""
    try:
        return before.tobytes() == after.tobytes()
    except Exception:
        return False
