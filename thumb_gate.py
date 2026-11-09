"""대표사진 게이트 — 숫자 검증·카피·템플릿·마스코트·모바일 QC·반복·manifest (30편~).

    python -X utf8 thumb_gate.py --selftest
    python -X utf8 thumb_gate.py --import-pose calculator 받은.png   # 받은 후보를 키·발 위치 맞춰 저장
    python -X utf8 thumb_gate.py --register-mascot   # 사용자가 승인한 새 pig_*.png를 등록(이미 등록된 파일은 건드리지 않는다)
    python -X utf8 thumb_gate.py --approve-asset 이름  # 사용자가 터미널에서 직접. 바뀐 자산을 새 버전으로 승인

렌더링은 make_naver_images.py가 한다. 여기는 통과 여부만 판정한다.
마스터 돼지는 블로그 프로필 캐릭터다(선 귀·둥근 얼굴·저금통 투입구·연두 새싹·목도리 없음). 자세와 소품은 한 번만 만들어 등록하고
글마다 다시 만들지 않는다. 자세 반복은 막지 않는다. 그림이 프로필과 같은지는 코드가 못 본다 —
등록은 사람이 눈으로 확인한 뒤에 한다. 여기서는 등록된 파일에서 바뀌지 않았는지만 해시로 본다.
자동 검사 통과는 사실 정확성 보장이 아니다. 낱말·역할 검사는 보조 수단이고 의미 일치를 보장하지 않는다.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from check_naver import CATEGORY_COLORS, MASCOT_POSES, facts, memo_value, thumb_lines

ROOT = Path(__file__).parent
MASTER_DIR = ROOT / "assets" / "mascot" / "pig"
REGISTRY = MASTER_DIR / "registry.json"
MANIFESTS = ROOT / "content" / "naver" / "_thumb_manifests"

THUMB, OUT_SIZE, QC_SIZE = 860, 1080, 160      # 렌더 좌표, 출력 크기, 가장 작은 축소본
QC_PREVIEWS = (160, 320)
CREAM = "#fdf8ef"
MAIN_MIN_QC, SUB_MIN_QC = 12, 7.5              # 160px 축소본에서 읽히는 글자 크기(px)
MASCOT_RATIO = (0.13, 0.25)                    # 2026-11-01 사용자 확정 시안의 돼지가 13.5%라 하한을 13%로 낮췄다
BADGE_ZONE = (160 * THUMB / OUT_SIZE, 90 * THUMB / OUT_SIZE)     # 내부 AI 표시 안전영역(오른쪽 아래, 1080 기준 160×90). 네이버 공식 크기가 아니다. 실제 표시는 게시 화면에서 본다
MAX_MAIN, MAX_SUB, MAX_BADGE, MIN_CANDIDATES = 16, 14, 14, 3     # 공백 제외. 후보는 내부에서 3개 만들어 1개를 고른다
MAX_LINES = {"compare": 2, "number": 2, "headline_v2": 3, "photo_question": 2, "photo_compare": 2}     # 판별 메인 줄 수. 질문형만 상황·대상·질문 3줄을 쓴다
LAYOUT = {"compare": "compare", "number": "number", "headline": "headline_v2", "photo_question": "photo_question", "photo_compare": "photo_compare"}     # 틀마다 지금 판
APPROVED_LAYOUTS = {"compare", "number", "headline_v2", "photo_question", "photo_compare"}   # 사용자가 미리보기를 승인한 판(compare 2026-11-01, number·headline_v2 2026-11-04, photo 두 틀 2026-11-09 카드 78%). 승인 전 판은 미리보기만 만들고 운영은 headline_v2로 한다(사진 틀은 대체 없음)
SAMPLE_EVERY = 5                               # 안정화된 틀은 5편마다 1편 축소본을 표본 확인한다(발행을 기다리게 하지 않는다)

NUM_RE = re.compile(r"(\d+(?:[.,]\d+)*)\s*(만원|억원|만|억|%|개월|년|원)?")
TAX_ONLY_RE = re.compile(r"×\s*0\.1[25]\s*=\s*(\d+(?:[.,]\d+)*)")     # 15%·12%만 곱한 결과 — 지방소득세를 뺀 국세 기준이다(30편 135만원)
BANNED_RE = re.compile(r"무조건|폭탄|안 보면 손해|모르면 손해|전부|누구나")
CLAIM_STOP = {"정리", "총정리", "방법", "확인"}
SPECIFIC_RE = re.compile(r"\d|\?|O|X|vs|될까|되나|가능|불가|계산|확인|수정|신청|오픈|조건|기준|차이|대상|누가|언제|어디|얼마|어떻게|왜")
REFUND_RE, CREDIT_RE, LIMIT_RE = re.compile(r"환급|돌려받"), re.compile(r"세액공제|공제액|공제받"), re.compile(r"한도|대상|납입|배분")
TEMPLATE_BY_INTENT = {"calculation": "number", "definition": "number", "comparison": "compare", "decision": "compare",
                      "warning_correction": "compare", "how_to": "action", "event_opening": "action", "experience_review": "action"}
COLOR_CODE = {"tax": "tax_teal", "pension": "pension_green", "support": "support_purple", "warning": "warning_brown", "card": "card_navy"}
POSE_BY_TOPIC = {"tax_calculation": ("calculator",), "application": ("document", "check"), "online_process": ("laptop", "phone"), "comparison": ("thinking",), "warning": ("surprised",),
                 "checklist": ("check", "document"), "refund_support": ("coin",), "dependent_family": ("family",), "lookup": ("phone", "laptop"), "general": ("face", "point_up", "point_left")}     # 앞이 기본, 뒤는 동등하게 맞는 자세
TOPIC_BY_TYPE = {"계산·실수령형": "tax_calculation", "서식·절차형": "application", "선택·비교형": "comparison", "오류·누락형": "warning", "혜택·지원금형": "refund_support"}
AVOID_RECENT = 3
POSE_SIZE, POSE_HEIGHT = 1600, (0.60, 0.85)     # 캔버스, 캐릭터 높이 비율(규격 약 75%)
POSE_TOP, POSE_BOTTOM = 200, 1400               # 모든 자세의 머리·발 위치. 템플릿 돼지 칸 하나로 12종이 같은 크기로 띠 위에 선다
PROPS = ROOT / "assets" / "mascot" / "props"
PROP_FILES = {"동전": "coins"}                  # `- 썸네일 소품:` → 등록된 소품 파일
CARD_TITLE_CHARS, CARD_LINE_EM, CARD_LINES = 5, 4.6, 3   # 카드 제목 글자 수, 내용 한 줄 폭(em), 줄 수



def text_em(text: str) -> float:
    """글자 폭 추정(em). 한글 1, 좁은 문자 0.3~0.6으로 넉넉하게 잡는다."""
    return sum(1 if "가" <= c <= "힣" else 0.3 if c in " .,:" else 0.6 for c in text)


def card_amount(body: str):
    """카드 내용이 `600만원`처럼 금액이면 (숫자, 단위)."""
    m = re.fullmatch(r"([\d.,]*\d)\s*([가-힣%]+)", body.strip())
    return m.groups() if m else None


def thumb_cards(md: str) -> list:
    """`- 썸네일 카드: A제목 | A내용 | B제목 | B내용 | +`. 내용은 금액(`600만원`)이거나 문장이다. 문장의 `/`는 줄바꿈. `+`는 합산할 때만."""
    raw = memo_value(md, "썸네일 카드")
    return [x.strip() for x in raw.split("|")] if raw else []


def can_add(cards: list) -> bool:
    """더하기는 단위가 같은 두 금액을 합산할 때만 쓴다."""
    a, b = [card_amount(c) for c in cards[1:4:2]] if len(cards) >= 4 else (None, None)
    return len(cards) == 5 and cards[4] == "+" and bool(a and b) and a[1] == b[1]


def trim_copy(main: str, sub: str, badge: str) -> tuple:
    """메인과 같거나 앞 문구와 같은 보조·하단은 생략한다."""
    squeeze = lambda s: re.sub(r"[\s/|｜:]", "", s)
    sub = "" if squeeze(sub) and squeeze(sub) in squeeze(main) else sub
    badge = "" if squeeze(badge) and (squeeze(badge) in squeeze(main) or squeeze(badge) == squeeze(sub)) else badge
    return main, sub, badge


def copy_of(md: str) -> tuple:
    """→ (메인, 서브, 배지). 메인의 `/`는 줄바꿈이라 남긴다. thumb_lines는 글자 수를 세려고 지운다."""
    raw = memo_value(md, "썸네일 문구") or ""
    main, _, sub = raw.partition("|")
    return (main.strip(), sub.strip(), memo_value(md, "썸네일 배지") or "") if thumb_lines(md) else ("", "", memo_value(md, "썸네일 배지") or "")


def _number_units(s: str) -> set:
    out = set()
    for n, u in NUM_RE.findall(s):
        out.add((n, {"만": "만원", "억": "억원"}.get(u, u)))
    return out


def number_issues(md: str, text: str) -> list:
    """대표사진의 숫자 → 수치 근거 표와 본문에 그대로 있어야 한다. 단위 충돌·국세만 계산한 값도 막는다."""
    main, sub, badge = copy_of(md)
    focus = (memo_value(md, "썸네일 강조 숫자") or "").split("|")[0]
    copy = " ".join((main, sub, badge, focus, *[c.replace("/", " ") for c in thumb_cards(md)]))
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
            if n in TAX_ONLY_RE.findall(r[2]) and "국세" not in copy:
                issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — {n}{u}은 국세만 계산한 값이다({r[0]}). 지방소득세 포함 기준을 쓰거나 대표사진에 `국세 기준`을 표시한다")
    # 공제율이 다른 구간이 있는 글에서 `최대`만 쓰면 낮은 구간 독자도 그 금액을 받는 것처럼 읽힌다
    if "최대" in copy and " vs " not in main and "이하" in text and ("초과" in text or "넘으면" in text) and not re.search(r"이하|초과|총급여", copy):
        issues.append("BLOCKED_THUMBNAIL_FACT_MISMATCH — 구간이 둘인 글의 `최대`에 조건이 없다. 조건을 넣거나 한도·선택 문제를 강조한다")
    return issues


def role_issues(md: str) -> list:
    """납입액·공제대상액·세액공제액·환급액 혼동. 같은 문구의 금액이 근거 표에서 무엇인지 항목 이름으로 대조한다. 뜻까지 보지는 못한다."""
    main, sub, badge = copy_of(md)
    cards = thumb_cards(md)
    pieces = [*main.split("/"), sub, badge, *[f"{cards[i]} {cards[i + 1]}" for i in (0, 2) if len(cards) >= 4]]
    rows = [r for r in facts(md) if r[4] in ("VERIFIED", "계산")]
    issues = []
    for piece in pieces:
        for n, u in sorted(_number_units(piece)):
            found = [r for r in rows if n in {x for x, _ in _number_units(r[1])}]
            if not found:
                continue
            if REFUND_RE.search(piece) and not any(REFUND_RE.search(r[0] + r[1]) for r in found):
                issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — {n}{u}은 환급액이 아니다: {piece.strip()}")
            if CREDIT_RE.search(piece) and not LIMIT_RE.search(piece) and all(LIMIT_RE.search(r[0]) for r in found):
                issues.append(f"BLOCKED_THUMBNAIL_FACT_MISMATCH — {n}{u}은 한도·납입액이지 세액공제액이 아니다: {piece.strip()}")
    return issues


def evidence_quotes(md: str) -> list:
    """`- 썸네일 근거: 본문 문장 | 본문 문장`. 메인의 질문에 답하는 본문을 그대로 옮긴다."""
    return [x.strip() for x in (memo_value(md, "썸네일 근거") or "").split("|") if x.strip()]


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("*", ""))


def repeat_copy_issues(main: str, others: list) -> list:
    """경고 — 다른 정보를 주지 않는 반복. 단위를 붙인 금액 카드는 비교·배분 이해에 필요하니 넣지 않는다(review_copy)."""
    nums = {n for n, _ in _number_units(main)}
    issues = []
    squeezed = re.sub(r"[\s/|｜:]", "", main)
    for o in others:
        again = nums & {n for n, _ in _number_units(o)}
        if again:
            issues.append(f"메인의 숫자 {', '.join(sorted(again))}를 다시 적었다: {o}")
        if o and re.sub(r"[\s/|｜:]", "", o) in squeezed:
            issues.append(f"메인과 같은 문구라 생략한다: {o}")
    return issues


def claim_issues(phrases: list, text: str) -> list:
    """경고 — 하단·카드의 낱말이 본문에 없다. 동의어·요약일 수 있어 막지 않는다. 낱말이 있어도 뜻이 맞다는 보장은 아니다."""
    issues = []
    for phrase in phrases:
        for word in re.findall(r"[가-힣]{2,}", phrase):
            word = re.sub(r"(으로|와|과|및|을|를|은|는|이|가|의|로)$", "", word)
            if len(word) >= 2 and word not in CLAIM_STOP and word not in text:
                issues.append(f"WARN_THUMBNAIL_WORDING — 본문에 없는 낱말: {word} ({phrase}). 본문이 답하는지 확인한다")
    return issues


def card_copy_issues(cards: list) -> list:
    """카드 문제. 있으면 막지 않고 headline으로 바꾼다(select_template)."""
    if len(cards) not in (4, 5) or (len(cards) == 5 and cards[4] != "+"):
        return ["`- 썸네일 카드:`는 A제목 | A내용 | B제목 | B내용 | + 형식이다"]
    issues = []
    for title in (cards[0], cards[2]):
        if not title or len(re.sub(r"\s", "", title)) > CARD_TITLE_CHARS:
            issues.append(f"카드 제목은 1~{CARD_TITLE_CHARS}자다: {title}")
    for body in (cards[1], cards[3]):
        if not body:
            issues.append("카드 내용이 비었다")
        if card_amount(body):
            continue
        lines = [x.strip() for x in body.split("/") if x.strip()]
        if len(lines) > CARD_LINES:
            issues.append(f"카드 내용은 {CARD_LINES}줄까지다: {body}")
        issues += [f"카드 한 줄이 넘친다: {x}" for x in lines if text_em(x) > CARD_LINE_EM]
    return issues


def number_parts(main: str):
    """number 메인 → (기준 대상, 숫자+단위, 뒤 낱말). 숫자 묶음이 하나이고 기준 대상 낱말이 있을 때만.
    `25%`만 크게 쓰면 공제율처럼 읽힌다. `총급여의 25%`처럼 무엇의 숫자인지가 붙어야 한다."""
    flat = main.replace("/", " ")
    found = [m for m in NUM_RE.finditer(flat) if m.group(2) and not re.fullmatch(r"20\d\d", m.group(1))]
    if len(found) != 1:
        return None
    m = found[0]
    before, after = flat[:m.start()].strip(), flat[m.end():].strip()
    return (before, m.group(0).strip(), after) if re.search(r"[가-힣]", before + after) else None


def template_fit(md: str) -> dict:
    """틀마다 맞지 않는 이유. 빈 문자열이면 맞는다."""
    main = copy_of(md)[0]
    cards = thumb_cards(md)
    problems = card_copy_issues(cards) if cards else ["`- 썸네일 카드:`가 없다"]
    return {"compare": f"카드가 맞지 않는다: {problems[0]}" if cards and problems else (problems[0] if problems else ""),
            "number": "" if number_parts(main) else "메인에 숫자 하나와 기준 대상 낱말이 없다",
            "headline": ""}


PHOTO_TEMPLATES = ("photo_question", "photo_compare")     # 시즌 글 전용(2026-11-09 노션 계획). 돼지 없이 실사 사진 + 코드 카드
PHOTOS = ROOT / "assets" / "photos"
PHOTO_LEDGER = PHOTOS / "_licenses.csv"
PHOTO_COLS = ["file", "sha256", "source_url", "creator", "provider", "license", "license_url", "checked_at",
              "commercial_ok", "edit_ok", "attribution", "crop_note", "use", "prompt"]
AI_PROVIDER = "AI"      # 2026-11-09 사용자가 AI 생성 배경을 정식 출처로 허용했다. 숨기지 않고 표시한다
AI_DISCLOSE_RE = re.compile(r"AI(?:로 만든| 활용| 생성)")


def track_of(md: str) -> str:
    """`- 콘텐츠 트랙:` core | seasonal. 메모가 없는 기존 원고는 core다."""
    return (memo_value(md, "콘텐츠 트랙") or "core").strip()


def photo_status(md: str, text: str, ledger: Path = None) -> tuple:
    """시즌 대표사진 → (차단 목록, 사진 경로). 검색 결과에 보인다는 것은 이용 허락이 아니라서 원장 기록이 있어야 쓴다."""
    import csv
    rel = (memo_value(md, "썸네일 사진") or "").strip()
    if not rel:
        return ["PHOTO_REQUIRED — `- 썸네일 사진: assets/photos/파일`이 없다. suggest_cover.py 후보에서 골라 사용자가 내려받는다"], None
    path = ROOT / rel
    if not path.exists():
        return [f"PHOTO_REQUIRED — 사진 파일이 없다: {rel}"], None
    ledger = ledger or PHOTO_LEDGER
    rows = list(csv.DictReader(open(ledger, encoding="utf-8-sig", newline=""))) if ledger.exists() else []
    row = next((r for r in rows if r.get("file") == path.name), None)
    if not row:
        return [f"BLOCKED_PHOTO_LICENSE — 라이선스 원장({ledger.name})에 {path.name}이 없다"], path
    blocks = [f"BLOCKED_PHOTO_LICENSE — {path.name}: {k}가 Y가 아니다" for k in ("commercial_ok", "edit_ok") if row.get(k) != "Y"]
    if row.get("provider") == AI_PROVIDER:     # AI 배경: 출처 URL 대신 모델·생성일·프롬프트, 상황 설명용 표시, 본문 공개
        blocks += [f"BLOCKED_PHOTO_LICENSE — {path.name}(AI 생성): {k}가 비어 있다" for k in ("creator", "checked_at", "prompt") if not row.get(k)]
        if "AI" not in row.get("use", ""):
            blocks.append(f"BLOCKED_PHOTO_LICENSE — {path.name}: use에 'AI 생성 배경(상황 설명용)'이라고 적는다")
        if not AI_DISCLOSE_RE.search(text):
            blocks.append("BLOCKED_PHOTO_LICENSE — AI로 만든 대표사진인데 본문에 AI 활용 표시가 없다(예: 대표 이미지는 AI로 만든 배경입니다)")
    else:
        blocks += [f"BLOCKED_PHOTO_LICENSE — {path.name}: {k}가 비어 있다" for k in ("source_url", "license", "checked_at") if not row.get(k)]
    if row.get("sha256") != _sha(path):
        blocks.append(f"BLOCKED_PHOTO_LICENSE — {path.name}이 원장에 기록한 파일과 다르다(해시 불일치)")
    if row.get("attribution") and _plain(row["attribution"]) not in _plain(text):
        blocks.append(f"BLOCKED_PHOTO_LICENSE — 출처 표기 의무가 있는데 본문에 없다: {row['attribution']}")
    return blocks, path


def select_template(md: str, recent=()) -> tuple:
    """→ (요청한 틀, 실제 틀, 이유). 지정한 틀이 맞으면 그대로, 안 맞으면 headline으로 바꾸고 이유를 남긴다.
    지정이 없으면 맞는 틀 중에서 고르고, 맞는 틀이 둘 이상일 때만 최근 글의 틀을 피한다."""
    kind = memo_value(md, "썸네일 유형") or ""
    fit = template_fit(md)
    if track_of(md) == "seasonal":     # 시즌 글은 돼지 틀로 대체하지 않는다
        if kind == "photo_compare" and fit["compare"]:
            return kind, "photo_question", fit["compare"]
        if kind in PHOTO_TEMPLATES:
            return kind, kind, ""
        return kind, "photo_question" if fit["compare"] else "photo_compare", "자동: 시즌 글은 사진 틀"
    if kind == "scene":
        return kind, "headline", "scene은 현재 운영에서 비활성화했다"
    if kind in fit:
        return (kind, kind, "") if not fit[kind] else (kind, "headline", fit[kind])
    lines = copy_of(md)[0].count("/") + 1
    ready = [t for t in ("compare", "number", "headline") if not fit[t] and lines <= MAX_LINES[operating_layout(t)]]
    pick = next((t for t in ready if t not in recent), ready[0]) if len(ready) > 1 else ready[0]
    why = f"자동: 맞는 틀 {', '.join(ready)}" + (f", 최근 {AVOID_RECENT}편의 {ready[0]}를 피했다" if pick != ready[0] else "")
    return kind, pick, why if len(ready) > 1 else f"자동: {fit['compare']}"


def review_copy(md: str, text: str) -> tuple:
    """→ (차단, 경고). 차단은 숫자·단위·조건·역할 불일치와 근거 문장 불일치, 입력 오류만이다."""
    blocks, warns = [], []
    title = re.search(r"^제목: (.+)$", md, re.M).group(1).strip()
    main, sub, badge = copy_of(md)
    if not main:
        return ["작성 메모 `- 썸네일 문구: 메인 | 서브`가 없다"], []
    squeeze = lambda s: re.sub(r"[\s|｜:/]", "", s)
    m_, s_, b_ = squeeze(main), squeeze(sub), squeeze(badge)
    from pipeline import contain
    if contain(m_ + s_, squeeze(title)) >= 0.8:     # 글자 수로 재면 25자 제목에서 짧은 카피까지 복사로 잡혔다
        blocks.append("REJECT_TITLE_COPY_AS_THUMBNAIL — SEO 제목을 그대로 넣었다")
    if len(m_) > MAX_MAIN:
        blocks.append(f"메인 카피 {len(m_)}자 ({MAX_MAIN}자 이내) — 문구를 줄인다")
    if len(s_) > MAX_SUB:
        blocks.append(f"서브 카피 {len(s_)}자 (한 줄 {MAX_SUB}자 이내) — 문구를 줄이거나 생략한다")
    if len(b_) > MAX_BADGE:
        blocks.append(f"하단 배지 {len(b_)}자 ({MAX_BADGE}자 이내) — 문구를 줄이거나 생략한다")
    template = select_template(md)[1]
    lay = operating_layout(template) or LAYOUT.get(template, template)
    limit = MAX_LINES[lay]
    if main.count("/") + 1 > limit:
        blocks.append(f"메인 카피는 {lay}에서 {limit}줄까지다")
    if track_of(md) == "seasonal" and any(memo_value(md, k) for k in ("돼지 자세", "돼지 주제", "썸네일 소품")):
        blocks.append("시즌 글 대표사진에는 돼지·소품을 쓰지 않는다 — `- 돼지 자세:`·`- 돼지 주제:`·`- 썸네일 소품:`을 지운다")
    if track_of(md) != "seasonal" and (memo_value(md, "썸네일 유형") or "") in PHOTO_TEMPLATES:
        blocks.append("photo 틀은 시즌 글(`- 콘텐츠 트랙: seasonal`)에만 쓴다")
    phrase = (memo_value(md, "썸네일 강조 구절") or "").strip()
    if phrase and not any(phrase in x.strip() for x in main.split("/")):
        blocks.append(f"`- 썸네일 강조 구절:`이 메인 한 줄 안에 그대로 없다: {phrase}")
    if template == "headline" and operating_layout(template) == "headline_v2" and not phrase:
        warns.append("headline에 `- 썸네일 강조 구절:`이 없다 — 강조 없이 그린다")
    if not SPECIFIC_RE.search(main + sub + badge):
        blocks.append("카피에 숫자·대상·조건·선택 문제가 하나도 없다")
    if m := BANNED_RE.search(main + sub + badge):
        blocks.append(f"금지 표현: {m.group(0)}")
    cards = thumb_cards(md)
    card_bodies = [c for c in cards[1:4:2] if c]
    warns += repeat_copy_issues(main, [sub, badge, *[c for c in card_bodies if not card_amount(c)]])
    warns += claim_issues([badge, *[c.replace("/", " ") for c in card_bodies]], text)
    if len(cards) == 5 and cards[4] == "+":
        if not can_add(cards):
            warns.append("더하기를 뺐다 — 단위가 같은 두 금액이 아니다")
        else:
            total = sum(float(card_amount(c)[0].replace(",", "")) for c in cards[1:4:2])
            known = {float(n.replace(",", "")) for r in facts(md) for n, _ in _number_units(r[1])}
            if total not in known:
                warns.append(f"두 금액의 합 {total:g}이 수치 근거 표에 없다 — 합산이 맞는지 본다")
    if len([x for x in (memo_value(md, "썸네일 후보") or "").split("|") if x.strip()]) < MIN_CANDIDATES:
        warns.append(f"`- 썸네일 후보:`에 메인 카피 후보 {MIN_CANDIDATES}개가 없다")
    if not memo_value(md, "썸네일 선택 이유"):
        warns.append("`- 썸네일 선택 이유:`가 없다")
    if memo_value(md, "카테고리 색") not in CATEGORY_COLORS:
        blocks.append(f"`- 카테고리 색:`이 {' · '.join(CATEGORY_COLORS)} 중 하나가 아니다")
    pose, topic = memo_value(md, "돼지 자세"), memo_value(md, "돼지 주제")
    if pose and pose not in MASCOT_POSES:
        blocks.append(f"`- 돼지 자세:`가 {' · '.join(MASCOT_POSES)} 중 하나가 아니다")
    if topic and topic not in POSE_BY_TOPIC:
        blocks.append(f"`- 돼지 주제:`가 {' · '.join(POSE_BY_TOPIC)} 중 하나가 아니다")
    prop = memo_value(md, "썸네일 소품")
    if prop and prop not in PROP_FILES:
        blocks.append(f"`- 썸네일 소품:`이 {' · '.join(PROP_FILES)} 중 하나가 아니다")
    plain = _plain(text)
    blocks += [f"BLOCKED_THUMBNAIL_CLAIM — `- 썸네일 근거:` 문장이 본문에 없다: {q}" for q in evidence_quotes(md) if _plain(q) not in plain]
    return blocks + number_issues(md, text) + role_issues(md), warns


def copy_issues(md: str, text: str) -> list:
    """차단만. check_naver가 부른다."""
    return review_copy(md, text)[0]


def manual_reasons(md: str, template: str) -> list:
    """사람이 봐야 하는 이유. 안정화된 틀과 근거 문장이 있는 글은 기다리게 하지 않는다."""
    main, sub, _ = copy_of(md)
    out = []
    if LAYOUT.get(template, template) not in APPROVED_LAYOUTS:
        op = operating_layout(template)
        out.append(f"새 판 {LAYOUT.get(template, template)}: 미리보기 승인 전이다 — "
                   + (f"운영 대표사진은 {op}로 만들었다" if op else "운영 대표사진은 만들지 않았다"))
    if "?" in main + sub and not evidence_quotes(md):
        out.append("질문의 답이 본문 어디인지 `- 썸네일 근거:`가 없어 미검증이다")
    return out


def number_evidence(md: str, text: str) -> list:
    """대표사진 숫자의 근거 위치 → `숫자: 근거 표 항목 / 본문 N행`."""
    main, sub, badge = copy_of(md)
    focus = (memo_value(md, "썸네일 강조 숫자") or "").split("|")[0]
    copy = " ".join((main, sub, badge, focus, *[c.replace("/", " ") for c in thumb_cards(md)]))
    rows = [r for r in facts(md) if r[4] in ("VERIFIED", "계산")]
    lines = md.split("\n")
    out = []
    for n, u in sorted(_number_units(copy)):
        row = next((r[0] for r in rows if n in {x for x, _ in _number_units(r[1])}), "없음")
        at = next((i + 1 for i, ln in enumerate(lines) if n in {x for x, _ in _number_units(ln)} and "## 작성 메모" not in ln), 0)
        out.append(f"{n}{u}: {row} / 본문 {at}행")
    return out


def operating_layout(template: str) -> str:
    """운영 대표사진에 쓰는 판. 지금 판이 승인 전이면 승인된 headline_v2. 사진 틀은 돼지 판으로 대체하지 않아 빈 문자열."""
    layout = LAYOUT.get(template, template)
    if layout in APPROVED_LAYOUTS:
        return layout
    return "" if layout in PHOTO_TEMPLATES else "headline_v2"


def recent_templates(num: str, count: int = AVOID_RECENT) -> list:
    return recent_poses(num, count, "actual_template")


def template_for(intent: str) -> str:
    return TEMPLATE_BY_INTENT.get(intent, "number")


def asset_path(name: str, master_dir: Path = None) -> Path:
    if name.startswith("prop_"):
        return (master_dir or PROPS) / f"{name[5:]}.png"
    return (master_dir or MASTER_DIR) / f"pig_{name}.png"


def asset_info(name: str, master_dir: Path = None) -> dict:
    reg = (master_dir or MASTER_DIR) / "registry.json"
    return json.loads(reg.read_text(encoding="utf-8")).get(name, {}) if reg.exists() else {}


def mascot_status(pose: str, master_dir: Path = None) -> tuple:
    """→ (상태, 파일). OK · MISSING_MASTER_MASCOT · BLOCKED_MASCOT_INCONSISTENCY. 등록부의 승인 해시와 같아야 쓴다."""
    png = asset_path(pose, master_dir)
    info = asset_info(pose, master_dir)
    if not png.exists() or not info:
        return "MISSING_MASTER_MASCOT", None
    if hashlib.sha256(png.read_bytes()).hexdigest() != info["hash"] or info.get("status") != "approved":
        return "BLOCKED_MASCOT_INCONSISTENCY", None
    return "OK", png


def recent_poses(num: str, count: int = AVOID_RECENT, field: str = "mascot_pose") -> list:
    """manifest에 남은 이전 글의 값(기본은 자세), 최근 것부터."""
    out = []
    for n in range(int(num) - 1, int(num) - 1 - count, -1):
        p = MANIFESTS / f"{n}.yaml"
        m = re.search(rf'^{field}: "(.*)"', p.read_text(encoding="utf-8"), re.M) if p.exists() else None
        if m and m.group(1):
            out.append(m.group(1))
    return out


def choose_pose(md: str, recent=(), master_dir: Path = None) -> tuple:
    """→ (자세, 상태, 파일, 이유). 지정 → 주제에 맞는 자세 → 있는 파일 → 반복 회피 순이다.
    반복은 동등하게 맞는 자세가 있을 때만 피한다. 멈추는 경우는 face까지 없거나 파일이 승인 없이 바뀌었을 때뿐이다."""
    forced = memo_value(md, "돼지 자세")
    topic = memo_value(md, "돼지 주제") or TOPIC_BY_TYPE.get(memo_value(md, "글 유형"), "general")
    options = (forced,) if forced else POSE_BY_TOPIC[topic]
    why = "작성 메모 지정" if forced else f"주제 {topic}"
    state = {p: mascot_status(p, master_dir) for p in options}
    if state[options[0]][0] == "BLOCKED_MASCOT_INCONSISTENCY":
        return options[0], *state[options[0]], why
    ready = [p for p in options if state[p][0] == "OK"]
    if not ready:
        return "face", *mascot_status("face", master_dir), f"{why}, pig_{options[0]}.png가 없어 face로 대체"
    pick = next((p for p in ready if p not in recent), ready[0])
    if pick != options[0]:
        why += f", 최근 {AVOID_RECENT}편에 {options[0]}가 있어 동등한 {pick} 선택"
    elif pick in recent:
        why += f", 최근 {AVOID_RECENT}편과 같지만 주제에 맞아 그대로 쓴다"
    return pick, *state[pick], why


def spec_issues(png: Path) -> list:
    """받은 자세 파일의 규격."""
    from PIL import Image
    im = Image.open(png)
    if im.size != (POSE_SIZE, POSE_SIZE):
        return [f"크기 {im.size} ({POSE_SIZE}×{POSE_SIZE})"]
    alpha = im.convert("RGBA").getchannel("A")
    box = alpha.point(lambda v: 255 if v >= 128 else 0).getbbox()
    if not box or alpha.getpixel((0, 0)) or alpha.getpixel((POSE_SIZE - 1, POSE_SIZE - 1)):
        return ["투명 배경이 아니다"]
    if box[0] == 0 or box[1] == 0 or box[2] == POSE_SIZE or box[3] == POSE_SIZE:
        return ["캐릭터가 캔버스 끝에서 잘렸다"]
    height = (box[3] - box[1]) / POSE_SIZE
    return [] if POSE_HEIGHT[0] <= height <= POSE_HEIGHT[1] else [f"캐릭터 높이 {height:.0%} (약 75%)"]


def import_pose(src: Path, out: Path) -> Path:
    """후보 PNG → 캐릭터만 잘라 키를 맞추고 POSE_TOP~POSE_BOTTOM에 세운 1600 캔버스."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    im = im.crop(im.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox())
    h = POSE_BOTTOM - POSE_TOP
    w = round(im.width * h / im.height)
    assert w < POSE_SIZE, f"{src}: 캐릭터가 너무 넓다({w}px)"
    canvas = Image.new("RGBA", (POSE_SIZE, POSE_SIZE), (0, 0, 0, 0))
    canvas.paste(im.resize((w, h), Image.LANCZOS), ((POSE_SIZE - w) // 2, POSE_TOP))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def save_previews(png: Path) -> list:
    """160·320px 축소본. 매 글 만들고, 사람은 새 틀·이상 발생·5편마다 표본으로 본다."""
    from PIL import Image
    d = ROOT / "_workspace" / "naver"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for size in QC_PREVIEWS:
        out.append(d / f"{png.stem}_{size}.png")
        Image.open(png).convert("RGB").resize((size, size), Image.LANCZOS).save(out[-1])
    return out


def card_mascot(pose: str, full: Path, master_dir: Path = None) -> tuple:
    """비교 카드는 상반신을 먼저 쓴다. 없으면 전신. 등록 뒤 바뀐 상반신은 막는다 → (상태, 파일)."""
    status, bust = mascot_status(f"bust_{pose}", master_dir)
    return ("OK", full) if status == "MISSING_MASTER_MASCOT" else (status, bust)


def bust_issues(png: Path) -> list:
    """상반신은 아래가 잘린 그림이라 크기·높이 규격 대신 위쪽 투명만 본다."""
    from PIL import Image
    alpha = Image.open(png).convert("RGBA").getchannel("A")
    return ["투명 배경이 아니다"] if alpha.getpixel((0, 0)) or alpha.getpixel((alpha.width - 1, 0)) else []


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write_registry(reg: dict):
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def register_mascots() -> int:
    """사용자가 프로필과 같은지 눈으로 본 새 파일만 넣고 실행한다. 등록된 파일이 바뀌었으면 건드리지 않는다 — 여기서 덮으면 바꿔치기가 통과한다."""
    import datetime
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}
    added = []
    for pose in (*MASCOT_POSES, *[f"bust_{x}" for x in MASCOT_POSES]):
        p = MASTER_DIR / f"pig_{pose}.png"
        if not p.exists():
            continue
        if pose in reg:
            if _sha(p) != reg[pose]["hash"]:
                print(f"{p.name}: 승인 뒤 바뀌었다 — 사용자가 `--approve-asset {pose}`로 승인해야 쓴다")
            continue
        bad = bust_issues(p) if pose.startswith("bust_") else spec_issues(p)
        if bad:
            print(f"{p.name}: {bad[0]} — 등록하지 않았다")
            continue
        reg[pose] = {"hash": _sha(p), "version": 1, "approved_at": datetime.date.today().isoformat(), "status": "approved"}
        added.append(pose)
    _write_registry(reg)
    print(f"새로 등록 {len(added)}개: {', '.join(added) or '-'} / 전체 {len(reg)}개")
    return 0 if reg else 1


def next_version(info: dict, sha: str, today: str) -> dict:
    return {"hash": sha, "version": info.get("version", 0) + 1, "approved_at": today, "status": "approved"}


def confirm_typed(name: str, read=input) -> bool:
    """isatty만 보면 Windows에서 NUL 입력이 터미널로 통과한다(2026-11-01 실제로 통과했다). 이름을 직접 입력받는다."""
    if not sys.stdin.isatty():
        return False
    try:
        return read(f"{name}의 새 파일을 눈으로 확인했으면 이름을 입력: ").strip() == name
    except EOFError:
        return False


def approve_asset(name: str) -> int:
    """바뀐 자산을 새 버전으로 승인한다. 사용자가 터미널에서 직접 입력한다."""
    import datetime
    if not confirm_typed(name):
        print("승인은 사용자가 터미널에서 직접 입력한다")
        return 1
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reg[name] = next_version(reg.get(name, {}), _sha(asset_path(name)), datetime.date.today().isoformat())
    _write_registry(reg)
    print(f"{name} v{reg[name]['version']} 승인")
    return 0


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


def mobile_qc(main_px: float, sub_px: float, ratio: float, mascot_rect: dict = None,
              text_rects: list = (), color: str = "#000000") -> dict:
    """렌더 값 → {fail: [...], drop_sub}."""
    scale = QC_SIZE / THUMB
    fail = []
    if main_px * scale < MAIN_MIN_QC:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 메인 카피가 {QC_SIZE}px에서 {main_px * scale:.0f}px")
    if ratio > MASCOT_RATIO[1]:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 돼지가 {ratio:.0%} ({MASCOT_RATIO[1]:.0%} 이하)")
    if badge_zone_hit(mascot_rect) or any(badge_zone_hit(r) for r in text_rects):
        fail.append("BLOCKED_MOBILE_READABILITY — 오른쪽 아래 내부 AI 표시 안전영역과 겹친다")
    if contrast(color, CREAM) < 4.5:
        fail.append(f"BLOCKED_MOBILE_READABILITY — 글자색 대비 {contrast(color, CREAM):.1f} (4.5 이상)")
    return {"fail": fail, "drop_sub": bool(sub_px) and sub_px * scale < SUB_MIN_QC}


def write_manifest(num: str, md: str, status: str, mascot: Path, ratio: float, passed: bool, original: Path, preview: Path,
                   pose: str = "", pose_reason: str = "", renderer: str = "code", template: str = "", extra: dict = None) -> Path:
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
        "main_copy": main, "sub_copy": sub, "bottom_badge": badge, "copy_candidates": [x.strip() for x in (memo_value(md, "썸네일 후보") or "").split("|") if x.strip()], "selection_reason": memo_value(md, "썸네일 선택 이유") or "",
        "verified_number": ", ".join(numbers), "verified_rows": " / ".join(r[0] for r in rows if set(numbers) & {x for x, _ in _number_units(r[1])}),
        "verified_source_url": src[0] if src else "", "verified_at": (memo_value(md, "최신성 재확인") or "").split("|")[0].strip(),
        "category": memo_value(md, "카테고리 색") or "", "color_code": COLOR_CODE.get(memo_value(md, "카테고리 색"), ""),
        "mascot_asset": str(mascot.name) if mascot else "", "mascot_pose": pose, "mascot_pose_reason": pose_reason, "renderer": renderer, "template_id": template, "card_copy": " | ".join(thumb_cards(md)),
        "mascot_area_ratio": round(ratio, 3), "mascot_position": "lower_right_safe" if mascot else "none", "ai_mark_safe_zone_clear": passed,
        "auto_qc_passed": passed, "auto_fact_checks_passed": not number_issues(md, parts_text(md)), "number_evidence": number_evidence(md, parts_text(md)),
        "output_original": original.name, "output_mobile_preview": preview.name,
        **(extra or {}),
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
    text = "총급여 5,500만원 이하와 초과로 갈립니다. 연금저축 600만원과 IRP 300만원, 합산 900만원 한도를 나누는 법. 148.5만원, 118.8만원, 135만원, 2개월입니다. 한도를 넘긴 돈은 공제 밖, 남은 금액은 IRP로."

    def doc(main="600 + 300만원", sub="연금저축·IRP 나누기", badge="합산 900만원 한도", extra=""):
        return (f"제목: 2026 IRP 세액공제 계산｜연금저축과 나눠 납입하는 방법\n\n{text}\n\n## 작성 메모\n\n"
                f"- 썸네일 유형: compare\n- 썸네일 문구: {main} | {sub}\n- 썸네일 배지: {badge}\n- 썸네일 후보: a | b | c\n- 썸네일 선택 이유: 사유\n"
                f"- 카테고리 색: pension\n- 돼지 자세: calculator\n{extra}\n{facts_tbl}")

    assert copy_issues(doc(), text) == [], copy_issues(doc(), text)
    assert copy_issues(doc("148.5만 vs 118.8만", "총급여별 IRP 공제", "연금저축 600 + IRP 300"), text) == []

    # TEST-THUMB-IRP-001: 국세 값은 `국세 기준`을 표시하면 허용, 숫자 없는 글도 대상·질문이 있으면 허용
    assert any("국세만" in i for i in copy_issues(doc("135만원", "IRP 공제 계산", "나누는 법"), text))
    assert copy_issues(doc("135만원", "국세 기준", "나누는 법"), text) == []
    assert copy_issues(doc("연금 안내", "맞벌이 누가 받을까?", ""), text) == [], "숫자 필수 조건은 없앴다"
    assert any("하나도 없다" in i for i in copy_issues(doc("연금 안내", "잘 알아보기", ""), text))
    # TEST-THUMB-COPY-005: 동의어는 경고, 숫자·단위·역할 오류는 차단. 반복은 물음표로 가르지 않는다
    card = "- 썸네일 카드: 연금저축 | 600만원 | IRP | 300만원 | +"
    ok = doc("연금저축 600, / IRP 300", "꼭 이렇게 나눠야 할까", "나누는 법과 한도 정리", card)
    assert review_copy(ok, text) == ([], []), review_copy(ok, text)
    assert card_amount("1,000만원") == ("1,000", "만원") and card_amount("공제 밖") is None
    assert can_add(thumb_cards(ok)) and not can_add(["a", "600만원", "b", "2년", "+"]) and not can_add(["a", "600만원", "b", "300만원"])
    blocks, warns = review_copy(doc("연금저축 600, / IRP 300?", "꼭 이렇게 나눠야 할까", "납입 순서와 한도 정리"), text)
    assert blocks == [] and any("WARN_THUMBNAIL_WORDING" in w and "순서" in w for w in warns), "동의어는 경고만"
    blocks, warns = review_copy(doc("연금저축 600, / IRP 300?", "꼭 이렇게 나눠야 할까", "IRP 300 한도"), text)
    assert blocks == [] and any("다시 적었다" in w for w in warns), "단순 반복은 경고만"
    assert trim_copy("합산 900만원", "합산 900만원", "합산 900만원") == ("합산 900만원", "", "")
    assert any("2줄" in i for i in copy_issues(doc("600 / 300 / 900", extra=card), text)), "compare는 2줄까지"
    for bad in ("전부", "누구나", "모르면 손해", "무조건"):
        assert any("금지" in i for i in copy_issues(doc(f"{bad} 900만원"), text)), bad
    assert any("`최대`" in i for i in copy_issues(doc("최대 148.5만원", "IRP·연금저축 세액공제", "연 900만원 한도"), text))
    assert copy_issues(doc("최대 148.5만원", "총급여 5,500만원 이하", "연 900만원 한도"), text) == []
    one_tier = text.replace("이하와 초과로 갈립니다", "이하만 받습니다")
    assert not any("`최대`" in i for i in number_issues(doc("최대 148.5만원", "IRP·연금저축 세액공제", "연 900만원 한도"), one_tier)), "구간이 하나면 막지 않는다. `초과` 판정이 항상 참이었다"
    # 숫자·단위·역할 — 2년과 2개월, 근거 없는 숫자, 한도를 공제액처럼, 환급액 단정
    assert any("단위" in i for i in copy_issues(doc("기한 2년 확인"), text))
    assert any("BLOCKED_UNVERIFIED_NUMBER" in i for i in copy_issues(doc("200만원 계산"), text))
    assert any("세액공제액이 아니다" in i for i in copy_issues(doc("세액공제 900만원"), text))
    assert copy_issues(doc("세액공제 148.5만원", "총급여 5,500만원 이하", ""), text) == []
    assert any("환급액이 아니다" in i for i in copy_issues(doc("환급 148.5만원", "총급여 5,500만원 이하", ""), text))
    assert any("REJECT_TITLE_COPY" in i for i in copy_issues(doc("2026 IRP 세액공제 계산", "연금저축과 나눠 납입하는 방법"), text))
    assert any("문구를 줄인다" in i for i in copy_issues(doc("연금저축과 개인형 퇴직연금의 세액공제 900만원"), text)), "긴 문구는 이유를 말하고 멈춘다"
    assert any("후보" in w for w in review_copy(doc().replace("- 썸네일 후보: a | b | c\n", ""), text)[1])
    assert copy_issues(doc().replace("- 돼지 자세: calculator\n", ""), text) == [], "자세는 생략할 수 있다"
    assert any("돼지 자세" in i for i in copy_issues(doc().replace("자세: calculator", "자세: explain"), text))
    assert any("돼지 주제" in i for i in copy_issues(doc(extra="- 돼지 주제: 세금"), text))
    # 근거 문장 — 본문에 있어야 하고, 질문에 근거가 없으면 사람이 본다
    assert copy_issues(doc(extra="- 썸네일 근거: 합산 900만원 한도를 나누는 법"), text) == []
    assert any("근거" in i for i in copy_issues(doc(extra="- 썸네일 근거: 본문에 없는 문장"), text))
    assert manual_reasons(doc("600 / 300?", "고민"), "compare") and not manual_reasons(doc(), "compare")
    assert not manual_reasons(doc("600 / 300?", "고민", extra="- 썸네일 근거: 합산"), "compare") and manual_reasons(doc(), "새틀")
    assert not manual_reasons(doc(), "headline") and not manual_reasons(doc(), "number")
    assert operating_layout("새틀") == "headline_v2" and any("headline_v2로" in x for x in manual_reasons(doc(), "새틀")), "승인 전 판은 사람이 보고, 운영은 headline_v2로 만든다"
    # TEST-THUMB-TEMPLATE-006: 금액 배분 → compare, 신청·조회 → headline, 카드 누락 → headline 대체
    assert select_template(ok)[1:] == ("compare", "")
    assert select_template(doc(extra="- 썸네일 유형: x").replace("- 썸네일 유형: compare", "- 썸네일 유형: headline").replace("- 썸네일 유형: x\n", ""))[:2] == ("headline", "headline")
    got = select_template(doc().replace("- 썸네일 유형: compare", "- 썸네일 유형: action"))
    assert got[:2] == ("action", "headline") and "없다" in got[2], "신청·조회 글은 카드 없이 headline"
    got = select_template(ok.replace(card, "- 썸네일 카드: 연금저축 | IRP"))
    assert got[1] == "headline" and "맞지 않는다" in got[2], "카드 필드 누락은 조용히 넘어가지 않고 이유를 남긴다"
    assert select_template(ok.replace("600만원", "개인형 퇴직연금과 연금저축 합산"))[1] == "headline", "카드가 과밀하면 headline"
    assert select_template(doc().replace("- 썸네일 유형: compare", "- 썸네일 유형: scene"))[1:] == ("headline", "scene은 현재 운영에서 비활성화했다")
    # TEST-THUMB-FORMAT-007: number는 숫자 하나와 기준 대상이 있어야 한다. 자동 선택은 맞는 틀이 둘 이상일 때만 반복을 피한다
    num_doc = lambda main, kind="number": doc(main, "나는 넘겼을까?", "").replace("- 썸네일 유형: compare", f"- 썸네일 유형: {kind}")
    assert number_parts("총급여의 25%") == ("총급여의", "25%", "") and number_parts("25%") is None and number_parts("600만원 / 300만원") is None
    assert select_template(num_doc("합산 900만원"))[1:] == ("number", "")
    got = select_template(num_doc("900만원"))
    assert got[1] == "headline" and "기준 대상" in got[2], "숫자만 크게 쓰면 공제율처럼 읽혀 headline으로 바꾼다"
    auto = ok.replace("- 썸네일 유형: compare\n", "")
    assert select_template(auto)[1] == "compare" and select_template(auto, ("compare",))[1] == "headline", "compare·headline이 다 맞으면 최근 틀을 피한다"
    assert select_template(num_doc("연금 안내", "x").replace("- 썸네일 유형: x\n", ""), ("headline",))[1] == "headline", "맞는 틀이 하나면 반복해도 그대로"
    assert select_template(ok, ("compare", "compare", "compare"))[1] == "compare", "지정한 틀은 반복이어도 쓴다"
    # 줄 수는 판마다. 질문형만 3줄
    three = "따로 사는 / 부모님도 / 공제될까?"
    hl = lambda extra="": doc(three, "나이·소득 조건 확인", "", extra).replace("- 썸네일 유형: compare", "- 썸네일 유형: headline")
    assert any("compare에서 2줄" in i for i in copy_issues(doc(three, "", "", card), text))
    assert not any("줄까지" in i for i in copy_issues(hl(), text)), "질문형은 3줄"
    assert any("강조 구절" in w for w in review_copy(hl(), text)[1])
    assert not any("강조 구절" in w for w in review_copy(hl("- 썸네일 강조 구절: 공제될까?"), text)[1])
    assert any("강조 구절" in i for i in copy_issues(hl("- 썸네일 강조 구절: 부모님도 공제"), text)), "줄을 넘는 구절은 막는다"

    # 시즌 트랙 — 사진 틀, 돼지 금지, 라이선스 원장 (2026-11-09 노션 계획)
    sea = lambda extra="": doc("외출모드 / 켜둘까?", "난방비 설정 체크", "", "- 콘텐츠 트랙: seasonal\n" + extra).replace("- 돼지 자세: calculator\n", "")
    assert track_of(doc()) == "core" and track_of(sea()) == "seasonal", "트랙 메모가 없으면 core"
    assert select_template(sea())[1] == "photo_question" and select_template(sea(card))[1] == "photo_compare", "시즌 글은 돼지 틀로 가지 않는다"
    assert operating_layout("photo_question") == "photo_question" and not any("새 판" in r for r in manual_reasons(sea(), "photo_question")), "사진 두 틀은 2026-11-09 승인"
    global APPROVED_LAYOUTS
    keep_layouts, APPROVED_LAYOUTS = APPROVED_LAYOUTS, APPROVED_LAYOUTS - {"photo_question"}
    try:
        assert operating_layout("photo_question") == "" and any("만들지 않았다" in x for x in manual_reasons(sea(), "photo_question")), "승인 전 사진 틀은 돼지 판으로 대체하지 않는다"
    finally:
        APPROVED_LAYOUTS = keep_layouts
    assert any("돼지" in i for i in copy_issues(sea("- 돼지 주제: warning"), text)), "시즌 글에 돼지 메모는 차단"
    assert any("시즌 글" in i for i in copy_issues(doc().replace("- 썸네일 유형: compare", "- 썸네일 유형: photo_question"), text)), "core에 사진 틀은 차단"
    with tempfile.TemporaryDirectory() as d:
        import csv as _csv
        from PIL import Image
        global ROOT
        keep_root, ROOT = ROOT, Path(d)
        try:
            (ROOT / "assets" / "photos").mkdir(parents=True)
            led = ROOT / "assets" / "photos" / "_licenses.csv"
            assert "PHOTO_REQUIRED" in photo_status(sea(), text, led)[0][0], "사진이 없으면 확보 요청으로 멈춘다"
            ph = "- 썸네일 사진: assets/photos/heat.jpg\n"
            Image.new("RGB", (20, 20), "white").save(ROOT / "assets" / "photos" / "heat.jpg")
            assert "원장" in photo_status(sea(ph), text, led)[0][0], "원장에 없으면 차단"
            row = {c: "" for c in PHOTO_COLS}
            row.update(file="heat.jpg", sha256=_sha(ROOT / "assets" / "photos" / "heat.jpg"), source_url="https://www.pexels.com/photo/1",
                       license="Pexels License", checked_at="2026-11-09", commercial_ok="Y", edit_ok="Y")
            def save(r):
                with open(led, "w", encoding="utf-8-sig", newline="") as f:
                    w = _csv.DictWriter(f, PHOTO_COLS)
                    w.writeheader()
                    w.writerow(r)
            save(row)
            assert photo_status(sea(ph), text, led)[0] == [], "원장·해시·허용이 맞으면 통과"
            save({**row, "commercial_ok": "N"})
            assert any("commercial_ok" in b for b in photo_status(sea(ph), text, led)[0])
            save({**row, "attribution": "Photo by Kim"})
            assert any("출처 표기" in b for b in photo_status(sea(ph), text, led)[0])
            ai = {**row, "source_url": "", "license": "AI 생성", "provider": "AI", "creator": "gpt-image-2.5-flare",
                  "use": "AI 생성 배경(상황 설명용)", "prompt": "thermostat, no text"}
            save(ai)
            assert any("AI 활용 표시" in b for b in photo_status(sea(ph), text, led)[0]), "AI 배경은 본문에 공개해야 한다"
            assert photo_status(sea(ph), text + " 대표 이미지는 AI로 만든 배경입니다.", led)[0] == [], "AI 행은 출처 URL 없이 모델·프롬프트로 통과"
            save({**ai, "prompt": ""})
            assert any("prompt" in b for b in photo_status(sea(ph), text + " AI 활용", led)[0])
            save(row)
            Image.new("RGB", (21, 21), "white").save(ROOT / "assets" / "photos" / "heat.jpg")
            assert any("해시" in b for b in photo_status(sea(ph), text, led)[0]), "원장 기록 뒤 바뀐 파일은 차단"
        finally:
            ROOT = keep_root

    # TEST-THUMB-MASCOT-002: 등록 안 된 돼지·승인 없이 바뀐 파일은 쓰지 않는다. 승인한 새 버전은 쓴다
    from PIL import Image
    entry = lambda p: {"hash": _sha(p), "version": 1, "approved_at": "2026-11-01", "status": "approved"}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        assert mascot_status("calculator", d)[0] == "MISSING_MASTER_MASCOT"
        Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(d / "pig_calculator.png")
        assert mascot_status("calculator", d)[0] == "MISSING_MASTER_MASCOT"
        (d / "registry.json").write_text(json.dumps({"calculator": entry(d / "pig_calculator.png")}), encoding="utf-8")
        assert mascot_status("calculator", d)[0] == "OK"
        Image.new("RGBA", (11, 11), (255, 0, 0, 0)).save(d / "pig_calculator.png")     # 처진 귀·목도리 돼지로 바꿔치기한 경우
        assert mascot_status("calculator", d)[0] == "BLOCKED_MASCOT_INCONSISTENCY"
        assert choose_pose("- 글 유형: 계산·실수령형\n", (), d)[1] == "BLOCKED_MASCOT_INCONSISTENCY", "미승인 자산 변경은 차단"
        v2 = next_version(entry(d / "pig_calculator.png"), _sha(d / "pig_calculator.png"), "2026-12-01")
        assert v2["version"] == 2
        (d / "registry.json").write_text(json.dumps({"calculator": v2}), encoding="utf-8")
        assert mascot_status("calculator", d)[0] == "OK", "승인된 새 버전은 쓴다"
        def eof(_):
            raise EOFError
        assert not confirm_typed("calculator", eof), "입력이 없으면 승인하지 않는다"

    # TEST-THUMB-POSE-004: 주제가 반복 회피보다 먼저다. 반복·없는 자세로는 멈추지 않는다
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        reg = {}
        for p in ("face", "calculator", "document", "point_left", "point_up", "laptop", "phone"):
            Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(d / f"pig_{p}.png")
            reg[p] = entry(d / f"pig_{p}.png")
        (d / "registry.json").write_text(json.dumps(reg), encoding="utf-8")
        memo = lambda *lines: "\n".join(lines) + "\n"
        assert choose_pose(memo("- 글 유형: 계산·실수령형"), (), d)[0] == "calculator"
        assert choose_pose(memo("- 글 유형: 서식·절차형"), (), d)[0] == "document"
        assert choose_pose(memo("- 글 유형: 기준·한도형"), (), d)[0] == "face"
        assert choose_pose(memo("- 글 유형: 서식·절차형", "- 돼지 주제: tax_calculation"), (), d)[0] == "calculator"
        assert choose_pose(memo("- 글 유형: 서식·절차형", "- 돼지 자세: point_up"), (), d)[0] == "point_up"
        got = choose_pose(memo("- 글 유형: 계산·실수령형"), ("calculator", "face", "point_up"), d)
        assert got[:2] == ("calculator", "OK") and "그대로" in got[3], "계산 글의 calculator 반복은 정상 생성"
        assert choose_pose(memo("- 글 유형: 기준·한도형"), ("face",), d)[0] == "point_up", "동등한 자세가 있을 때만 반복을 피한다"
        assert choose_pose(memo("- 돼지 주제: online_process"), ("laptop",), d)[0] == "phone"
        assert choose_pose(memo("- 돼지 자세: calculator"), ("calculator",), d)[0] == "calculator", "지정한 자세는 반복이어도 쓴다"
        got = choose_pose(memo("- 글 유형: 혜택·지원금형"), (), d)
        assert got[:2] == ("face", "OK") and "pig_coin" in got[3], "없는 자세는 face로 대체"
        (d / "pig_face.png").unlink()
        assert choose_pose(memo("- 글 유형: 혜택·지원금형"), (), d)[1] == "MISSING_MASTER_MASCOT", "face까지 없을 때만 멈춘다"

    # 자세 정규화, 상반신 우선
    with tempfile.TemporaryDirectory() as d:
        from PIL import ImageDraw as _C
        q = Path(d) / "pose.png"
        raw = Image.new("RGBA", (1600, 1600), (0, 0, 0, 0))
        _C.Draw(raw).rectangle([500, 300, 1000, 1200], fill=(250, 190, 180, 255))
        raw.save(q)
        norm = Image.open(import_pose(q, q))
        assert norm.size == (1600, 1600) and norm.getchannel("A").getbbox()[1::2] == (POSE_TOP, POSE_BOTTOM) and spec_issues(q) == []

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(d / "pig_bust_calculator.png")
        full = d / "pig_calculator.png"
        assert card_mascot("calculator", full, d) == ("OK", full), "상반신이 등록 전이면 전신"
        (d / "registry.json").write_text(json.dumps({"bust_calculator": entry(d / "pig_bust_calculator.png")}), encoding="utf-8")
        assert card_mascot("calculator", full, d)[1].name == "pig_bust_calculator.png"
        assert bust_issues(d / "pig_bust_calculator.png") == []
        Image.new("RGBA", (11, 11), (0, 0, 0, 0)).save(d / "pig_bust_calculator.png")
        assert card_mascot("calculator", full, d)[0] == "BLOCKED_MASCOT_INCONSISTENCY"

    # 자세 파일 규격
    with tempfile.TemporaryDirectory() as d:
        from PIL import ImageDraw as _D
        p = Path(d) / "p.png"
        im = Image.new("RGBA", (1600, 1600), (0, 0, 0, 0))
        _D.Draw(im).rectangle([400, 200, 1200, 1400], fill=(250, 190, 180, 255))
        im.save(p)
        assert spec_issues(p) == [], spec_issues(p)
        _D.Draw(im).rectangle([400, 1300, 1200, 1599], fill=(250, 190, 180, 255))
        im.save(p)
        assert any("잘렸다" in x for x in spec_issues(p))
        Image.new("RGB", (1600, 1600), "white").save(p)
        assert any("투명" in x for x in spec_issues(p))
        Image.new("RGBA", (800, 800), (0, 0, 0, 0)).save(p)
        assert any("크기" in x for x in spec_issues(p))

    # TEST-THUMB-MOBILE-003: 돼지 25% 초과·배지 자리 중첩은 실패, 22%·안전 위치는 통과
    safe = {"right": 834, "bottom": 776}
    hit = {"right": 850, "bottom": 850}
    assert mobile_qc(120, 52, 0.22, mascot_rect=safe)["fail"] == []
    assert mobile_qc(120, 52, 0.25, mascot_rect=safe)["fail"] == []
    assert any("돼지" in x for x in mobile_qc(120, 52, 0.26, mascot_rect=safe)["fail"])
    assert any("안전영역" in x for x in mobile_qc(120, 52, 0.22, mascot_rect=hit)["fail"])
    assert any("메인" in x for x in mobile_qc(40, 0, 0.22)["fail"])
    assert mobile_qc(120, 30, 0.22)["drop_sub"] and not mobile_qc(120, 0, 0.22)["drop_sub"]
    assert any("대비" in x for x in mobile_qc(120, 52, 0.22, color="#dddddd")["fail"])
    assert all(contrast(c, CREAM) >= 4.5 for c in CATEGORY_COLORS.values()), "카테고리 색 대비"
    assert OUT_SIZE == 1080 and round(BADGE_ZONE[0] * OUT_SIZE / THUMB) == 160

    # manifest
    with tempfile.TemporaryDirectory() as d:
        global MANIFESTS
        keep, MANIFESTS = MANIFESTS, Path(d)
        try:
            p = write_manifest("30", doc(), "OK", None, 0.0, True, Path("a.png"), Path("b.png"), "calculator", "주제 tax_calculation")
            t = p.read_text(encoding="utf-8")
            assert 'main_copy: "600 + 300만원"' in t and "auto_fact_checks_passed: true" in t and "thumbnail_id" in t and '"900만원: 합산 한도' in t, t
            write_manifest("29", doc(), "OK", None, 0.0, True, Path("a.png"), Path("b.png"), "document")
            assert recent_poses("31") == ["calculator", "document"]
        finally:
            MANIFESTS = keep
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--import-pose" in sys.argv:
        i = sys.argv.index("--import-pose")
        assert sys.argv[i + 1] in MASCOT_POSES
        print(import_pose(Path(sys.argv[i + 2]), MASTER_DIR / f"pig_{sys.argv[i + 1]}.png"))
    elif "--approve-asset" in sys.argv:
        sys.exit(approve_asset(sys.argv[sys.argv.index("--approve-asset") + 1]))
    elif "--register-mascot" in sys.argv:
        sys.exit(register_mascots())
    else:
        print(__doc__)
