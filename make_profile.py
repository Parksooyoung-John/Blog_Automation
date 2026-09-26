"""네이버 프로필 이미지 — 선택한 마크(2번)를 정확한 브랜드 색으로 다시 그린다.

AI가 뽑은 도형의 배치는 그대로 두고, 색과 가장자리만 정확하게 만든다.
좌표는 프로필_2번_1000.png를 실측한 값이다.

    python -X utf8 make_profile.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1000
SS = 4               # 4배로 그린 뒤 줄여서 가장자리를 깨끗하게
BLUE = (27, 100, 218)   # #1b64da — 카드 도식과 동일
WHITE = (255, 255, 255)

CX = CY = 499
R = 340
BAR_W = 85
BAR_BOTTOM = 699
BARS = [(324, 460), (457, 379), (590, 299)]   # (왼쪽 x, 위쪽 y)

SRC = Path("_workspace/naver/profile_a")   # Higgsfield 원본(추적 안 함)
OUT = Path("assets/naver_img")


def draw() -> Image.Image:
    img = Image.new("RGB", (SIZE * SS, SIZE * SS), WHITE)
    d = ImageDraw.Draw(img)
    d.ellipse([(CX - R) * SS, (CY - R) * SS, (CX + R) * SS, (CY + R) * SS], fill=BLUE)
    for x, y in BARS:
        d.rounded_rectangle(
            [x * SS, y * SS, (x + BAR_W) * SS, BAR_BOTTOM * SS],
            radius=BAR_W * SS // 2, fill=WHITE,
        )
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def preview(new: Image.Image, old: Path, out: Path, px=40, zoom=6):
    """40px로 줄였을 때 알아볼 수 있는지 나란히 본다."""
    strip = Image.new("RGB", (px * 3 * zoom, px * zoom), WHITE)
    for i, im in enumerate([Image.open(old).convert("RGB"), new]):
        small = im.resize((px, px), Image.LANCZOS).resize((px * zoom, px * zoom), Image.NEAREST)
        strip.paste(small, (i * 2 * px * zoom, 0))
    strip.save(out)


if __name__ == "__main__":
    img = draw()
    img.save(OUT / "프로필_최종_1000.png")
    img.resize((160, 160), Image.LANCZOS).save(OUT / "프로필_최종_160.png")
    if (SRC / "프로필_2번_1000.png").exists():
        preview(img, SRC / "프로필_2번_1000.png", SRC / "프로필_최종_40px비교.png")
    print("완료:", OUT)
