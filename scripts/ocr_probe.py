"""验证 Windows 自带 OCR 能否识别中文界面截图（用于桌面视觉定位）。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.storage import FileAccessMode, StorageFile


async def ocr(path: str):
    file = await StorageFile.get_file_from_path_async(str(Path(path).resolve()))
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        print("没有可用的 OCR 语言包")
        return None
    print("OCR 语言:", engine.recognizer_language.display_name)
    return await engine.recognize_async(bitmap)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/screenshots/qq_window.png"
    result = asyncio.run(ocr(path))
    if result is None:
        return 1
    lines = list(result.lines)
    print(f"识别到 {len(lines)} 行")
    for line in lines[:25]:
        r = line.words[0].bounding_rect
        print(f"  ({int(r.x):>4},{int(r.y):>4}) {line.text[:40]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
