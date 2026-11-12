"""网页平台适配器公共基类。

四个网页平台（抖音 / 微博 / B站 / 小红书）共用同一套浏览器生命周期与动作流程：

- 每个平台一个持久化上下文，登录态存放在 data/browser_profiles/<platform>，不下载浏览器内核；
- 优先使用本机 Chrome（channel="chrome"），启动失败自动降级本机 Edge；
- 浏览器被人工关闭、或上下文变成僵尸时自动重建，避免一次异常拖垮整批任务；
- execute() 内所有异常都转成中文失败结果（附截图路径），绝不向调用方抛出。

子类只需声明平台名、首页地址与候选选择器，关注 / 私信流程全部在基类复用。
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse, urlunparse
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..settings import PROFILE_DIR, ROOT, load_settings
from .base import BaseAdapter, Ctx, ExecResult, shot_path

if TYPE_CHECKING:  # 仅类型提示：运行时才导入 playwright，未安装也不影响界面启动
    from playwright.async_api import BrowserContext, Page

# playwright 缺失时的中文提示
_PW_HINT = "未安装 playwright：请在项目 Python 环境执行 pip install playwright（无需下载浏览器，脚本会使用本机 Chrome）"

# web 配置的兜底默认值（config/settings.json 里的 web 节可覆盖）
_DEFAULT_WEB: dict[str, Any] = {
    "headless": False,
    "channel": "chrome",
    "slow_mo_ms": 120,
    "action_timeout_ms": 15000,
}

# 上下文 / 页面被关闭时的异常特征，用来决定「是重建浏览器还是只是页面在跳转」
_CLOSED_HINTS = (
    "target closed",
    "target page",
    "browser has been closed",
    "connection closed",
    "has been closed",
    "browser closed",
)

# 候选选择器：dict 形式（role / text / css / xpath / placeholder），也兼容直接给字符串（按文本匹配）
Selector = dict[str, Any] | str

# 在搜索结果页里按链接特征收集「人」的卡片（只读，不做任何点击）
_DISCOVER_JS = r"""(args) => {
  const patterns = args.patterns || [];
  const limit = args.limit || 20;
  const out = [];
  const seen = new Set();
  const skip = /^(关注|已关注|\+ ?关注|私信|发消息|查看更多|展开|更多)$/;
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href || '';
    if (!href || href.startsWith('javascript')) continue;
    if (!patterns.some(p => href.indexOf(p) !== -1)) continue;
    if (seen.has(href)) continue;
    const raw = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
    if (!raw || raw.length > 40) continue;
    if (skip.test(raw)) continue;
    seen.add(href);
    out.push({ name: raw, url: href });
    if (out.length >= limit) break;
  }
  return out;
}"""


def _short(exc: object, limit: int = 200) -> str:
    """把异常压成一行，便于写进界面提示与审计日志。"""
    text = str(exc).strip()
    if not text:
        return type(exc).__name__
    return text.splitlines()[0][:limit]


def _is_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def _as_int(value: Any, default: int, *, low: int = 0) -> int:
    try:
        return max(low, int(value))
    except (TypeError, ValueError):
        return default


# 人机验证的特征文案：命中就说明平台在拦你，继续操作只会加重风控
CAPTCHA_HINTS = (
    "请完成下列验证",
    "拖动滑块",
    "滑动验证",
    "按住左边滑块",
    "人机验证",
    "安全验证",
    "captcha",
)


def _looks_closed(exc: object) -> bool:
    """判断异常是否属于「浏览器/标签页已被关闭」。"""
    text = str(exc).lower()
    return any(hint in text for hint in _CLOSED_HINTS)


def _clean_candidate_name(raw: str) -> str:
    """搜索结果里的链接文本常带元信息，如「量子菠萝_ · 2天前」，只留昵称。"""
    name = (raw or "").strip()
    for sep in (" · ", " | ", "·", "｜"):
        if sep in name:
            head = name.split(sep, 1)[0].strip()
            if head:
                name = head
                break
    return name.strip(" .·-—")


# 搜索结果里会把当前登录用户自己的主页塞进来，不是可操作对象
_JUNK_PROFILE_RE = re.compile(r"/(user|profile|people)/(self|me)/?$", re.I)


def _canonical_url(url: str) -> str:
    """把 URL 归一成「协议 + 域名 + 路径」，丢掉 query / fragment。

    抖音、微博的搜索结果会带一长串跟踪参数（`?enter_from=search...`），
    不剥掉会出现三个问题：超过目标长度上限被安全策略拦、同一个人被当成多个目标、去重失效。
    """
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    if not path:
        return ""
    if _JUNK_PROFILE_RE.search(path):
        return ""
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


class WebAdapter(BaseAdapter):
    """网页平台适配器基类（Playwright 异步 API + 本机浏览器）。"""

    kind = "web"

    # ---- 子类必须声明 ----
    display_name: str = ""  # 中文平台名，用于提示语
    home_url: str = ""  # 平台首页

    # ---- 登录判定 ----
    login_candidates: list[Selector] = [
        {"role": "button", "name": "登录", "exact": True},
        {"role": "link", "name": "登录", "exact": True},
    ]

    # ---- 关注 ----
    follow_candidates: list[Selector] = []
    followed_texts: tuple[str, ...] = ("已关注", "互相关注", "取消关注")

    # ---- 私信 ----
    message_candidates: list[Selector] = []
    # 有些平台（如知乎）把「私信」收在「更多」菜单里：点不到私信时先展开更多再试一次
    more_candidates: list[Selector] = []
    # 输入框优先 textarea / contenteditable：站内搜索框多为 input，这样能避免把文案打进搜索框
    input_candidates: list[Selector] = [
        {"css": '[role="dialog"] textarea'},
        {"css": '[role="dialog"] [contenteditable="true"]'},
        {"css": "textarea"},
        {"css": '[class*="chat"] textarea'},
        {"css": "[contenteditable=true]"},
        {"role": "textbox"},
    ]
    send_candidates: list[Selector] = [
        {"role": "button", "name": "发送", "exact": True},
        {"css": 'button:has-text("发送")'},
    ]
    # 明确的不可发送提示（命中即判定失败，且不重试）
    blocked_hints: tuple[str, ...] = (
        "需要互相关注",
        "互相关注后",
        "对方已关闭私信",
        "暂不支持私信",
        "暂不能发送",
        "无法发送私信",
        "消息发送失败",
        "由于对方的隐私设置",
    )

    # ---- 搜索结果里「第一个用户」的候选 ----
    user_card_candidates: list[Selector] = []

    # ---- 按方向找人：在搜索结果页里认哪些链接是「人」 ----
    # 例如抖音是 /user/，知乎是 /people/。留空表示该平台不支持发现。
    discover_patterns: tuple[str, ...] = ()

    # ---- 昵称清洗 ----
    nick_separators: tuple[str, ...] = (" - ", " | ", " — ", "的微博", "的个人空间")
    nick_suffixes: tuple[str, ...] = ("的微博", "_微博")
    site_titles: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.profile_dir = PROFILE_DIR / (self.platform or "web")  # 每个平台独立的浏览器用户目录
        self._pw: Any = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        self._launch_key: tuple[str, bool] | None = None  # (实际通道, 是否有头)
        self._loop: Any = None
        self._settings: dict[str, Any] | None = None  # 最近一次 execute 传入的配置快照
        # 同一平台的浏览器操作必须串行：手动发现和无限模式同时跑会互相打断页面
        self._op_lock = asyncio.Lock()

    # ------------------------------------------------------------------ 配置
    def _web_options(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """读取 web 配置：Ctx.settings 优先，其次 config/settings.json，最后内置默认值。"""
        src = settings if isinstance(settings, dict) and settings else self._settings
        cfg = src if isinstance(src, dict) and src else load_settings()
        web = dict(_DEFAULT_WEB)
        extra = cfg.get("web") if isinstance(cfg, dict) else None
        if isinstance(extra, dict):
            web.update(extra)
        web["headless"] = bool(web.get("headless", False))
        web["channel"] = str(web.get("channel") or "chrome")
        web["slow_mo_ms"] = _as_int(web.get("slow_mo_ms"), 120, low=0)
        web["action_timeout_ms"] = _as_int(web.get("action_timeout_ms"), 15000, low=3000)
        return web

    # ------------------------------------------------------------------ 状态
    async def health(self) -> dict[str, Any]:
        """只读检查登录态目录，绝不启动浏览器。"""
        folder = self.profile_dir
        try:
            ready = folder.is_dir() and any(folder.iterdir())
        except OSError:
            ready = False
        if ready:
            return {"ready": True, "detail": "已保存浏览器配置（真正登录态在开始执行时再校验）"}
        return {"ready": False, "detail": "未登录：点击「打开浏览器登录」后手动登录一次"}

    # ------------------------------------------------------------------ 浏览器
    async def ensure_page(self, settings: dict[str, Any] | None = None) -> Page:
        """返回可操作的页面：能复用就复用，僵尸上下文或被人工关掉就重建。"""
        web = self._web_options(settings)
        key = (web["channel"], web["headless"])

        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            # 事件循环换了（例如服务重启），旧对象已不可用，直接丢弃后重建
            self._pw = self._ctx = self._page = None
            self._launch_key = None
        self._loop = loop

        page = await self._reuse_page()
        if page is not None and self._launch_key == key:
            return page
        if self._ctx is not None:
            # 已有上下文但不满足有头/无头或通道要求（例如人工登录需要弹窗），关闭后重建
            await self._shutdown()
        return await self._launch(web)

    async def _reuse_page(self) -> Page | None:
        if self._ctx is None or self._page is None:
            return None
        try:
            pages = list(self._ctx.pages)  # 浏览器被外部关掉时，这里就会抛异常
        except Exception:
            await self._shutdown()
            return None
        if not pages:
            # 所有标签页都被关了，但浏览器还活着：补开一个
            try:
                self._page = await self._ctx.new_page()
                return self._page
            except Exception:
                await self._shutdown()
                return None
        try:
            page = self._page if (not self._page.is_closed() and self._page in pages) else pages[0]
        except Exception:
            await self._shutdown()
            return None
        try:
            await page.evaluate("() => 1")  # 探活：标签页已关闭会立刻抛异常
        except Exception as exc:
            if _looks_closed(exc):
                await self._shutdown()
                return None
            # 只是页面正在跳转（执行上下文被销毁），沿用原页面即可
            self._page = page
            return page
        self._page = page
        return page

    async def _launch(self, web: dict[str, Any]) -> Page:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(_PW_HINT) from exc

        headless = bool(web["headless"])
        if self._pw is None:
            try:
                self._pw = await async_playwright().start()
            except Exception as exc:
                self._pw = None
                raise RuntimeError(f"启动 Playwright 失败：{_short(exc)}") from exc

        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"无法创建浏览器配置目录 {self.profile_dir}：{_short(exc)}") from exc

        channels: list[str] = [web["channel"]]
        if web["channel"] == "chrome":
            channels.append("msedge")  # Chrome 不可用时降级到本机 Edge

        ctx: BrowserContext | None = None
        used = ""
        errors: list[str] = []
        for channel in channels:
            try:
                ctx = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    channel=channel,
                    headless=headless,
                    slow_mo=web["slow_mo_ms"],
                    viewport={"width": 1440, "height": 900},
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                )
                used = channel
                break
            except Exception as exc:
                errors.append(f"{channel}：{_short(exc)}")

        if ctx is None:
            raise RuntimeError(
                f"启动浏览器失败（已尝试 {' / '.join(channels)}）：{'；'.join(errors)}。"
                "请确认本机已安装 Chrome 或 Edge，并关闭可能残留的旧浏览器窗口后重试"
            )

        self._ctx = ctx
        self._launch_key = (used, headless)
        try:
            ctx.set_default_timeout(web["action_timeout_ms"])
            self._page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        except Exception as exc:
            await self._shutdown()
            raise RuntimeError(f"打开浏览器页面失败：{_short(exc)}") from exc
        return self._page

    async def _shutdown(self) -> None:
        """关闭当前上下文与 playwright 句柄；任何异常都忽略，保证可以反复调用。"""
        ctx, pw = self._ctx, self._pw
        self._ctx = self._page = self._pw = None
        self._launch_key = None
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass

    async def close(self) -> None:
        await self._shutdown()

    # ------------------------------------------------------------------ 工具
    async def goto(self, url: str, wait: str = "domcontentloaded") -> Page:
        """打开页面；导航超时视为「页面已可操作」，其它错误重试一次再报中文错误。"""
        page = await self.ensure_page()
        timeout = self._web_options()["action_timeout_ms"]
        error = ""
        for wait_until in (wait, "commit"):
            try:
                await page.goto(url, wait_until=wait_until, timeout=timeout)
                error = ""
                break
            except Exception as exc:
                if "timeout" in str(exc).lower():
                    error = ""  # 超时兜底：内容通常已加载，继续往下走
                    break
                error = _short(exc)
                if _looks_closed(exc):
                    await self._shutdown()
                    break
        try:
            await page.wait_for_timeout(300)  # 给前端渲染留一点时间
        except Exception:
            pass
        if error:
            raise RuntimeError(f"打开页面失败：{url}（{error}）")
        return page

    async def shot(self, tag: str) -> str:
        """截图并返回相对项目根的可读路径；失败返回空串，绝不抛异常。"""
        page = self._page
        if page is None:
            return ""
        path = shot_path(self.platform, tag)
        try:
            await page.screenshot(path=str(path), full_page=False)
        except Exception:
            return ""
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except (ValueError, OSError):
            return str(path)

    async def _shot_safe(self, tag: str) -> str:
        try:
            return await self.shot(tag)
        except Exception:
            return ""

    def _locator(self, page: Page, cand: Selector) -> Any:
        """把候选选择器翻译成 locator；无法翻译时返回 None。"""
        try:
            if isinstance(cand, str):
                return page.get_by_text(cand)
            if not isinstance(cand, dict):
                return None
            if "role" in cand:
                role = str(cand["role"])
                kwargs = {k: v for k, v in cand.items() if k != "role"}
                return page.get_by_role(role, **kwargs)
            if "css" in cand:
                return page.locator(str(cand["css"]))
            if "text" in cand:
                return page.get_by_text(str(cand["text"]), exact=bool(cand.get("exact", False)))
            if "xpath" in cand:
                return page.locator(f"xpath={cand['xpath']}")
            if "placeholder" in cand:
                return page.get_by_placeholder(str(cand["placeholder"]))
        except Exception:
            return None
        return None

    async def find(self, page: Page | None, candidates: Sequence[Selector], timeout_ms: int = 6000) -> Any:
        """依次尝试候选选择器，命中且可见就返回 locator，全部失败返回 None。"""
        if page is None:
            return None
        cands = list(candidates or [])
        if not cands:
            return None
        per = max(500, int(timeout_ms) // len(cands))
        for cand in cands:
            loc = self._locator(page, cand)
            if loc is None:
                continue
            try:
                first = loc.first
                await first.wait_for(state="visible", timeout=per)
                if await first.is_visible():
                    return first
            except Exception:
                continue
        return None

    async def click_first(self, page: Page | None, candidates: Sequence[Selector], timeout_ms: int = 6000) -> bool:
        """点击第一个命中的候选元素；被遮罩挡住时再强行点一次。"""
        loc = await self.find(page, candidates, timeout_ms)
        if loc is None:
            return False
        try:
            await loc.click(timeout=timeout_ms)
            return True
        except Exception:
            pass
        try:
            await loc.click(timeout=2500, force=True)
            return True
        except Exception:
            return False

    async def _type_into(
        self, page: Page | None, candidates: Sequence[Selector], text: str, timeout_ms: int = 6000
    ) -> Any:
        """把文案填进第一个可用输入框，成功返回 locator，否则 None。"""
        loc = await self.find(page, candidates, timeout_ms)
        if loc is None or page is None:
            return None
        try:
            await loc.click(timeout=timeout_ms)
        except Exception:
            pass
        try:
            await loc.fill("")
            await loc.fill(text)
            return loc
        except Exception:
            pass
        try:  # contenteditable 等富文本编辑器常不支持 fill
            await loc.press_sequentially(text, delay=30)
            return loc
        except Exception:
            pass
        try:
            await loc.type(text, delay=30)
            return loc
        except Exception:
            return None

    async def type_text(self, page: Page | None, candidates: Sequence[Selector], text: str, timeout_ms: int = 6000) -> bool:
        return await self._type_into(page, candidates, text, timeout_ms) is not None

    async def _verify_typed(self, page: Page | None, message: str) -> bool:
        """确认文案确实落进了输入框，避免误把内容打进站内搜索框。"""
        if page is None:
            return False
        head = (message or "").strip()[:12]
        if not head:
            return True
        script = r"""(head) => {
            const nodes = document.querySelectorAll('textarea, [contenteditable="true"], input[type="text"], input:not([type])');
            for (const el of nodes) {
                const v = (el.value !== undefined ? el.value : el.innerText) || '';
                if (v.indexOf(head) !== -1) return true;
            }
            return false;
        }"""
        try:
            return bool(await page.evaluate(script, head))
        except Exception:
            return False

    async def _visible_texts(self, page: Page, selector: str, limit: int = 30) -> list[str]:
        """采集可见元素的文本（去重、限制条数），用于 probe 校准。"""
        script = r"""(sel) => {
            const out = [];
            const seen = new Set();
            for (const el of document.querySelectorAll(sel)) {
                const style = window.getComputedStyle(el);
                if (!style || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
                if (!el.getClientRects().length) continue;
                const raw = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                const t = raw.replace(/\s+/g, ' ');
                if (!t || t.length > 40 || seen.has(t)) continue;
                seen.add(t);
                out.push(t);
                if (out.length >= 30) break;
            }
            return out;
        }"""
        try:
            data = await page.evaluate(script, selector)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(x) for x in data][:limit]

    async def _input_summary(self, page: Page) -> list[str]:
        """采集输入框概要（标签 + 占位符 + id），用于 probe 校准。"""
        script = r"""() => {
            const out = [];
            const nodes = document.querySelectorAll('input, textarea, [contenteditable="true"], [role="textbox"]');
            for (const el of nodes) {
                if (!el.getClientRects().length) continue;
                const tag = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                const ph = el.getAttribute('placeholder') || '';
                const label = el.getAttribute('aria-label') || '';
                const id = el.id ? '#' + el.id : '';
                const desc = [tag + (type ? '[' + type + ']' : ''), ph, label, id].filter(Boolean).join(' ');
                if (desc) out.push(desc.slice(0, 60));
                if (out.length >= 15) break;
            }
            return out;
        }"""
        try:
            data = await page.evaluate(script)
        except Exception:
            return []
        return [str(x) for x in data] if isinstance(data, list) else []

    # ------------------------------------------------------------------ 登录与定位
    async def _logged_out(self, page: Page) -> bool:
        """未登录判定：跳到登录页 / 护照页，或页面上出现「登录」按钮。"""
        url = (page.url or "").lower()
        if any(key in url for key in ("login", "passport", "signin", "sign_in")):
            return True
        return await self.find(page, self.login_candidates, timeout_ms=1800) is not None

    async def _detect_captcha(self, page: Page) -> str:
        """页面上是否出现了人机验证，命中返回命中的特征词。

        抖音/微博的滑块验证挂在 iframe 里，只看主文档抓不到，必须把所有 frame 都扫一遍。
        """
        frames: list[Any] = [page]
        try:
            frames += [f for f in page.frames if f != page.main_frame]
        except Exception:
            pass
        for frame in frames:
            try:
                body = await frame.locator("body").inner_text(timeout=1200)
            except Exception:
                continue
            low = (body or "").lower()
            for hint in CAPTCHA_HINTS:
                if hint.lower() in low:
                    return hint
        url = (page.url or "").lower()
        if "captcha" in url or "verify" in url:
            return "验证页"
        return ""

    async def _login_gate(self) -> ExecResult | None:
        """先回首页做一次登录判定；未登录就立即返回，不继续点任何按钮。"""
        page = await self.ensure_page(self._settings)
        await self.goto(self.home_url)
        if await self._logged_out(page):
            shot = await self._shot_safe("not_logged_in")
            return ExecResult(
                ok=False,
                detail=f"未登录，请先在界面里打开浏览器登录 {self.display_name}",
                screenshot=shot or None,
            )
        captcha = await self._detect_captcha(page)
        if captcha:
            shot = await self._shot_safe("captcha")
            return ExecResult(
                ok=False,
                detail=f"{self.display_name} 弹出了人机验证（{captcha}），需要你手动完成后再试",
                screenshot=shot or None,
            )
        return None

    def build_profile_url(self, target: str) -> str:
        """按账号 ID 直接拼主页链接；拼不出来返回空串（由子类覆盖）。"""
        return ""

    def build_search_url(self, target: str) -> str:
        """按昵称走站内搜索；不支持返回空串（由子类覆盖）。"""
        return ""

    def build_discover_url(self, keyword: str) -> str:
        """按关键词找人时打开的页面；默认与普通搜索一致。"""
        return self.build_search_url(keyword)

    async def discover(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        async with self._op_lock:
            return await self._discover_impl(keyword, limit)

    async def _discover_impl(self, keyword: str, limit: int = 20) -> dict[str, Any]:
        """按关键词搜索并返回候选对象（只读，不发任何消息）。

        返回 {"ok", "candidates":[{name,url}], "detail"}。
        这是「给名单」而不是「替人决定」，调用方必须让用户勾选后才进入执行链路。
        """
        if not self.discover_patterns:
            return {"ok": False, "detail": f"{self.display_name}暂不支持按方向找人", "candidates": []}

        limit = max(1, min(int(limit), 50))
        try:
            page = await self.ensure_page(self._settings)
            url = self.build_discover_url(keyword)
            if not url:
                return {"ok": False, "detail": "该平台无法根据关键词搜索", "candidates": []}
            page = await self.goto(url)
            if await self._logged_out(page):
                return {"ok": False, "detail": f"未登录，请先打开浏览器登录 {self.display_name}", "candidates": []}

            captcha = await self._detect_captcha(page)
            if captcha:
                shot = await self._shot_safe(f"discover_captcha_{keyword}")
                return {
                    "ok": False,
                    "captcha": True,
                    "candidates": [],
                    "detail": f"{self.display_name} 弹出了人机验证（{captcha}），需要你手动完成后重试"
                    + (f"，截图：{shot}" if shot else ""),
                }

            await page.wait_for_timeout(1500)
            # 滚一下触发懒加载，再等一会儿
            try:
                await page.mouse.wheel(0, 900)
            except Exception:
                pass
            await page.wait_for_timeout(1300)

            raw = await page.evaluate(
                _DISCOVER_JS,
                {"patterns": list(self.discover_patterns), "limit": limit},
            )
            items = raw if isinstance(raw, list) else []
            seen: set[str] = set()
            candidates: list[dict[str, Any]] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                href = _canonical_url(str(it.get("url") or ""))
                name = _clean_candidate_name(str(it.get("name") or ""))
                if not href or not name or href in seen:
                    continue
                seen.add(href)
                candidates.append({"name": name, "url": href})
                if len(candidates) >= limit:
                    break
            try:
                page_title = (await page.title())[:80]
            except Exception:
                page_title = ""
            page_url = page.url or ""

            if not candidates:
                # 抓不到候选时留一张截图，方便判断是「未登录」「被风控」还是「页面改版」
                shot = await self._shot_safe(f"discover_empty_{keyword}")
                msg = f"「{keyword}」没有找到结果"
                if shot:
                    msg += f"，截图：{shot}"
                return {
                    "ok": True,
                    "keyword": keyword,
                    "candidates": [],
                    "detail": msg,
                    "url": page_url,
                    "title": page_title,
                }
            return {
                "ok": True,
                "keyword": keyword,
                "candidates": candidates,
                "detail": f"「{keyword}」找到 {len(candidates)} 个候选",
                "url": page_url,
                "title": page_title,
            }
        except Exception as exc:
            return {"ok": False, "detail": f"搜索失败：{_short(exc)}", "candidates": []}

    async def _open_target(self, page: Page, target: str) -> Page:
        """定位目标页：链接直接打开 → 能按 ID 拼主页就直达 → 否则站内搜索并点第一个用户。"""
        if _is_url(target):
            return await self.goto(target)

        profile = self.build_profile_url(target)
        if profile:
            return await self.goto(profile)
        search = self.build_search_url(target)
        if search:
            page = await self.goto(search)
            hit = await self._click_user_card(page)
            if hit is not None:
                page = hit
            await page.wait_for_timeout(800)  # 等个人主页骨架渲染完
            return page
        raise RuntimeError("目标格式无法识别，请填写该平台的主页链接或账号 ID")

    async def _page_count(self) -> int:
        """当前浏览器里打开的标签页数量；上下文已失效时按 0 处理。"""
        try:
            return len(self._ctx.pages) if self._ctx is not None else 0
        except Exception:
            return 0

    async def _absorb_page(self, page: Page, before: int) -> Page:
        """点击后若弹出了新标签页（微博/B站私信常见），就切到新页继续操作。"""
        try:
            pages = list(self._ctx.pages) if self._ctx is not None else []
        except Exception:
            return page
        if len(pages) <= before or not pages:
            return page
        new_page = pages[-1]
        try:
            await new_page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        self._page = new_page
        return new_page

    async def _click_user_card(self, page: Page) -> Page | None:
        """点开搜索结果里的第一个用户。"""
        if not self.user_card_candidates:
            return None
        before = await self._page_count()
        loc = await self.find(page, self.user_card_candidates, timeout_ms=4000)
        if loc is None:
            return None
        try:
            await loc.click(timeout=6000)
        except Exception:
            try:
                await loc.click(timeout=3000, force=True)
            except Exception:
                return None
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=6000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        return await self._absorb_page(page, before)

    # ------------------------------------------------------------------ 文案
    def _clean_nick(self, raw: str) -> str:
        """从页面标题里剥出昵称：去掉「- 抖音」「的微博」这类站点后缀。"""
        nick = (raw or "").strip()
        if not nick:
            return ""
        for sep in self.nick_separators:
            if sep and sep in nick:
                nick = nick.split(sep, 1)[0].strip()
        for suffix in self.nick_suffixes:
            if suffix and nick.endswith(suffix):
                nick = nick[: -len(suffix)].strip()
        if not nick or nick in self.site_titles or len(nick) > 40:
            return ""
        return nick

    async def _read_nick(self, page: Page) -> str:
        """读昵称：先 h1 / 昵称节点，再退回页面标题。"""
        for cand in ({"css": "h1"}, {"css": '[class*="nickname"]'}, {"css": '[class*="user-name"]'}):
            loc = await self.find(page, [cand], timeout_ms=1200)
            if loc is None:
                continue
            try:
                nick = self._clean_nick(await loc.inner_text())
            except Exception:
                continue
            if nick:
                return nick
        try:
            title = await page.title()
        except Exception:
            title = ""
        return self._clean_nick(title)

    async def _render_text(self, page: Page, text: str, target: str) -> str:
        """把 {nick} 替换成页面昵称；拿不到就用 target 兜底。"""
        if "{nick}" not in (text or ""):
            return text or ""
        nick = await self._read_nick(page)
        return (text or "").replace("{nick}", nick or target)

    async def _blocked_reason(self, page: Page) -> str:
        """检测「对方设置不可发送」这类明确拦截提示，命中就返回原因片段。"""
        try:
            body = await page.locator("body").inner_text(timeout=3000)
        except Exception:
            return ""
        text = (body or "").replace("\n", " ")
        for hint in self.blocked_hints:
            idx = text.find(hint)
            if idx >= 0:
                return text[max(0, idx - 10) : idx + 26].strip()
        for kw in ("对方设置", "对方的隐私设置"):
            idx = text.find(kw)
            if idx < 0:
                continue
            window = text[idx : idx + 40]
            if any(word in window for word in ("不可", "无法", "不能", "不接收", "拒收", "限制")):
                return window.strip()
        return ""

    # ------------------------------------------------------------------ 动作
    async def execute(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        async with self._op_lock:
            return await self._execute_impl(action, target, text, extra, ctx)

    async def _execute_impl(self, action: str, target: str, text: str, extra: dict[str, Any], ctx: Ctx) -> ExecResult:
        """统一入口：任何异常都转成中文失败结果，绝不外泄。"""
        self._settings = ctx.settings if ctx is not None else None
        target = (target or "").strip()
        extra = extra if isinstance(extra, dict) else {}
        try:
            if not target:
                return ExecResult(ok=False, detail="目标为空：请填写主页链接或账号 ID")
            if action == "send_message" and not (text or "").strip():
                return ExecResult(ok=False, detail="文案为空：请填写要发送的私信内容")
            if action not in self.actions:
                return ExecResult(ok=False, detail=f"{self.display_name}不支持「{action}」动作")

            gate = await self._login_gate()
            if gate is not None:
                return gate

            # 「关注后再发送」：先关注同一个人，再发消息。一次会话里完成，少一次页面往返。
            follow_note = ""
            if action == "send_message" and extra.get("auto_follow") and "follow" in self.actions:
                fres = await self._do_follow(target, extra)
                follow_note = "已关注" if fres.ok else f"未关注（{(fres.detail or '')[:40]}）"

            if action == "follow":
                return await self._do_follow(target, extra)
            res = await self._do_send_message(target, text or "", extra)
            if follow_note:
                res.detail = f"{follow_note} · {res.detail}"
            return res
        except Exception as exc:
            shot = await self._shot_safe(f"{action}_error")
            return ExecResult(
                ok=False,
                detail=f"{self.display_name}操作异常：{_short(exc)}",
                screenshot=shot or None,
                retryable=True,
            )

    async def _is_following(self, page: Page) -> bool:
        """页面上是否已经出现「已关注 / 互相关注 / 取消关注」这类文案。"""
        cands: list[Selector] = [{"role": "button", "name": t, "exact": True} for t in self.followed_texts]
        cands += [{"text": t, "exact": True} for t in self.followed_texts]
        return await self.find(page, cands, timeout_ms=1500) is not None

    async def _do_follow(self, target: str, extra: dict[str, Any]) -> ExecResult:
        """关注：打开目标主页 → 点关注 → 复查已关注态。"""
        web = self._web_options()
        page = await self.ensure_page(self._settings)
        page = await self._open_target(page, target)

        if await self._is_following(page):
            return ExecResult(ok=True, detail=f"已关注 {target}")

        clicked = await self.click_first(page, self.follow_candidates, timeout_ms=web["action_timeout_ms"])
        if not clicked and self.more_candidates:
            # 关注按钮也可能收在「更多」菜单里（知乎等）
            if await self.click_first(page, self.more_candidates, timeout_ms=4000):
                await page.wait_for_timeout(700)
                clicked = await self.click_first(page, self.follow_candidates, timeout_ms=4000)
        if not clicked:
            shot = await self._shot_safe(f"follow_fail_{target}")
            return ExecResult(
                ok=False,
                detail=f"未找到关注按钮，可能页面改版或被风控，截图：{shot or '（截图失败）'}",
                screenshot=shot or None,
                retryable=True,
            )

        await page.wait_for_timeout(1200)
        if await self._is_following(page):
            return ExecResult(ok=True, detail=f"已关注 {target}")

        shot = await self._shot_safe(f"follow_check_{target}")
        return ExecResult(
            ok=False,
            detail=f"点击关注后未出现「已关注」状态，可能被风控或需要验证，截图：{shot or '（截图失败）'}",
            screenshot=shot or None,
            retryable=True,
        )

    async def _do_send_message(self, target: str, text: str, extra: dict[str, Any]) -> ExecResult:
        """私信：打开目标主页 → 点私信 → 填文案 → 发送 → 复查拦截提示。"""
        web = self._web_options()
        page = await self.ensure_page(self._settings)
        page = await self._open_target(page, target)

        reason = await self._blocked_reason(page)
        if reason:
            shot = await self._shot_safe(f"dm_blocked_{target}")
            return ExecResult(ok=False, detail=f"无法发送私信给 {target}：{reason}", screenshot=shot or None)

        message = await self._render_text(page, text, target)

        before = await self._page_count()
        opened = await self.click_first(page, self.message_candidates, timeout_ms=web["action_timeout_ms"])
        if not opened and self.more_candidates:
            # 入口藏在「更多」菜单里：先展开，再找一次私信
            if await self.click_first(page, self.more_candidates, timeout_ms=4000):
                await page.wait_for_timeout(700)
                opened = await self.click_first(page, self.message_candidates, timeout_ms=4000)
        if not opened:
            # 部分平台私信面板默认展开，没有「私信」按钮时再看一眼输入框
            if await self.find(page, self.input_candidates, timeout_ms=2000) is None:
                shot = await self._shot_safe(f"dm_nobtn_{target}")
                return ExecResult(
                    ok=False,
                    detail=f"未找到私信入口，可能页面改版、被风控或对方关闭了私信，截图：{shot or '（截图失败）'}",
                    screenshot=shot or None,
                    retryable=True,
                )
        await page.wait_for_timeout(900)
        page = await self._absorb_page(page, before)  # 私信页可能在新标签页里打开

        reason = await self._blocked_reason(page)
        if reason:
            shot = await self._shot_safe(f"dm_blocked_{target}")
            return ExecResult(ok=False, detail=f"无法发送私信给 {target}：{reason}", screenshot=shot or None)

        box = await self._type_into(page, self.input_candidates, message, timeout_ms=8000)
        if box is None:
            shot = await self._shot_safe(f"dm_noinput_{target}")
            return ExecResult(
                ok=False,
                detail=f"未找到私信输入框，可能页面改版或被风控，截图：{shot or '（截图失败）'}",
                screenshot=shot or None,
                retryable=True,
            )
        if not await self._verify_typed(page, message):
            shot = await self._shot_safe(f"dm_verify_{target}")
            return ExecResult(
                ok=False,
                detail=f"文案没有进入私信输入框（可能被页面拦截），请人工核对，截图：{shot or '（截图失败）'}",
                screenshot=shot or None,
            )

        sent = await self.click_first(page, self.send_candidates, timeout_ms=4000)
        if not sent:
            try:
                await box.press("Enter")  # 找不到发送按钮时，在输入框上回车兜底
                sent = True
            except Exception:
                sent = False
        await page.wait_for_timeout(1200)

        reason = await self._blocked_reason(page)
        if reason:
            shot = await self._shot_safe(f"dm_refused_{target}")
            return ExecResult(ok=False, detail=f"私信未能送达 {target}：{reason}", screenshot=shot or None)

        if not sent:
            shot = await self._shot_safe(f"dm_nosend_{target}")
            return ExecResult(
                ok=False,
                detail=f"没找到发送按钮，无法确认私信是否发出，请人工核对，截图：{shot or '（截图失败）'}",
                screenshot=shot or None,
            )

        shot = await self._shot_safe(f"dm_ok_{target}")
        return ExecResult(ok=True, detail=f"已发送私信给 {target}", screenshot=shot or None)

    # ------------------------------------------------------------------ 人工入口
    async def open_login(self) -> dict[str, Any]:
        """打开有头浏览器到首页，供人工登录；登录态写入 profile 目录。"""
        try:
            # 人工登录必须看得见窗口：复制一份配置并把 web.headless 改成 False，
            # 后续 goto / probe 都复用这份快照，不会又按无头配置重建而关掉登录窗口
            cfg = load_settings()
            web = dict(cfg.get("web") or {})
            web["headless"] = False
            cfg["web"] = web
            self._settings = cfg
            await self.ensure_page(self._settings)
            await self.goto(self.home_url)
            return {
                "ok": True,
                "detail": f"已打开 {self.display_name} 首页，请在浏览器窗口内完成登录，登录后关闭窗口即可",
            }
        except Exception as exc:
            return {"ok": False, "detail": f"打开浏览器失败：{_short(exc)}"}

    async def probe(self) -> dict[str, Any]:
        """返回当前页面 url / 标题 / 可见按钮与输入框，供人工校准选择器。"""
        try:
            page = await self.ensure_page(self._settings)
            if self.home_url and page.url in ("", "about:blank"):
                await self.goto(self.home_url)
            try:
                title = await page.title()
            except Exception:
                title = ""
            buttons = await self._visible_texts(
                page, 'button, [role="button"], a, input[type="button"], input[type="submit"]', 30
            )
            inputs = await self._input_summary(page)
            return {"url": page.url, "title": title, "buttons": buttons, "inputs": inputs}
        except Exception as exc:
            return {"error": f"探测失败：{_short(exc)}"}
