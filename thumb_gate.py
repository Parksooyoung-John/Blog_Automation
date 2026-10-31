"""대표사진 게이트 — 숫자 검증·카피·템플릿·마스코트·모바일 QC·반복·manifest (30편~).

    python -X utf8 thumb_gate.py --selftest
    python -X utf8 thumb_gate.py --register-mascot   # 사용자가 넣은 mascot_master/*.png를 마스터로 등록

렌더링은 make_naver_images.py가 한다. 여기는 통과 여부만 판정한다.
마스터 돼지는 블로그 프로필 캐릭터다(선 귀·둥근 얼굴·저금통 투입구·연두 새싹·목도리 없음). 등록된 파일만 쓰고,
없으면 비슷한 돼지를 만들지 않고 MISSING_MASTER_MASCOT으로 멈춘다. 그림이 프로필과 같은지는 코드가 못 본다 —
등록은 사람이 눈으로 확인한 뒤에 한다. 여기서는 등록된 파일에서 바뀌지 않았는지만 해시로 본다.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from check_naver import CATEGORY_COLORS, MASCOT_POSES, facts, memo_value, thumb_lines

ROOT = Path(__file__).parent
MASTER_DIR = ROOT / "assets" / "naver_img" / "mascot_master"
REGISTRY = MASTER_DIR / "registry.json"
MANIFESTS = ROOT / "content" / "naver" / "_thumb_manifests"

THUMB, OUT_SIZE, QC_SIZE = 860, 1080, 216      # 렌더 좌표, 출력 크기, 모바일 그리드
CREAM = "#fdf8ef"
MAIN_MIN_216, SUB_MIN_216 = 16, 10             # 축소본에서 읽히는 글자 크기(px)
MASCOT_RATIO = (0.08, 0.105)                   # 2026-11-01 사용자 지시: 13.5%는 커서 길이를 15~20% 줄였다
BADGE_ZONE = (160 * THUMB / OUT_SIZE, 90 * THUMB / OUT_SIZE)     # 네이버 `AI 활용` 표시 자리(오른쪽 아래), 1080 기준 160×90
MAX_MAIN, MAX_SUB, MAX_BADGE, MIN_CANDIDATES = 14, 14, 14, 5     # 공백 제외. 메인은 "가급적 12자"라 비교형 여유를 둔다
MAX_SCENE_IN_9, MAX_SAME_COMPOSITION = 3, 2

NUM_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(만원|억원|만|억|%|개월|년|원)?")
TAX_ONLY_RE = re.compile(r"×\s*0\.1[25]\s*=\s*(\d+(?:[.,]\d+)*)")     # 15%·12%만 곱한 결과 — 지방소득세를 뺀 국세 기준이다(30편 135만원)
BANNED_RE = re.compile(r"무조건|폭탄|안 보면 손해")
JUDGE_RE = re.compile(r"\d|O|X|vs|될까|되나|가능|불가|계산|확인|수정|신청|오픈|조건|기준|차이")
TEMPLATE_BY_INTENT = {"calculation": "number", "definition": "number", "comparison": "compare", "decision": "compare",
                      "warning_correction": "compare", "how_to": "action", "event_opening": "action", "experience_review": "action"}
COLOR_CODE = {"tax": "tax_teal", "pension": "pension_green", "support": "support_purple", "warning": "warning_brown", "card": "card_navy"}


def copy_of(md: str) -> tuple:
    lines = thumb_lines(md) or ("", "")
    return lines[0], lines[1], memo_value(md, "썸네일 배지") or ""


def _number_units(s: str) -> set:
    out = set()
    for n, u in NUM_RE.findall(s):
        out.add((n, {"만": "만원", "억": "억원"}.get(u, u)))
    return out


def number_issues(md: str, text: str) -> list:
    """대표사진의 숫자 → 수치 근거 표와 본문에 그대로 있어야 한다. 단위 충돌·국세만 계산한 값도 막는다."""
    main, sub, badge = copy_of(md)
    copy = " ".join((main, sub, badge))
    rows = [r for r in facts(md) if r[4] in ("VERIFIED", "계산")]
    verified = _number_units(" ".join(r[1] for r in rows))
    body = _number_units(text)
    issues = []
    for n, u in sorted(_number_units(copy)):
        if re.fullmatch(r"20\d\d", n):
            continue
        if n not in {x for x, _ in verified}:
            issues.append(f"BLOCKED_UNVERIFIED_NUMBER — 수치 근거 표에 없는 숫자: {n}{u}")
        elif n not in {x for x, _ in body}:
            issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — 본문에 없는 숫자: {n}{u}")
        elif u and u not in {y for x, y in body if x == n}:
            issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — 단위가 본문과 다르다: {n}{u}")
        for r in rows:
            if n in TAX_ONLY_RE.findall(r[2]) and "국세" not in r[0] + copy:
                issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — {n}{u}은 국세만 계산한 값이다({r[0]}). 지방소득세 포함 기준을 쓴다")
    # 소득 구간이 둘인 글에서 `최대`만 쓰면 낮은 구간 독자도 그 금액을 받는 것처럼 읽힌다
    if "최대" in main and " vs " not in main and "이하" in text and "초과" in text + "넘으면" and not re.search(r"이하|초과|총급여", sub + badge):
        issues.append("BLOCKED_THUMBNAIL_FACT_MISMATCH — 구간이 둘인 글의 `최대`에 조건이 없다. 조건을 넣거나 A vs B로 쓴다")
    return issues


def copy_issues(md: str, text: str) -> list:
    """30편부터 check_naver가 부른다. SEO 제목과 분리, 카피 길이·구체성, 숫자, 입력 칸."""
    issues = []
    title = re.search(r"^제목: (.+)$", md, re.M).group(1).strip()
    kind = memo_value(md, "썸네일 유형")
    main, sub, badge = copy_of(md)
    if not main:
        return ["작성 메모 `- 썸네일 문구: 메인 | 서브`가 없다"]
    squeeze = lambda s: re.sub(r"[\s|｜:/]", "", s)
    m_, s_, b_ = squeeze(main), squeeze(sub), squeeze(badge)
    t_ = squeeze(title)
    from pipeline import contain
    if contain(m_ + s_, t_) >= 0.8:     # 글자 수로 재면 25자 제목에서 짧은 카피까지 복사로 잡혔다
        issues.append("REJECT_TITLE_COPY_AS_THUMBNAIL — SEO 제목을 그대로 넣었다")
    if len(m_) > MAX_MAIN:
        issues.append(f"메인 카피 {len(m_)}자 ({MAX_MAIN}자 이내)")
    if len(s_) > MAX_SUB:
        issues.append(f"서브 카피 {len(s_)}자 (한 줄 {MAX_SUB}자 이내)")
    if len(b_) > MAX_BADGE:
        issues.append(f"하단 배지 {len(b_)}자 ({MAX_BADGE}자 이내)")
    if main.count("/") > 1:
        issues.append("메인 카피는 2줄까지다")
    if not JUDGE_RE.search(main):
        issues.append("메인 카피에 숫자·판정·행동이 없다")
    if m := BANNED_RE.search(main + sub + badge):
        issues.append(f"금지 표현: {m.group(0)}")
    if not re.search(r"\d", sub + badge) and kind != "action":
        issues.append(f"서브·배지에 구체적인 숫자가 없다: {sub} — 한도나 기준을 쓴다")
    if kind == "action" and not (memo_value(md, "썸네일 강조 숫자") or "").strip():
        issues.append("action인데 `- 썸네일 강조 숫자:`(O·X·체크 기호)가 없다")
    if len([x for x in (memo_value(md, "썸네일 후보") or "").split("|") if x.strip()]) < MIN_CANDIDATES:
        issues.append(f"`- 썸네일 후보:`에 메인 카피 후보 {MIN_CANDIDATES}개가 없다")
    if memo_value(md, "카테고리 색") not in CATEGORY_COLORS:
        issues.append(f"`- 카테고리 색:`이 {' · '.join(CATEGORY_COLORS)} 중 하나가 아니다")
    if memo_value(md, "돼지 자세") not in MASCOT_POSES + ("없음",):
        issues.append(f"`- 돼지 자세:`가 {' · '.join(MASCOT_POSES)} · 없음 중 하나가 아니다")
    if kind == "scene" and not memo_value(md, "AI 사용 이유"):
        issues.append("scene인데 `- AI 사용 이유:`가 없다")
    return issues + number_issues(md, text)


def template_for(intent: str) -> str:
    return TEMPLATE_BY_INTENT.get(intent, "number")


def mascot_status(pose: str, category: str, master_dir: Path = None) -> tuple:
    """→ (상태, 파일). OK · MISSING_MASTER_MASCOT · BLOCKED_MASCOT_INCONSISTENCY. 돼지 생략은 엄격한 주제(warning)만."""
    d = master_dir or MASTER_DIR
    if pose == "없음":
        return ("OK", None) if category == "warning" else ("MISSING_MASTER_MASCOT", None)
    png, reg = d / f"{pose}.png", d / "registry.json"
    if not png.exists() or not reg.exists():
        return "MISSING_MASTER_MASCOT", None
    want = json.loads(reg.read_text(encoding="utf-8")).get(pose)
    if want is None:
        return "MISSING_MASTER_MASCOT", None
    if hashlib.sha256(png.read_bytes()).hexdigest() != want:
        return "BLOCKED_MASCOT_INCONSISTENCY", None
    return "OK", png


def cut_face(src: Path, out: Path) -> Path:
    """프로필 원본 → 배경을 지운 얼굴 PNG. AI를 쓰지 않으니 그림은 프로필 그대로다.
    프로필은 몸통이 화면 아래에서 잘려 있다. 턱을 타원으로 끊으면 얼굴이 납작해져서, 잘린 면 그대로 두고 대표사진의 하단 띠 위에 앉힌다."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(src).convert("RGB")
    w, h = im.size
    mark = im.copy()
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(mark, corner, (255, 0, 255), thresh=18)     # 배경 크림색만 지운다
    bg = Image.eval(mark.getchannel("R"), lambda v: 255 if v == 255 else 0)
    is_bg = Image.composite(Image.new("L", im.size, 255), Image.new("L", im.size, 0),
                            Image.eval(mark.getchannel("G"), lambda v: 255 if v == 0 else 0))
    alpha = Image.composite(Image.new("L", im.size, 0), Image.new("L", im.size, 255), Image.composite(is_bg, Image.new("L", im.size, 0), bg))
    alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
    res = im.convert("RGBA")
    res.putalpha(alpha)
    res = res.crop(alpha.point(lambda v: 255 if v >= 128 else 0).getbbox())
    out.parent.mkdir(parents=True, exist_ok=True)
    res.save(out)
    return out


def register_mascots() -> int:
    """사용자가 프로필과 같은지 눈으로 본 파일만 넣고 실행한다. 투명 배경이 아니면 등록하지 않는다."""
    from PIL import Image
    found = {}
    for pose in MASCOT_POSES:
        p = MASTER_DIR / f"{pose}.png"
        if not p.exists():
            continue
        alpha = Image.open(p).convert("RGBA").getchannel("A")
        if sum(alpha.histogram()[128:]) / (alpha.width * alpha.height) > 0.9:
            print(f"{p.name}: 투명 배경이 아니다 — 등록하지 않았다")
            continue
        found[pose] = hashlib.sha256(p.read_bytes()).hexdigest()
    REGISTRY.write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"등록 {len(found)}개: {', '.join(found)} / 없음: {', '.join(set(MASCOT_POSES) - set(found)) or '-'}")
    return 0 if found else 1


def luminance(hex_color: str) -> float:
    vals = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in vals]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def badge_zone_hit(rect: dict) -> bool:
    """rect(렌더 좌표)가 오른쪽 아래 플랫폼 표시 자리에 닿는가."""
    return bool(rect) and rect["right"] > THUMB - BADGE_ZONE[0] and rect["bottom"] > THUMB - BADGE_ZONE[1]


def mobile_qc(main_px: float, sub_px: float, ratio: float, strict: bool = False, mascot_rect: dict = None,
              text_rects: list = (), color: str = "#000000") -> dict:
    """렌더 값 → {fail: [...], drop_sub}. 서브가 안 읽히면 키우지 말고 뺀다. 축소본은 사람도 눈으로 본다."""
    scale = QC_SIZE / THUMB
    fail = []
    if main_px * scale < MAIN_MIN_216:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 메인 카피가 {QC_SIZE}px에서 {main_px * scale:.0f}px")
    hi = 0.05 if strict else MASCOT_RATIO[1]
    if ratio > hi + 0.005:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 돼지가 {ratio:.0%} ({hi:.0%} 이하)")
    if badge_zone_hit(mascot_rect) or any(badge_zone_hit(r) for r in text_rects):
        fail.append("BLOCKED_MOBILE_READABILITY — 오른쪽 아래 `AI 활용` 표시 자리와 겹친다")
    if contrast(color, CREAM) < 4.5:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 글자색 대비 {contrast(color, CREAM):.1f} (4.5 이상)")
    return {"fail": fail, "drop_sub": bool(sub_px) and sub_px * scale < SUB_MIN_216}


def repeat_issues(rows: dict) -> list:
    """편 번호 → {kind, pose, composition, main}. 30편부터 최근 9개 반복. 베이지 실내 배경 연속은 코드가 못 봐 사람이 본다."""
    seq = sorted((int(k), v) for k, v in rows.items() if v.get("kind"))
    out = []
    for i, (n, v) in enumerate(seq):
        if n < 30:
            continue
        window = [x for _, x in seq[max(0, i - 8):i + 1]]
        last3 = [x for _, x in seq[max(0, i - 2):i + 1]]
        why = []
        if v["kind"] == "scene":
            if sum(x["kind"] == "scene" for x in window) > MAX_SCENE_IN_9:
                why.append(f"AI 대표사진이 최근 9개 중 {MAX_SCENE_IN_9}개를 넘는다")
            if v.get("composition") and sum(x.get("composition") == v["composition"] for x in window) > MAX_SAME_COMPOSITION:
                why.append(f"같은 구도가 {MAX_SAME_COMPOSITION}개를 넘는다: {v['composition']}")
        if len(last3) == 3:
            if len({x["kind"] for x in last3}) == 1:
                why.append(f"템플릿 {v['kind']} 3연속")
            pose = v.get("pose")
            if pose and pose != "없음" and all(x.get("pose") == pose for x in last3):
                why.append(f"돼지 자세 {pose} 3연속")
            shapes = [re.sub(r"\d+(?:[.,]\d+)*", "N", x.get("main") or "") for x in last3]
            if shapes[0] and len(set(shapes)) == 1:
                why.append(f"메인 카피 구조 3연속: {shapes[0]}")
        out += [(n, f"BLOCKED_VISUAL_REPETITION — {w}") for w in why]
    return out


def write_manifest(num: str, md: str, status: str, mascot: Path, ratio: float, passed: bool, original: Path, preview: Path) -> Path:
    import datetime
    main, sub, badge = copy_of(md)
    rows = [r for r in facts(md) if r[4] in ("VERIFIED", "계산")]
    numbers = [n for n, _ in _number_units(main + " " + badge) if not re.fullmatch(r"20\d\d", n)]
    src = re.findall(r"^- 출처:.*?(https?://\S+)", md, flags=re.M)
    kind = memo_value(md, "썸네일 유형")
    title = re.search(r"^제목: (.+)$", md, re.M).group(1).strip()
    fields = {
        "thumbnail_id": f"TH-{datetime.date.today():%Y%m%d}-{num}", "status": status, "seo_title": title,
        "template_type": {"number": "calculation", "compare": "comparison", "action": "action"}.get(kind, kind),
        "main_copy": main, "sub_copy": sub, "bottom_badge": badge, "copy_candidates": memo_value(md, "썸네일 후보") or "",
        "verified_number": ", ".join(numbers), "verified_rows": " / ".join(r[0] for r in rows if set(numbers) & {x for x, _ in _number_units(r[1])}),
        "verified_source_url": src[0] if src else "", "verified_at": (memo_value(md, "최신성 재확인") or "").split("|")[0].strip(),
        "category": memo_value(md, "카테고리 색") or "", "color_code": COLOR_CODE.get(memo_value(md, "카테고리 색"), ""),
        "human_required": kind == "scene", "mascot_asset": str(mascot.name) if mascot else "", "mascot_pose": memo_value(md, "돼지 자세") or "",
        "mascot_area_ratio": round(ratio, 3), "mascot_position": "lower_right_safe" if mascot else "none", "platform_badge_safe_zone": passed,
        "mobile_preview_passed": passed, "fact_check_passed": not number_issues(md, parts_text(md)),
        "output_original": original.name, "output_mobile_preview": preview.name,
    }
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    out = MANIFESTS / f"{num}.yaml"
    out.write_text("".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in fields.items()), encoding="utf-8")
    return out


def parts_text(md: str) -> str:
    """작성 메모를 뺀 본문."""
    return md.split("## 작성 메모")[0]


def selftest():
    import tempfile
    facts_tbl = ("### 수치 근거\n\n| 항목 | 값 | 출처·식 | 확인일 | 상태 |\n|---|---|---|---|---|\n"
                 "| 합산 한도 | 연 900만원 | 소득세법 | 2026-10-31 | VERIFIED |\n"
                 "| 연금저축 한도 | 연금저축 600만원 + IRP 300만원 | 600 + 300 = 900 | 2026-10-31 | 계산 |\n"
                 "| 지방소득세 포함 최대 | 148.5만원, 118.8만원 | 900 × 0.165 = 148.5, 900 × 0.132 = 118.8 | 2026-10-31 | 계산 |\n"
                 "| 가상 사례 배분 | 900만원 → 135만원 | 900 × 0.15 = 135 | 2026-10-31 | 계산 |\n"
                 "| 기한 | 2개월 | 국세기본법 | 2026-10-31 | VERIFIED |\n"
                 "| 구간 | 총급여 5,500만원 이하 | 소득세법 | 2026-10-31 | VERIFIED |\n")
    text = "총급여 5,500만원 이하와 초과로 갈립니다. 연금저축 600만원과 IRP 300만원, 합산 900만원. 148.5만원, 118.8만원, 135만원, 2개월입니다."

    def doc(main="600 + 300만원", sub="연금저축·IRP 나누기", badge="합산 900만원 한도", extra=""):
        return (f"제목: 2026 IRP 세액공제 계산｜연금저축과 나눠 납입하는 방법\n\n{text}\n\n## 작성 메모\n\n"
                f"- 썸네일 유형: number\n- 썸네일 문구: {main} | {sub}\n- 썸네일 배지: {badge}\n- 썸네일 후보: a | b | c | d | e\n"
                f"- 카테고리 색: pension\n- 돼지 자세: calculator\n{extra}\n{facts_tbl}")

    assert copy_issues(doc(), text) == [], copy_issues(doc(), text)
    assert copy_issues(doc("148.5만 vs 118.8만", "총급여별 IRP 공제", "연금저축 600 + IRP 300"), text) == []

    # TEST-THUMB-IRP-001: 국세만 계산한 135만원, 뜻이 넓은 `납입 나누는 법`
    old = copy_issues(doc("135만원", "IRP 공제 계산", "납입 나누는 법"), text)
    assert any("국세만" in i for i in old), old
    assert any("구체적인 숫자" in i for i in copy_issues(doc("IRP 계산", "납입 나누는 법", ""), text))
    assert any("`최대`" in i for i in copy_issues(doc("최대 148.5만원", "IRP·연금저축 세액공제", "연 900만원 한도"), text))
    assert copy_issues(doc("최대 148.5만원", "총급여 5,500만원 이하", "연 900만원 한도"), text) == []
    # 숫자·단위 — 2년과 2개월, 근거 없는 숫자, 제목 복사, 금지어
    assert any("단위" in i for i in copy_issues(doc("기한 2년 확인"), text))
    assert any("BLOCKED_UNVERIFIED_NUMBER" in i for i in copy_issues(doc("200만원 계산"), text))
    assert any("REJECT_TITLE_COPY" in i for i in copy_issues(doc("2026 IRP 세액공제 계산", "연금저축과 나눠 납입하는 방법"), text))
    assert any("금지" in i for i in copy_issues(doc("무조건 900만원"), text))
    assert any("후보" in i for i in copy_issues(doc().replace("- 썸네일 후보: a | b | c | d | e\n", ""), text))

    # TEST-THUMB-MASCOT-002: 등록 안 된 돼지·바뀐 파일은 쓰지 않는다. 마스터가 없으면 만들지 않고 멈춘다
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        assert mascot_status("calculator", "pension", d)[0] == "MISSING_MASTER_MASCOT"
        Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(d / "calculator.png")
        assert mascot_status("calculator", "pension", d)[0] == "MISSING_MASTER_MASCOT"
        (d / "registry.json").write_text(json.dumps({"calculator": hashlib.sha256((d / "calculator.png").read_bytes()).hexdigest()}), encoding="utf-8")
        assert mascot_status("calculator", "pension", d)[0] == "OK"
        Image.new("RGBA", (11, 11), (255, 0, 0, 0)).save(d / "calculator.png")     # 처진 귀·목도리 돼지로 바꿔치기한 경우
        assert mascot_status("calculator", "pension", d)[0] == "BLOCKED_MASCOT_INCONSISTENCY"
        assert mascot_status("없음", "pension", d)[0] == "MISSING_MASTER_MASCOT"
        assert mascot_status("없음", "warning", d)[0] == "OK"

    # TEST-THUMB-MOBILE-003: 돼지 20%·배지 자리 중첩은 실패, 12~15%·안전 위치는 통과
    safe = {"right": 834, "bottom": 776}
    hit = {"right": 850, "bottom": 850}
    assert mobile_qc(120, 52, 0.09, mascot_rect=safe)["fail"] == []
    assert any("돼지" in x for x in mobile_qc(120, 52, 0.20, mascot_rect=safe)["fail"])
    assert any("AI 활용" in x for x in mobile_qc(120, 52, 0.09, mascot_rect=hit)["fail"])
    assert any("메인" in x for x in mobile_qc(40, 0, 0.09)["fail"])
    assert mobile_qc(120, 30, 0.09)["drop_sub"] and not mobile_qc(120, 0, 0.09)["drop_sub"]
    assert any("대비" in x for x in mobile_qc(120, 52, 0.09, color="#dddddd")["fail"])
    assert all(contrast(c, CREAM) >= 4.5 for c in CATEGORY_COLORS.values()), "카테고리 색 대비"
    assert OUT_SIZE == 1080 and round(BADGE_ZONE[0] * OUT_SIZE / THUMB) == 160

    # 얼굴 자산 — 배경은 투명, 얼굴은 그대로 남고 아래는 둥글게 끊긴다
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "s.png"
        im = Image.new("RGB", (400, 300), (251, 247, 235))
        from PIL import ImageDraw
        ImageDraw.Draw(im).ellipse([100, 40, 300, 340], fill=(250, 190, 180))
        im.save(src)
        res = Image.open(cut_face(src, Path(d) / "face.png"))
        assert res.mode == "RGBA" and res.getpixel((res.width // 2, res.height // 2))[3] == 255
        assert res.getpixel((0, 0))[3] == 0

    # 반복 — 21~29편이 전부 AI 장면이라 30편 scene은 막힌다
    past = {str(n): {"kind": "scene", "composition": "창가 옆모습" if n > 27 else str(n)} for n in range(21, 30)}
    got = repeat_issues({**past, "30": {"kind": "scene", "composition": "창가 옆모습", "pose": "없음"}})
    assert any("AI 대표사진" in w for _, w in got) and any("구도" in w for _, w in got), got
    assert not any(n == 30 and "AI" in w for n, w in repeat_issues({**past, "30": {"kind": "number"}}))
    three = {str(30 + i): {"kind": k, "pose": "check", "main": f"{i}만원 계산"} for i, k in enumerate(("number", "compare", "action"))}
    got = [w for _, w in repeat_issues(three)]
    assert any("자세" in w for w in got) and any("구조" in w for w in got) and not any("템플릿" in w for w in got), got
    assert any("템플릿" in w for _, w in repeat_issues({str(30 + i): {"kind": "number"} for i in range(3)}))
    assert template_for("calculation") == "number" and template_for("warning_correction") == "compare" and template_for("how_to") == "action"

    # manifest
    with tempfile.TemporaryDirectory() as d:
        global MANIFESTS
        keep, MANIFESTS = MANIFESTS, Path(d)
        try:
            p = write_manifest("30", doc(), "OK", None, 0.0, True, Path("a.png"), Path("b.png"))
            t = p.read_text(encoding="utf-8")
            assert 'main_copy: "600 + 300만원"' in t and "fact_check_passed: true" in t and "thumbnail_id" in t, t
        finally:
            MANIFESTS = keep
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--cut-face" in sys.argv:
        print(cut_face(Path(sys.argv[sys.argv.index("--cut-face") + 1]), MASTER_DIR / "face.png"))
    elif "--register-mascot" in sys.argv:
        sys.exit(register_mascots())
    else:
        print(__doc__)
