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


def rounded_mask(size: int, radius_ratio: float = 0.225, supersample: int = 4,
                 inset_ratio: float = 0.0) -> Image.Image:
    """生成抗锯齿的圆角矩形蒙版（超采样后缩小）。

    inset_ratio 用来向内收一点点，把生成图自带的白色描边一起切掉。
    """
    big = size * supersample
    pad = int(big * inset_ratio)
    r = int((big - 2 * pad) * radius_ratio)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, big - 1 - pad, big - 1 - pad), radius=r, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def strip_uniform_background(img: Image.Image) -> Image.Image:
    """生成图常带白底；从四角泛洪去掉，保留图案本身。"""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    corner = rgba.getpixel((0, 0))
    if corner[0] > 238 and corner[1] > 238 and corner[2] > 238:
        for pt in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            ImageDraw.floodfill(rgba, pt, (0, 0, 0, 0), thresh=45)
    return rgba


def build(src: Path, out_dir: Path, ico_path: Path | None = None) -> None:
    img = strip_uniform_background(Image.open(src))
    side = min(img.size)
    # 居中裁成正方形
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))

    big = 1024
    img = img.resize((big, big), Image.LANCZOS)
    img.putalpha(rounded_mask(big, inset_ratio=0.018))

    # 削掉 2px 边缘：生成图的圆角带抗锯齿白边，不处理会在图标上留一圈亮线
    img.putalpha(img.getchannel("A").filter(ImageFilter.MinFilter(5)))

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

    ico_target = ico_path or ICO_PATH
    ico_target.parent.mkdir(parents=True, exist_ok=True)
    img.save(ico_target, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    print(f"PNG: {png_out}")
    print(f"ICO: {ico_target}  sizes={ICO_SIZES}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1]).resolve()
    target = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / "docs"
    ico = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    for p in (source,):
        if not p.is_file():
            raise SystemExit(f"找不到图片：{p}")
    build(source, target, ico)
