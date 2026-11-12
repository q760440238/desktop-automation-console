"""全局配置：路径、默认值、读写。

配置文件位于 config/settings.json，可被界面直接修改（热生效）。
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
WEB_DIR = ROOT / "web"
LOG_DIR = DATA_DIR / "logs"
SHOT_DIR = DATA_DIR / "screenshots"
PROFILE_DIR = DATA_DIR / "browser_profiles"
DB_PATH = DATA_DIR / "agent.db"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

_lock = threading.RLock()

DEFAULT_SETTINGS: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 18765},
    # dry_run: 只出计划，绝不触碰任何应用
    # confirm: 逐条/整批人工确认后才执行（默认，最安全）
    # auto:    审批后自动连跑，但依旧受频率与条数上限约束
    "mode": "confirm",
    # 演练模式：不驱动真实应用，只返回模拟结果，用于熟悉流程
    "simulation": True,
    "guardrails": {
        "default": {"per_hour": 15, "per_day": 50, "delay_min": 5.0, "delay_max": 12.0},
        "per_platform": {
            "wechat": {"per_hour": 10, "per_day": 30, "delay_min": 6.0, "delay_max": 15.0},
            "wecom": {"per_hour": 10, "per_day": 30, "delay_min": 6.0, "delay_max": 15.0},
            "qq": {"per_hour": 12, "per_day": 40, "delay_min": 6.0, "delay_max": 15.0},
            "douyin": {"per_hour": 20, "per_day": 60, "delay_min": 4.0, "delay_max": 10.0},
            "kuaishou": {"per_hour": 20, "per_day": 60, "delay_min": 4.0, "delay_max": 10.0},
            "weibo": {"per_hour": 20, "per_day": 60, "delay_min": 4.0, "delay_max": 10.0},
            "bilibili": {"per_hour": 20, "per_day": 60, "delay_min": 4.0, "delay_max": 10.0},
            "xiaohongshu": {"per_hour": 15, "per_day": 45, "delay_min": 5.0, "delay_max": 12.0},
            "zhihu": {"per_hour": 15, "per_day": 45, "delay_min": 5.0, "delay_max": 12.0},
            "tieba": {"per_hour": 15, "per_day": 45, "delay_min": 5.0, "delay_max": 12.0},
        },
    },
    # 同一目标在该小时数内不重复触达，防止骚扰与重复发送
    "dedupe_hours": 168,
    "web": {
        "headless": False,
        # 使用本机已安装的 Chrome / Edge，避免额外下载浏览器内核
        "channel": "chrome",
        "slow_mo_ms": 120,
        "action_timeout_ms": 15000,
    },
    "desktop": {
        # 微信 4.x 安装路径（Weixin.exe），留空则自动探测
        "wechat_exe": "",
        "qq_exe": "",
        "wecom_exe": "",
        "allow_launch": False,
    },
    "safety": {
        "require_approval": True,
        "block_self": True,
        "max_batch": 50,
        # 命中这些词的目标/文案直接拒绝
        "blocked_keywords": ["代开发票", "博彩", "刷单", "裸聊"],
    },
}


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_dirs() -> None:
    for d in (DATA_DIR, CONFIG_DIR, LOG_DIR, SHOT_DIR, PROFILE_DIR, WEB_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    with _lock:
        if not SETTINGS_PATH.exists():
            save_settings(DEFAULT_SETTINGS)
            return copy.deepcopy(DEFAULT_SETTINGS)
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        merged = _deep_merge(DEFAULT_SETTINGS, raw)
        return merged


def save_settings(patch: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_dirs()
    with _lock:
        current = DEFAULT_SETTINGS
        if SETTINGS_PATH.exists():
            try:
                current = _deep_merge(DEFAULT_SETTINGS, json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                current = copy.deepcopy(DEFAULT_SETTINGS)
        merged = _deep_merge(current, patch or {})
        SETTINGS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return merged


def limits_for(platform: str, settings: dict[str, Any] | None = None) -> dict[str, float]:
    """返回某平台的频率限制（小时/天/间隔）。"""
    cfg = settings or load_settings()
    g = cfg.get("guardrails", {})
    base = dict(g.get("default", DEFAULT_SETTINGS["guardrails"]["default"]))
    base.update(g.get("per_platform", {}).get(platform, {}))
    return base


def detect_wechat_exe() -> str:
    cands = [
        r"C:\Program Files\Tencent\Weixin\Weixin.exe",
        r"C:\Program Files (x86)\Tencent\Weixin\Weixin.exe",
        r"C:\Program Files\Tencent\WeChat\WeChat.exe",
        r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    ]
    cfg = load_settings().get("desktop", {})
    if cfg.get("wechat_exe"):
        cands.insert(0, cfg["wechat_exe"])
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""


def detect_qq_exe() -> str:
    cands = [
        r"C:\Program Files\Tencent\QQNT\QQ.exe",
        r"C:\Program Files (x86)\Tencent\QQNT\QQ.exe",
        r"C:\Program Files\Tencent\QQ\Bin\QQ.exe",
    ]
    cfg = load_settings().get("desktop", {})
    if cfg.get("qq_exe"):
        cands.insert(0, cfg["qq_exe"])
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""


def detect_wecom_exe() -> str:
    cands = [
        r"C:\Program Files (x86)\WXWork\WXWork.exe",
        r"C:\Program Files\WXWork\WXWork.exe",
        r"D:\Program Files (x86)\WXWork\WXWork.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\WXWork\WXWork.exe"),
        os.path.expandvars(r"%APPDATA%\Tencent\WXWork\WXWork.exe"),
    ]
    cfg = load_settings().get("desktop", {})
    if cfg.get("wecom_exe"):
        cands.insert(0, cfg["wecom_exe"])
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ""
