"""네이버 모바일 커버 1080x1300 생성.

배경(그라데이션+점그리드)은 Higgsfield C안을 실측해 그대로 다시 그린다.
직접 그리는 이유: 네이버 '커버 1' 스타일이 하단 80%·88% 지점에 블로그명과
프로필을 얹기 때문에, 막대 위치를 픽셀 단위로 피해야 한다.

    python -X utf8 make_cover.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1300
SS = 2                    # 2배로 그린 뒤 축소 — 라운드 끝을 매끄럽게
MARGIN = 94

TOP_RGB = (244, 245, 237)     # 실측: cover_c_3 상단
BOT_RGB = (223, 237, 249)     # 실측: cover_c_3 하단
DOT_GAP, DOT_SIZE = 25, 2

INK = (26, 26, 26)
SUB_INK = (90, 100, 114)
AMBER = (245, 159, 0)
BLUE = (27, 100, 218)         # 프로필 마크와 동일
CHIP_BG = (219, 231, 251)

TITLE = "머니브리핑"
SUB = "지원금·세금, 숫자로 정리합니다"
CHIPS = ["근로장려금", "실업급여", "연말정산"]

# 세로 좌표. 네이버가 y 1040 부근에 블로그명, 1144 부근에 프로필을 얹으므로
# 우리 요소는 전부 y 930 위에서 끝낸다.
Y_ACCENT, Y_TITLE, Y_SUB, Y_CHIPS = 150, 196, 368, 478
BARS = [(606, 420), (724, 580), (842, 740)]   # (위쪽 y, 가로 길이)
BAR_H = 88

BOLD = "C:/Windows/Fonts/malgunbd.ttf"
REG = "C:/Windows/Fonts/malgun.ttf"


def background() -> Image.Image:
    img = Image.new("RGB", (W * SS, H * SS))
    d = ImageDraw.Draw(img)
    for y in range(H * SS):
        t = y / (H * SS - 1)
        row = tuple(round(a + (b - a) * t) for a, b in zip(TOP_RGB, BOT_RGB))
        d.line([(0, y), (W * SS, y)], fill=row)
        if y % (DOT_GAP * SS) == 0:
            dot = tuple(max(0, c - 45) for c in row)
            for x in range(12 * SS, W * SS, DOT_GAP * SS):
                d.rectangle([x, y, x + DOT_SIZE * SS - 1, y + DOT_SIZE * SS - 1], fill=dot)
    return img


def draw_chips(d: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont):
    x = MARGIN * SS
    for label in CHIPS:
        w = round(d.textlength(label, font=font)) + 44 * SS
        d.rounded_rectangle([x, Y_CHIPS * SS, x + w, (Y_CHIPS + 56) * SS],
                            radius=28 * SS, fill=CHIP_BG)
        d.text((x + 22 * SS, (Y_CHIPS + 12) * SS), label, font=font, fill=BLUE)
        x += w + 14 * SS


def build() -> Image.Image:
    img = background()
    d = ImageDraw.Draw(img)

    d.rectangle([MARGIN * SS, Y_ACCENT * SS, (MARGIN + 64) * SS, (Y_ACCENT + 8) * SS], fill=AMBER)
    d.text((MARGIN * SS, Y_TITLE * SS), TITLE, font=ImageFont.truetype(BOLD, 104 * SS), fill=INK)
    d.text((MARGIN * SS, Y_SUB * SS), SUB, font=ImageFont.truetype(REG, 42 * SS), fill=SUB_INK)
    draw_chips(d, ImageFont.truetype(BOLD, 30 * SS))

    for y, w in BARS:   # 프로필 마크와 같은 스타디움 형태
        d.rounded_rectangle([MARGIN * SS, y * SS, (MARGIN + w) * SS, (y + BAR_H) * SS],
                            radius=BAR_H * SS // 2, fill=BLUE)

    return img.resize((W, H), Image.LANCZOS)


BAND_TOP, BAND_RGB = 980, (19, 58, 122)


def with_band(img: Image.Image) -> Image.Image:
    """하단을 진한 남색으로 덮는다 — 네이버가 얹는 흰 글씨의 가독성 확보용."""
    p = img.copy()
    ImageDraw.Draw(p).rectangle([0, BAND_TOP, W, H], fill=BAND_RGB)
    return p


def naver_preview(img: Image.Image) -> Image.Image:
    """네이버 '커버 1'이 얹는 블로그명·프로필 위치를 모사해 겹침을 확인한다.
    좌표는 실제 앱 화면을 재서 얻은 값이다(전체 높이의 80%, 88% 부근)."""
    p = img.copy()
    d = ImageDraw.Draw(p)
    d.text((26, 1020), "머니브리핑 | 지원금·세금 정리",
           font=ImageFont.truetype(BOLD, 38), fill=(255, 255, 255),
           stroke_width=2, stroke_fill=(90, 90, 90))
    d.ellipse([32, 1120, 84, 1172], fill=(170, 170, 170))
    d.text((100, 1132), "머니브리핑", font=ImageFont.truetype(REG, 28), fill=(255, 255, 255),
           stroke_width=2, stroke_fill=(90, 90, 90))
    return p


if __name__ == "__main__":
    out = Path("_workspace/naver/cover_c/커버_최종.png")
    img = build()
    img.save(out)
    naver_preview(img).save(out.with_name("커버_최종_앱미리보기.png"))
    band = with_band(img)
    band.save(out.with_name("커버_최종_하단밴드.png"))
    naver_preview(band).save(out.with_name("커버_최종_하단밴드_앱미리보기.png"))
    print(out, img.size)
