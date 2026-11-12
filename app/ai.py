"""AI 模型配置与调用（OpenAI 兼容协议）。

对应界面上「右上角 → AI 设置」那一组参数：
    服务商 / API 地址 / API Key / 模型 / 思考深度

设计取舍：
- 只支持 OpenAI 兼容的 /chat/completions 接口。DeepSeek、Moonshot、通义、硅基流动、
  OpenRouter、Ollama、vLLM 都符合这个形状，覆盖面足够，也避免为每家写一套适配。
- 思考深度映射到 `reasoning_effort`（o 系列 / GPT-5 / DeepSeek 等支持）；
  不支持的网关会忽略这个字段，不影响主流程。
- Key 存在本机 config/ai.json，接口只回传「是否已配置 + 末四位」，不回传明文。
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from .settings import CONFIG_DIR, ensure_dirs

AI_PATH = CONFIG_DIR / "ai.json"
_lock = threading.RLock()

THINKING_LEVELS = ("off", "low", "medium", "high")
THINKING_LABELS = {"off": "关闭", "low": "低", "medium": "中", "high": "高"}

DEFAULT_AI: dict[str, Any] = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
    "thinking": "medium",
    "temperature": 0.7,
    "timeout": 60,
}

# 常见服务商的默认值，界面上选「服务商」时自动带出
PROVIDERS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
    },
    "moonshot": {
        "name": "Moonshot 月之暗面",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0905-preview"],
    },
    "dashscope": {
        "name": "阿里通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
    },
    "siliconflow": {
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["anthropic/claude-sonnet-4", "google/gemini-2.5-pro"],
    },
    "ollama": {
        "name": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5:7b", "llama3.1:8b"],
    },
    "custom": {"name": "自定义（OpenAI 兼容）", "base_url": "", "models": []},
}


def load_ai() -> dict[str, Any]:
    ensure_dirs()
    with _lock:
        if not AI_PATH.exists():
            return dict(DEFAULT_AI)
        try:
            raw = json.loads(AI_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_AI)
    cfg = dict(DEFAULT_AI)
    cfg.update({k: v for k, v in raw.items() if v is not None})
    return cfg


def save_ai(patch: dict[str, Any]) -> dict[str, Any]:
    cfg = load_ai()
    for key in ("provider", "base_url", "model", "thinking", "temperature", "timeout"):
        if key in patch and patch[key] not in (None, ""):
            cfg[key] = patch[key]
    # 密钥单独处理：留空表示「不修改」，传 "-" 表示清空
    if "api_key" in patch:
        val = (patch.get("api_key") or "").strip()
        if val == "-":
            cfg["api_key"] = ""
        elif val:
            cfg["api_key"] = val
    with _lock:
        ensure_dirs()
        AI_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def public_view(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    c = cfg or load_ai()
    key = c.get("api_key") or ""
    return {
        "provider": c.get("provider", ""),
        "base_url": c.get("base_url", ""),
        "model": c.get("model", ""),
        "thinking": c.get("thinking", "medium"),
        "temperature": c.get("temperature", 0.7),
        "api_key_set": bool(key),
        "api_key_tail": key[-4:] if len(key) >= 4 else "",
        "providers": [
            {"key": k, "name": v["name"], "base_url": v["base_url"], "models": v["models"]}
            for k, v in PROVIDERS.items()
        ],
    }


def _request(url: str, payload: dict[str, Any] | None, api_key: str, timeout: int, method: str = "POST") -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        hint = {
            401: "API Key 无效或没有权限（401）",
            403: "该 Key 无权访问这个模型（403）",
            404: "接口地址不对，通常应以 /v1 结尾（404）",
            429: "请求过于频繁或额度用尽（429）",
        }.get(exc.code, f"服务端返回 {exc.code}")
        return {"ok": False, "detail": hint, "body": body, "status": exc.code}
    except urllib.error.URLError as exc:
        return {"ok": False, "detail": f"连不上接口地址：{exc.reason}"}
    except TimeoutError:
        return {"ok": False, "detail": "请求超时，检查网络或把超时时间调大"}
    except json.JSONDecodeError:
        return {"ok": False, "detail": "返回内容不是 JSON，接口地址可能填错了"}


def fetch_models(base_url: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    """拉取服务商的可用模型列表（GET /models）。

    界面上填完地址与 Key 就自动调用，让用户从列表里选，而不是手打模型名。
    不同网关返回结构不一：有 {data:[...]}，也有直接返回数组的，还有返回 {models:[...]} 的。
    """
    cfg = load_ai()
    base = (base_url or cfg.get("base_url") or "").rstrip("/")
    key = (api_key or cfg.get("api_key") or "").strip()
    local = "127.0.0.1" in base or "localhost" in base

    if not base:
        return {"ok": False, "detail": "请先填写 API 地址", "models": []}
    if not key and not local:
        return {"ok": False, "detail": "请先填写 API Key", "models": []}

    timeout = min(int(cfg.get("timeout", 60)), 30)
    res = _request(f"{base}/models", None, key, timeout, method="GET")
    if not res.get("ok"):
        detail = res.get("detail", "拉取模型失败")
        if res.get("status") in (404, 405):
            detail = "该网关没有 /models 接口，请手动填写模型名"
        return {"ok": False, "detail": detail, "models": [], "body": res.get("body", "")}

    data = res.get("data")
    items: list[Any] = []
    if isinstance(data, dict):
        for key_name in ("data", "models", "model_list"):
            if isinstance(data.get(key_name), list):
                items = data[key_name]
                break
    elif isinstance(data, list):
        items = data

    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("name") or it.get("model")
            if not mid:
                continue
            mid = str(mid)
            owned = str(it.get("owned_by") or it.get("publisher") or "")
            created = it.get("created")
        elif isinstance(it, str):
            mid, owned, created = it, "", None
        else:
            continue
        if mid in seen:
            continue
        seen.add(mid)
        models.append({"id": mid, "owned_by": owned, "created": created})

    models.sort(key=lambda m: m["id"].lower())
    return {
        "ok": True,
        "models": models,
        "count": len(models),
        "detail": f"获取到 {len(models)} 个模型" if models else "接口返回了空的模型列表",
    }


def test_connection(override: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = load_ai()
    if override:
        for k, v in override.items():
            if v:
                cfg[k] = v
    base = (cfg.get("base_url") or "").rstrip("/")
    key = cfg.get("api_key") or ""
    if not base:
        return {"ok": False, "detail": "请先填写 API 地址"}
    if not key and "127.0.0.1" not in base and "localhost" not in base:
        return {"ok": False, "detail": "请先填写 API Key"}

    timeout = min(int(cfg.get("timeout", 60)), 30)
    models = _request(f"{base}/models", None, key, timeout, method="GET")
    if models.get("ok"):
        data = models.get("data") or {}
        items = data.get("data") if isinstance(data, dict) else None
        count = len(items) if isinstance(items, list) else 0
        return {"ok": True, "detail": f"连接成功，可用模型 {count} 个", "models": [m.get("id") for m in (items or [])][:30]}

    # 有些网关不开放 /models，用一次最小对话兜底验证
    chat = _request(
        f"{base}/chat/completions",
        {"model": cfg.get("model"), "messages": [{"role": "user", "content": "ping"}], "max_tokens": 4},
        key,
        timeout,
    )
    if chat.get("ok"):
        return {"ok": True, "detail": "连接成功（该网关不支持模型列表，已用一次对话验证）"}
    return {"ok": False, "detail": chat.get("detail") or models.get("detail"), "body": chat.get("body", "")}


SYSTEM_PROMPT = (
    "你是一个社交场景的文案助手。用户会给你平台的限制条件和一句话意图，"
    "你只输出一条可以直接发送的中文消息正文：不要解释、不要引号、不要 emoji 堆砌，"
    "控制在 80 字以内，语气自然、像真人打字，不要出现「亲」「好评」这类营销词。"
)


RECOVERY_ACTIONS = ("retry", "switch_keyword", "reload", "wait", "stop")

RECOVERY_SYSTEM = (
    "你是社交自动化任务的巡检员。你会收到一次「没有进展」的诊断信息，"
    "请判断最可能的真实原因，并从下面五个动作里选一个最合适的：\n"
    "- retry：原样重试（偶发抖动）\n"
    "- switch_keyword：换个搜索词再试（当前方向搜不到人/结果不相关），需要给出 keywords（1-3 个短词）\n"
    "- reload：重启浏览器或重新加载页面（页面卡住、白屏、渲染异常）\n"
    "- wait：等一段时间再说（触发频控、需要冷却），需要给出 wait_seconds（30-600）\n"
    "- stop：必须人工介入（验证码、登录失效、账号受限）或方向本身不可行\n"
    "判断要保守：拿不准就选 stop，不要假装能绕过验证码。\n"
    "特别地：page_title / page_url 里出现「登录」「注册」「验证」「安全」字样时，说明需要人工登录，必须选 stop；"
    "tried_keywords 里已经出现过的词不要重复给出。\n"
    '只输出 JSON：{"diagnosis":"一句话原因","action":"...","keywords":["..."],"wait_seconds":0,"reason":"给用户看的一句话"}'
)


def _extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出里抠出第一个 JSON 对象，兼容 ```json 包裹和前后废话。"""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def decide_recovery(context: dict[str, Any]) -> dict[str, Any]:
    """让模型判断「卡住/没进展」的原因并给出下一步动作。

    动作是封闭集合，模型不能发明新操作；输出不是 JSON 时会重问一次，
    仍然失败则返回 ok=False，由调用方熔断（而不是盲目重试）。
    """
    cfg = load_ai()
    base = (cfg.get("base_url") or "").rstrip("/")
    key = cfg.get("api_key") or ""
    model = (cfg.get("model") or "").strip()
    if not base or not model:
        return {"ok": False, "detail": "未配置 AI 模型"}

    user_msg = json.dumps(context, ensure_ascii=False)[:3000]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RECOVERY_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    parsed: dict[str, Any] | None = None
    last_err = ""
    for attempt in range(2):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2 if attempt == 0 else 0.0,
            "stream": False,
            "max_tokens": 300,
        }
        res = _request(f"{base}/chat/completions", payload, key, min(int(cfg.get("timeout", 60)), 45))
        if not res.get("ok"):
            return {"ok": False, "detail": res.get("detail", "调用失败")}
        data = res.get("data") or {}
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return {"ok": False, "detail": "返回结构异常"}

        parsed = _extract_json(text)
        if parsed is not None:
            break
        last_err = text[:120] or "空回复"
        # 重问一次：把它的散文答案丢回去，要求只给 JSON
        messages = [
            {"role": "system", "content": RECOVERY_SYSTEM},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": text[:600]},
            {"role": "user", "content": "上面不是合法 JSON。请只输出一个 JSON 对象，不要解释、不要 Markdown。"},
        ]

    if parsed is None:
        return {"ok": False, "detail": f"模型两次都没有输出 JSON（{last_err}）"}

    action = str(parsed.get("action") or "").strip().lower()
    if action not in RECOVERY_ACTIONS:
        return {"ok": False, "detail": f"动作不在允许范围：{action}"}

    kws = [str(k).strip() for k in (parsed.get("keywords") or []) if str(k).strip()][:3]
    try:
        wait_s = int(parsed.get("wait_seconds") or 0)
    except (TypeError, ValueError):
        wait_s = 0
    wait_s = max(30, min(wait_s, 600)) if action == "wait" else 0
    if action == "switch_keyword" and not kws:
        action = "retry"

    return {
        "ok": True,
        "action": action,
        "diagnosis": str(parsed.get("diagnosis") or "")[:120],
        "reason": str(parsed.get("reason") or "")[:160],
        "keywords": kws,
        "wait_seconds": wait_s,
    }


SEARCH_SYSTEM = (
    "你是社交平台的搜索策略助手。用户给出一个「想找什么样的人/吧」的方向描述，"
    "你要输出 2-3 个适合在该平台搜索框里直接输入的关键词或短句，尽量具体、可被检索到。"
    "只输出 JSON，格式：{\"keywords\": [\"...\", \"...\"], \"note\": \"一句筛选思路，20字内\"}，不要任何解释。"
)


def build_search_plan(
    brief: str,
    platform_name: str = "",
    preset: list[str] | None = None,
) -> dict[str, Any]:
    """把「方向描述」变成可执行的搜索关键词。

    - 传了 preset（用户手填关键词）就直接用；
    - 配了 AI 就让模型生成；
    - 没配 AI 就退化成「整句当关键词」，功能不至于不可用。
    """
    if preset:
        return {"ok": True, "keywords": [k.strip() for k in preset if k.strip()][:3], "note": "手动指定关键词"}

    brief = (brief or "").strip()
    if not brief:
        return {"ok": False, "keywords": [], "note": "请先写一句想找什么样的人"}

    cfg = load_ai()
    base = (cfg.get("base_url") or "").rstrip("/")
    key = cfg.get("api_key") or ""
    model = (cfg.get("model") or "").strip()
    if not base or not model or (not key and "127.0.0.1" not in base and "localhost" not in base):
        return {
            "ok": True,
            "keywords": [brief[:40]],
            "note": "未配置 AI，直接把描述当关键词（可在设置里接入模型以获得更准的关键词）",
        }

    thinking = cfg.get("thinking", "medium")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SEARCH_SYSTEM},
            {"role": "user", "content": f"平台：{platform_name or '通用'}\n方向描述：{brief}"},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    if thinking in ("low", "medium", "high"):
        payload["reasoning_effort"] = thinking
        payload["max_tokens"] = 300

    res = _request(f"{base}/chat/completions", payload, key, int(cfg.get("timeout", 60)))
    if not res.get("ok"):
        return {"ok": True, "keywords": [brief[:40]], "note": f"AI 不可用（{res.get('detail')}），已退化为直接用描述搜索"}

    data = res.get("data") or {}
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return {"ok": True, "keywords": [brief[:40]], "note": "AI 返回结构异常，已退化为直接用描述搜索"}

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": True, "keywords": [brief[:40]], "note": "AI 输出无法解析，已退化为直接用描述搜索"}

    kws = [str(k).strip() for k in (parsed.get("keywords") or []) if str(k).strip()]
    if not kws:
        kws = [brief[:40]]
    return {"ok": True, "keywords": kws[:3], "note": str(parsed.get("note") or "")[:60]}


def draft_message(brief: str, platform: str = "", action: str = "send_message", extra: str = "") -> dict[str, Any]:
    cfg = load_ai()
    base = (cfg.get("base_url") or "").rstrip("/")
    key = cfg.get("api_key") or ""
    model = (cfg.get("model") or "").strip()
    if not base or not model:
        return {"ok": False, "detail": "还没有配置 AI 模型，请点右上角「AI 设置」填地址与模型"}
    if not key and "127.0.0.1" not in base and "localhost" not in base:
        return {"ok": False, "detail": "还没有填写 API Key"}

    brief = (brief or "").strip()
    if not brief:
        return {"ok": False, "detail": "请先写一句你想表达的意思"}

    thinking = cfg.get("thinking", "medium")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"平台：{platform or '通用'}\n动作：{action}\n用户意图：{brief}\n补充要求：{extra or '无'}"},
        ],
        "temperature": float(cfg.get("temperature", 0.7)),
        "stream": False,
    }
    if thinking in ("low", "medium", "high"):
        payload["reasoning_effort"] = thinking
        payload["max_tokens"] = {"low": 400, "medium": 800, "high": 1600}[thinking]

    res = _request(f"{base}/chat/completions", payload, key, int(cfg.get("timeout", 60)))
    if not res.get("ok"):
        return {"ok": False, "detail": res.get("detail", "调用失败"), "body": res.get("body", "")}

    data = res.get("data") or {}
    try:
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "detail": "返回结构不认识，可能不是 OpenAI 兼容接口", "body": json.dumps(data)[:400]}

    text = text.strip().strip('"').strip("“”").strip()
    usage = data.get("usage") or {}
    return {
        "ok": True,
        "text": text,
        "model": data.get("model", model),
        "thinking": thinking,
        "usage": {
            "prompt": usage.get("prompt_tokens"),
            "completion": usage.get("completion_tokens"),
        },
    }
