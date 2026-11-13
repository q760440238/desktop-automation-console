"""自主探索：让模型自己试，成功的做法蒸馏成配方存进经验库。

流程：
1. 给一个目标（例如「在 QQ 里加 白菜小哥 为好友」），让视觉代理自由尝试；
2. 成功后，把整段操作轨迹交给模型，让它写成「可复用的步骤」；
3. 连同平台、动作、目标一起存进 knowledge，下次同类任务先检索出来当提示。
"""
from __future__ import annotations

import json
from typing import Any

from . import ai, knowledge, vision_agent

EXPLORE_SYSTEM = """你是一个会自己摸索的桌面操作员。
目标：{goal}

你可以自由尝试任何办法（点按钮、用搜索框、右键、快捷键都可）。
每步只能做一个动作，做完会给你新的截图和「界面有没有变化」的反馈。

要求：
- 如果某种方式点了没反应，就换一种，不要连续三次重复同一下。
- 达成目标后用 done；确实做不到用 fail，并在 thought 里说清楚卡在哪。
- 只输出 JSON：{{"thought":"...","action":"click|type|key|scroll|done|fail","x":0,"y":0,"text":"","key":""}}"""

DISTILL_SYSTEM = """下面是一次成功的桌面操作过程（含每步的思考与执行结果）。
目标：{goal}

请把它总结成「下次可以直接照做的步骤」，只输出 JSON：
{{"title":"一句话标题","steps":["第一步做什么","第二步做什么"],
  "tips":["容易踩的坑或关键位置"]}}
要求：步骤具体到"点哪里、输入什么"，不要写"打开界面"这种空话；3-7 步为宜。"""


def explore(platform: str, goal: str, action: str = "", max_steps: int = 25) -> dict[str, Any]:
    """让模型自己试一遍，成功则蒸馏成配方入库。"""
    import importlib

    mod = importlib.import_module(f".adapters.{platform}", __package__)
    info = mod._window()
    if info is None:
        return {"ok": False, "detail": "窗口不可见，先启动并登录应用"}

    # 把已有经验作为参考
    hints = knowledge.render(knowledge.find(platform, action, goal))
    task = goal + (f"\n\n{hints}" if hints else "")

    res = vision_agent.run(info.hwnd, task, max_steps=max_steps)
    steps = res.get("steps") or []

    if not res.get("ok"):
        # 失败也要沉淀：记下走过的死路，下次别再试同样的地方
        dead = [
            f"点 ({s.get('x')},{s.get('y')}) 无效：{str(s.get('thought'))[:60]}"
            for s in steps
            if s.get("action") == "click"
        ][:6]
        try:
            knowledge.save(
                {
                    "platform": platform,
                    "action": action,
                    "goal": goal,
                    "title": f"（未成功）{goal}",
                    "steps": [],
                    "tips": dead,
                    "success": False,
                    "raw_steps": len(steps),
                }
            )
        except Exception:
            pass
        return {
            "ok": False,
            "detail": res.get("detail") or "没做成",
            "steps": steps,
            "learned": False,
        }

    # 蒸馏成配方
    trail = "\n".join(
        f"{s.get('step')}. {s.get('thought')} → {s.get('result') or ''}" for s in steps
    )
    recipe: dict[str, Any] = {}
    try:
        raw = ai._completion(
            DISTILL_SYSTEM.format(goal=goal), trail, timeout=120, max_tokens=1500
        )
        recipe = vision_agent._extract_json(raw) or {}
    except Exception as exc:  # noqa: BLE001
        recipe = {"title": goal, "steps": [], "tips": [f"蒸馏失败：{exc}"]}

    entry = {
        "platform": platform,
        "action": action,
        "goal": goal,
        "title": recipe.get("title") or goal,
        "steps": recipe.get("steps") or [],
        "tips": recipe.get("tips") or [],
        "success": True,
        "raw_steps": len(steps),
    }
    knowledge.save(entry)
    return {"ok": True, "learned": True, "recipe": entry, "steps": steps}
