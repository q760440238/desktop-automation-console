"""把一张方图做成应用图标：圆角裁切 + 多尺寸 .ico。

用法：
    python scripts/make_icon.py <输入图片> [输出目录]

产物：
    <输出目录>/icon.png              512x512 带透明圆角，用于文档/README
    flutter_app/windows/runner/resources/app_icon.ico   16~256 多尺寸，供 exe 使用
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ICO_PATH = ROOT / "flutter_app" / "windows" / "runner" / "resources" / "app_icon.ico"
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]


def rounded_mask(size: int, radius_ratio: float = 0.225, supersample: int = 4) -> Image.Image:
    """生成抗锯齿的圆角矩形蒙版（超采样后缩小）。"""
    big = size * supersample
    r = int(big * radius_ratio)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=r, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def build(src: Path, out_dir: Path) -> None:
    img = Image.open(src).convert("RGBA")
    side = min(img.size)
    # 居中裁成正方形
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))

    big = 1024
    img = img.resize((big, big), Image.LANCZOS)
    img.putalpha(rounded_mask(big))

    # 内描边，让图标在深色/浅色背景上都有轮廓
    stroke = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(stroke)
    w = max(2, big // 170)
    d.rounded_rectangle(
        (w // 2, w // 2, big - 1 - w // 2, big - 1 - w // 2),
        radius=int(big * 0.225),
        outline=(255, 255, 255, 46),
        width=w,
    )
    stroke = stroke.filter(ImageFilter.GaussianBlur(0.6))
    img = Image.alpha_composite(img, stroke)
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (big, big), 0), rounded_mask(big)))

    out_dir.mkdir(parents=True, exist_ok=True)
    png_out = out_dir / "icon.png"
    img.resize((512, 512), Image.LANCZOS).save(png_out)

    ICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(ICO_PATH, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    print(f"PNG: {png_out}")
    print(f"ICO: {ICO_PATH}  sizes={ICO_SIZES}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "docs"
    for p in (source,):
        if not p.is_file():
            raise SystemExit(f"找不到图片：{p}")
    build(source, target)
