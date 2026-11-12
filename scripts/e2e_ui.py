"""界面端到端测试：真实点一遍「选平台 → 选动作 → 填目标 → 生成计划 → 批准」，并截图。

用法：python scripts/e2e_ui.py [url]
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "screenshots" / "ui_plan.png"

TARGETS = [
    "https://www.douyin.com/user/MS4wLjABAAAA_alpha01",
    "https://www.douyin.com/user/MS4wLjABAAAA_beta02",
    "https://www.douyin.com/user/MS4wLjABAAAA_gamma03",
    "https://example.com/not-allowed",
]
MESSAGE = "你好 {nick}，看到你也在做效率工具，想交流一下。"


async def main(url: str = "http://127.0.0.1:18765/", out: Path = OUT) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport={"width": 1680, "height": 1050}, device_scale_factor=2)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_selector(".platform-card", timeout=15000)

        cards = page.locator(".platform-card")
        count = await cards.count()
        print(f"平台卡数量: {count}")
        assert count == 6, f"期望 6 个平台卡，实际 {count}"

        await page.locator('.platform-card[data-key="douyin"]').click()
        await page.wait_for_timeout(300)
        await page.locator('.chip[data-action="send_message"]').click()
        await page.wait_for_timeout(200)

        await page.fill("#targets", "\n".join(TARGETS))
        await page.fill("#message", MESSAGE)
        await page.wait_for_timeout(200)
        print("目标计数:", await page.text_content("#targetCount"))

        await page.click("#planBtn")
        await page.wait_for_selector(".step-item", timeout=15000)
        await page.wait_for_timeout(800)

        steps = await page.locator(".step-item").count()
        blocked = await page.locator("#blockedBox").is_visible()
        print(f"计划步骤: {steps}  拦截面板可见: {blocked}")
        print("计划状态:", await page.text_content("#planStatus"))

        await page.click("#approveAll")
        await page.wait_for_timeout(1200)
        approved = await page.locator(".status.st-approved").count()
        print(f"已批准步骤: {approved}")

        await page.wait_for_timeout(600)
        out.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out))
        print("saved", out)

        # 第二阶段：真正点「开始执行」，等跑完再看结果
        await page.click("#runBtn")
        try:
            await page.wait_for_function(
                "() => (document.querySelector('#progressPct')||{}).textContent === '100%'",
                timeout=60000,
            )
        except Exception as exc:
            print("等待执行完成超时:", exc)
        await page.wait_for_timeout(1000)
        done_out = out.with_name("ui_done.png")
        await page.screenshot(path=str(done_out))
        print("saved", done_out)
        print("进度:", await page.text_content("#progressText"))
        print("成功条数:", await page.locator(".status.st-ok").count())

        if errors:
            print("页面错误:")
            for e in errors[:10]:
                print("  ", e)
        await browser.close()
    return 0


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18765/"
    raise SystemExit(asyncio.run(main(u)))
