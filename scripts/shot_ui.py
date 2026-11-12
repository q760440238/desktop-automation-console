"""给控制台界面截图，用于交付验收。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "screenshots" / "ui.png"


async def main(url: str = "http://127.0.0.1:18765/", out: Path = OUT) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport={"width": 1680, "height": 1050}, device_scale_factor=1)
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2500)
        out.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(out), full_page=False)
        title = await page.title()
        await browser.close()
    print(f"saved {out}  title={title}")
    return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18765/"
    raise SystemExit(asyncio.run(main(url)))
