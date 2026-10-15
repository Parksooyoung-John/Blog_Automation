"""네이버 원고 검수 — 분량·소제목·이미지·경험·내부링크·태그, 그리고 티스토리 문장 중복.

    python -X utf8 check_naver.py
    python -X utf8 check_naver.py --selftest

⚠ 원고의 플레이스홀더 표기를 바꾸면 여기 정규식도 같이 봐야 한다.
2026-09-26에 표기가 `[이미지: ...]`에서 `[이미지 ①: ...]`로 바뀌었는데 정규식이 콜론을
고정하고 있어서, 이미지·경험을 0으로 세고 분량은 플레이스홀더까지 포함해 부풀려 잡았다.
오류를 내지 않고 조용히 틀린 값을 보고했다. `--selftest`가 그 재발을 막는다.
"""
import csv
import glob
import os
import re
import sys
import tempfile

PLACEHOLDERS = r'\[(이미지|경험 한 줄|내부 링크)[^\]]*\]'
VOLUME_CSV = '_workspace/keywords_volume.csv'   # 네이버 검색광고 API 실측 (gitignore됨)
# 없어진 서비스명 → 현재 이름. 2026-09-28 4편이 2024년 고용24로 통합된 '워크넷'을
# 현행 서비스처럼 안내한 채 발행됐다. `옛 워크넷`처럼 과거형으로 밝힌 표기는 허용한다.
STALE_TERMS = {'워크넷': '고용24'}

# 구조 검사(2026-10-07 추가) — 모바일 가독성과 검색·AI 요약이 가져가는 자리.
# 01~09편은 이미 발행됐다. 발행 글을 다시 고치는 것은 NAVER_GUIDE가 막으므로 판정에서 빼고 수치만 보여준다.
NEW_RULES_FROM = 10
MAX_SENT = 60          # 모바일 한 줄이 20자 안팎 → 60자는 3줄
HARD_SENT = 80
MAX_LONG_SENTS = 2     # 60자 초과 문장 허용 개수
MAX_PARA_SENTS = 3
MAX_BOLD = 30          # 문장 통째 볼드는 강조가 아니다 (10편 초안 최장 51자)


GEO_FROM = 11          # 작성 메모의 `- GEO 질의:` 줄을 요구하기 시작하는 편 (10편까지는 그 줄 없이 발행됐다)
MIN_GEO_QUERIES = 2


def geo_queries(md: str) -> list:
    """작성 메모의 `- GEO 질의: a | b | c` → ['a', 'b', 'c']. AI 브리핑 인용을 추적할 질의다.

    `keyword_research.py geo`로 블로그 인용형(aibAnswer)인지 확인한 질의를 적는다 —
    공공정책형 질의는 블로그를 인용하지 않아 추적해도 0이다.
    """
    m = re.search(r'^- GEO 질의:\s*(.+?)\s*$', md, flags=re.M)
    return [q.strip() for q in m.group(1).split('|') if q.strip()] if m else []


LENGTH_FROM = 12       # 분량·시각 요소 새 기준을 적용하기 시작하는 편
LENGTH_NEW = (1500, 2500)   # AI 브리핑에 인용된 블로그 글 24편의 중앙값이 2,195자였다(2026-10-09 실측)
LENGTH_OLD = (800, 1600)
MAX_TABLE_COLS = 3     # 폰 화면 폭


def is_table(block: str) -> bool:
    return all(ln.lstrip().startswith('|') for ln in block.strip().split('\n'))


# 박스(2026-10-12): 인용 블록의 첫 줄에 종류를 적는다 — `> [요약] 제목` 다음 줄부터 `> - 항목`.
# 붙여넣기 파일에는 배경색 1칸 표로 나간다. 시각 요소 개수에는 넣지 않는다(박스로 `소제목+1`을 채우게 된다).
# `[질문]`은 제목이 Q, 나머지 줄이 A다.
BOX_RE = re.compile(r'> ?\[(요약|주의|안내|출처|질문)\] ?')
MAX_SUMMARY_ITEMS = 6


def is_box(block: str) -> bool:
    block = block.strip()
    return bool(BOX_RE.match(block)) and all(ln.startswith('>') for ln in block.split('\n'))


def box_lines(block: str) -> list:
    """박스 블록 → [제목, 줄, …]. `>`와 종류 표지를 걷어낸다."""
    return [re.sub(r'^> ?', '', ln) for ln in BOX_RE.sub('> ', block.strip(), count=1).split('\n')]


def _nums(text: str) -> set:
    return set(re.findall(r'\d+(?:[.,]\d+)*', text))


def summary_issues(blocks: list) -> list:
    """요약 박스가 본문과 다른 숫자를 말하면 안 된다 — 요약만 읽고 나가는 사람이 틀린 값을 가져간다."""
    issues = []
    rest = _nums('\n'.join(b for b in blocks if not is_box(b)))
    for blk in blocks:
        if not (is_box(blk) and BOX_RE.match(blk).group(1) == '요약'):
            continue
        _, *items = box_lines(blk)
        if len(items) > MAX_SUMMARY_ITEMS:
            issues.append(f"요약 박스가 {len(items)}줄 ({MAX_SUMMARY_ITEMS}줄 이하)")
        missing = sorted(_nums('\n'.join(items)) - rest)
        if missing:
            issues.append(f"요약 박스의 숫자가 본문에 없다: {', '.join(missing)}")
    return issues


def same_box_title(results: dict) -> list:
    """박스 제목이 같은 원고 쌍. 제목을 글마다 똑같이 쓰면 그 줄이 고정 블록이 된다."""
    seen, pairs = {}, []
    for name, titles in results.items():
        for t in (x for x in titles if x != SUMMARY_TITLE):
            if seen.get(t, name) != name:
                pairs.append((seen[t], name, t))
            seen.setdefault(t, name)
    return pairs


def table_rows(block: str) -> list:
    """마크다운 표 블록 → 칸 목록의 목록. `|---|---|` 구분선 행은 뺀다."""
    rows = [[c.strip() for c in ln.strip().strip('|').split('|')] for ln in block.strip().split('\n')]
    return [r for r in rows if not all(re.fullmatch(r':?-{2,}:?', c) for c in r)]


def split_sentences(text: str) -> list:
    """문장 단위로 나눈다. 한글·닫는 괄호 뒤의 마침표에서만 끊는다 —
    `7.19%`, `2019. 8. 27.`, `1577-1000`에서 끊기면 안 된다."""
    return [s for s in re.split(r'(?<=[가-힣)][.?!])\s+', text.strip()) if s]


def target_keyword(md: str):
    """제목에 그대로 들어 있는 태그 중 가장 긴 것 — NAVER_GUIDE 태그 규칙상 그것이 목표 키워드다.

    첫 태그를 쓰면 안 된다: 1·3·8편의 첫 태그는 셋 다 '근로장려금'이었다.
    """
    line = re.search(r"^#\S+(?: +#\S+)+$", md, re.M)
    if not line:
        return None
    tags = re.findall(r"#(\S+)", line.group(0))
    title = re.search(r"^제목: (.+)$", md, re.M)
    squeezed = title.group(1).replace(" ", "") if title else ""
    return max((t for t in tags if t in squeezed), key=len, default=tags[0])


def structure_issues(body: str, keyword) -> list:
    """body: 제목·태그·플레이스홀더를 걷어낸 본문(소제목과 ** 표시는 남아 있다). → 문제 설명 목록"""
    issues = []
    blocks = [b.strip() for b in re.split(r'\n\s*\n', body) if b.strip()]
    intro = body.split('\n## ')[0]
    if keyword and keyword not in intro.replace(' ', ''):
        issues.append(f"도입부에 목표 키워드({keyword})가 없다")
    if not re.search(r'\d', intro):
        issues.append("도입부에 숫자가 없다 — 답(금액·기한·일수)을 먼저")
    if not re.search(r'20\d\d', body):
        issues.append("본문에 기준 연도가 없다")

    long_sents, hard = 0, 0
    for blk in blocks:
        if blk.startswith('## '):
            continue
        if is_table(blk):        # 표는 문장·볼드 한도 대신 열 수만 본다
            cols = max(len(r) for r in table_rows(blk))
            if cols > MAX_TABLE_COLS:
                issues.append(f"표가 {cols}열 — 폰에서 깨진다 ({MAX_TABLE_COLS}열 이하)")
            continue
        box = is_box(blk)
        if box:
            blk = '\n'.join(box_lines(blk))
        is_list = box or all(re.match(r'(- |\d+\. )', ln) for ln in blk.split('\n'))
        units = blk.split('\n') if is_list else [blk]     # 목록은 줄 단위, 문단은 통째로
        for u in units:
            if len(re.findall(r'\*\*.+?\*\*', u)) > 1:
                issues.append(f"한 {'줄' if is_list else '문단'}에 볼드가 둘 이상: {u[:24]}…")
            for s in split_sentences(u.replace('**', '')):
                long_sents += len(s) > MAX_SENT
                hard += len(s) > HARD_SENT
        if not is_list and len(split_sentences(blk)) > MAX_PARA_SENTS:
            issues.append(f"문단이 {len(split_sentences(blk))}문장: {blk[:24]}…")
    if hard:
        issues.append(f"{HARD_SENT}자 넘는 문장 {hard}개")
    if long_sents > MAX_LONG_SENTS:
        issues.append(f"{MAX_SENT}자 넘는 문장 {long_sents}개 (허용 {MAX_LONG_SENTS}개)")
    big = [b for b in re.findall(r'\*\*(.+?)\*\*', body) if len(b) > MAX_BOLD]
    if big:
        issues.append(f"볼드가 {MAX_BOLD}자를 넘는 곳 {len(big)}개: {big[0][:24]}…")
    return issues + summary_issues(blocks)


HEAD_RULES_FROM = 14   # 소제목 문구 기준을 적용하기 시작하는 편
MAX_HEAD = 22          # 에디터 소제목 한 줄이 13자 안팎 — 14편 초안의 27자 소제목이 "5월 종/합소득세"로 단어 중간에서 끊겼다
MAX_SAME_START = 2     # 같은 첫 어절로 시작하는 소제목 허용 개수 (13편은 5개 중 4개가 "연말정산 …"이었다)


def heading_issues(heads: list) -> list:
    """heads: 소제목 문자열 목록(`## ` 제외). → 문제 설명 목록

    추적 질의의 단어는 소제목이 아니라 바로 다음 문장에 넣는다(NAVER_GUIDE). 소제목마다 키워드로 시작하면
    길어지고, 같은 말이 줄줄이 반복된다.
    """
    issues = [f"소제목이 {len(h)}자 ({MAX_HEAD}자 이하): {h[:16]}…" for h in heads if len(h) > MAX_HEAD]
    starts = [h.split()[0] for h in heads if h.split()]
    for w in dict.fromkeys(starts):
        if starts.count(w) > MAX_SAME_START:
            issues.append(f"소제목 {starts.count(w)}개가 '{w}'(으)로 시작한다 ({MAX_SAME_START}개 이하)")
    return issues


# 벤치마크 템플릿 시험(2026-10-14, 15~17편). 명세 `donsalimpyo-post-harness.md`를 기존 원고 형식으로 옮긴 것이다 —
# 적용 방식과 판정 기준은 NAVER_GUIDE 「벤치마크 템플릿 시험」. 철회하면 TEMPLATE_FROM을 올린다.
TEMPLATE_FROM = 15
LENGTH_TEMPLATE = (2500, 4000)      # 벤치마크 최근 3편 공백 제외 2,681~3,410자
TITLE_LEN = (45, 55)
BANNED_TITLE = ("충격", "무조건", "필독")
SUMMARY_TITLE = "🐷 돼지가 먼저 알려줘요 (3초 요약)"      # 템플릿 고정 제목이라 박스 제목 중복 검사에서 뺀다
SUMMARY_ITEMS = 5
# 순서·이름은 사용자가 15편을 발행한 모양이다(2026-10-15): 살림 체크에 번호 없음, Q&A 다음이 근거 자료(맨 끝)
FIXED_HEADS = ["오늘 바로 할 살림 체크", "오늘의 살림 정리", "🐷 새싹돼지 Q&A", "근거 자료"]
MEMO_LINE = "🪙 살림 메모:"
THUMB_TYPES = ("scene", "card")     # scene = Gemini가 글자까지 그린 그림, card = 사진 + 코드로 얹은 카드
POST_TYPES = ("서식·절차형", "기준·한도형", "오류·누락형", "제도 변경형", "선택·비교형", "계산·실수령형", "혜택·지원금형")
# 본문에서 근거 표와 대조할 수치 — 단위가 붙은 것만 본다(소제목 번호·'5가지' 같은 말은 빼려고).
UNIT_NUM = re.compile(r'(\d+(?:[.,]\d+)*)\s?(%|만\s?원|억\s?원|천\s?원|원|세|년|개월|일|명|배)')
BENCH_DIR = '_workspace/benchmark'
BENCH_BLOG = 'sky09020'


def memo_value(md: str, key: str):
    m = re.search(rf'^- {re.escape(key)}:\s*(.+?)\s*$', md, flags=re.M)
    return m.group(1) if m else None


def facts(md: str) -> list:
    """작성 메모의 `### 수치 근거` 표 → [[항목, 값, 출처·식, 확인일, 상태], …]. 명세의 facts.md를 원고 안에 둔 것이다."""
    sec = md.split('### 수치 근거', 1)
    blk = re.match(r'\s*((?:[ \t]*\|.*(?:\n|$))+)', sec[1]) if len(sec) == 2 else None
    return [r + [''] * (5 - len(r)) for r in table_rows(blk.group(1))[1:]] if blk else []


def thumb_lines(md: str):
    """`- 썸네일 문구: 윗줄 | 아랫줄` → (윗줄, 아랫줄). `/`(줄바꿈 표시)는 뺀 글자로 센다."""
    v = memo_value(md, '썸네일 문구')
    if not v or '|' not in v:
        return None
    a, b = (x.strip().replace('/', '') for x in v.split('|', 1))
    return a, b


def template_issues(md: str, body: str, text: str, keyword) -> list:
    """15편부터의 벤치마크 템플릿. body: 플레이스홀더가 남은 본문, text: 플레이스홀더를 뺀 본문. → 문제 설명 목록"""
    issues = []
    blocks = [x.strip() for x in re.split(r'\n\s*\n', body) if x.strip() and not re.fullmatch(r'-{3,}', x.strip())]
    title = re.search(r'^제목: (.+)$', md, re.M).group(1).strip()

    # G1 순서: 훅 → 썸네일 → (도입) → 요약 → 1~5 → 6 체크 → 정리 → 근거 → Q&A
    if not blocks or not re.fullmatch(r'"[^"\n]{2,40}\?"', blocks[0]):
        issues.append('본문 첫 줄이 따옴표로 감싼 질문("…?", 40자 이하)이 아니다')
    if len(blocks) < 2 or not blocks[1].startswith('[이미지 ①'):
        issues.append('질문 바로 다음이 [이미지 ①] 썸네일이 아니다')
    order = [("요약 박스", lambda x: is_box(x) and BOX_RE.match(x).group(1) == '요약')]
    order += [(f"## {i}.", lambda x, i=i: x.startswith(f'## {i}. ')) for i in range(1, 6)]
    order += [(f"## {h}", lambda x, h=h: x == f'## {h}') for h in FIXED_HEADS]
    pos = 0
    for name, ok in order:
        i = next((k for k in range(pos, len(blocks)) if ok(blocks[k])), None)
        if i is None:
            issues.append(f'템플릿 순서: `{name}`이(가) 없거나 앞 블록보다 먼저 나온다')
        else:
            pos = i + 1
    # G4 번호 소제목은 정확히 1~6
    nums = re.findall(r'^## (\d+)\. ', body, flags=re.M)
    if nums != [str(i) for i in range(1, 6)]:
        issues.append(f'번호 소제목이 {", ".join(nums) or "없음"} — 1~5여야 한다')

    # G2 제목
    lo, hi = TITLE_LEN
    if not lo <= len(title) <= hi:
        issues.append(f'제목 {len(title)}자 ({lo}~{hi}자)')
    if not re.search(r'20\d\d', title[:15]):
        issues.append('제목 앞 15자에 연도가 없다')
    if keyword and not 0 <= title.replace(' ', '').find(keyword) < 15:
        issues.append(f'제목 앞부분에 목표 키워드({keyword})가 없다')
    if not re.search(r'\d', re.sub(r'20\d\d', '', title)):
        issues.append('제목에 연도 말고 숫자가 없다')
    issues += [f'제목 금지어: {w}' for w in BANNED_TITLE if w in title]

    # G3 요약 박스
    for blk in blocks:
        if is_box(blk) and BOX_RE.match(blk).group(1) == '요약':
            head, *items = box_lines(blk)
            if head.strip() != SUMMARY_TITLE:
                issues.append(f'요약 박스 제목이 "{SUMMARY_TITLE}"가 아니다')
            if len(items) != SUMMARY_ITEMS or not all(re.search(r'\d', x) for x in items):
                issues.append(f'요약 박스는 {SUMMARY_ITEMS}줄, 줄마다 숫자 (지금 {len(items)}줄)')
    # G5 표 아래 살림 메모
    for k, blk in enumerate(blocks):
        if is_table(blk) and not (k + 1 < len(blocks) and blocks[k + 1].startswith(MEMO_LINE)):
            issues.append(f'표 다음 줄이 `{MEMO_LINE}`이 아니다: {blk.splitlines()[0][:24]}…')

    # G6·G7 수치 근거
    rows = facts(md)
    if not rows:
        issues.append('작성 메모에 `### 수치 근거` 표가 없다')
    else:
        for r in rows:
            if r[4] not in ('VERIFIED', 'UNVERIFIED', '계산'):
                issues.append(f'수치 근거 상태가 VERIFIED·UNVERIFIED·계산 중 하나가 아니다: {r[0]}')
            if r[4] == '계산' and not re.search(r'[=×*/÷+−]|\d\s*-\s*\d', r[2]):
                issues.append(f'계산 행에 식이 없다: {r[0]}')
        ok = set().union(*(_nums(r[1]) for r in rows if r[4] in ('VERIFIED', '계산')))
        unverified = set().union(*(_nums(r[1]) for r in rows if r[4] == 'UNVERIFIED')) - ok
        used = {m.group(1) for m in UNIT_NUM.finditer(text)
                if not (m.group(2) == '년' and re.fullmatch(r'20\d\d', m.group(1)))}
        if used - ok:
            issues.append(f'수치 근거 표에 없는 수치: {", ".join(sorted(used - ok)[:6])}')
        if used & unverified:
            issues.append(f'UNVERIFIED 수치가 본문에 있다: {", ".join(sorted(used & unverified))}')

    # G9 근거 자료
    src = body.split('## 근거 자료', 1)[1].split('\n## ', 1)[0] if '## 근거 자료' in body else ''
    if not re.search(r'https?://|[가-힣](법|청|공단|부)(?![가-힣])', src):
        issues.append('근거 자료에 URL이나 기관·법령 이름이 없다')

    # 썸네일(G8·G11·G12의 원고 쪽 절반 — 연속 유형은 main에서 본다)
    kind, post_type = memo_value(md, '썸네일 유형'), memo_value(md, '글 유형')
    if kind not in THUMB_TYPES:
        issues.append(f'작성 메모 `- 썸네일 유형:`이 {"·".join(THUMB_TYPES)} 중 하나가 아니다')
    if post_type not in POST_TYPES:
        issues.append(f'작성 메모 `- 글 유형:`이 {"·".join(POST_TYPES)} 중 하나가 아니다')
    lines = thumb_lines(md)
    if lines:
        a, b = lines
        if kind == 'card' and not (8 <= len(a) <= 12 and 8 <= len(b) <= 12):
            issues.append(f'card 썸네일 문구는 두 줄 각 8~12자 (지금 {len(a)}·{len(b)}자)')
        elif len(a) > 12 or len(b) > 22:
            issues.append(f'썸네일 문구는 윗줄 12자·아랫줄 22자 이하 (지금 {len(a)}·{len(b)}자)')
        if re.search(r'(못|안) ?\S*니다|없습니다', a + ' ' + b):
            issues.append('썸네일 문구에 단정 표현이 있다 — 조건을 남긴다("못 받을 수 있어요")')
    if kind == 'scene':
        scene = memo_value(md, '썸네일 장면')
        if not scene:
            issues.append('scene인데 작성 메모에 `- 썸네일 장면:`(영어 장면 설명)이 없다')
        elif re.search(r'[가-힣0-9]', scene):
            issues.append('썸네일 장면 설명에 한글·숫자가 있다 — 글자는 썸네일 문구로만 넣는다')
    if kind == 'card':
        big = (memo_value(md, '썸네일 강조 숫자') or '').split('|')[0]      # `6% | 1년당 감액` — 앞이 숫자, 뒤는 목업 설명
        if not big or not _nums(big) or not _nums(big) <= _nums(text):
            issues.append('card인데 `- 썸네일 강조 숫자:`가 없거나 그 숫자가 본문에 없다')
    return issues


# card 썸네일은 보류 중이다(2026-10-15 사용자 결정: 품질이 떨어져, Mirr 연계로 품질을 확보하면 다시 쓴다).
# 그동안 scene만 쓰므로 3연속 금지는 끄고, 대신 card로 쓴 원고를 막는다. 다시 쓰면 True로 바꾼다.
CARD_ENABLED = False


def card_paused(kinds: dict) -> list:
    """CARD_ENABLED가 꺼져 있는데 썸네일 유형이 card인 원고."""
    return [] if CARD_ENABLED else [k for k, v in sorted(kinds.items()) if v == "card"]


def thumb_streak(kinds: dict, enabled: bool = None) -> list:
    """편 번호 순 썸네일 유형 → 같은 유형이 3편째 이어진 원고. 명세 6-2 '같은 유형 3편 연속 금지'
    (scene 3연속도 막으므로 '3편 중 1편은 card'도 같이 지켜진다). card 보류 중에는 보지 않는다."""
    if not (CARD_ENABLED if enabled is None else enabled):
        return []
    seq = [(k, v) for k, v in sorted(kinds.items()) if v]
    return [seq[i][0] for i in range(2, len(seq)) if seq[i][1] == seq[i - 1][1] == seq[i - 2][1]]


def format_issues(chars: int, heads: int, images: int, tables: int, thumb: bool, length=LENGTH_NEW) -> list:
    """12편부터 보는 분량·시각 요소 기준. → 문제 설명 목록"""
    issues = []
    lo, hi = length
    if not lo <= chars <= hi:
        issues.append(f"분량 {chars}자 ({lo}~{hi}자)")
    if images + tables < heads + 1:
        issues.append(f"시각 요소 {images + tables}개 (이미지 {images} + 표 {tables}) — 소제목 {heads}개면 {heads + 1}개 이상")
    if not thumb:
        issues.append("작성 메모에 `- 썸네일 문구: 윗줄 | 아랫줄` 줄이 없다")
    return issues


def parts(path):
    n = open(path, encoding='utf-8').read()
    b = n.split('## 작성 메모')[0]
    tags = re.findall(r'#[가-힣A-Za-z0-9]+', b)
    b2 = re.sub(r'^제목:.*$', '', b, flags=re.M)
    b2 = re.sub(r'^#[가-힣A-Za-z0-9]+.*$', '', b2, flags=re.M)
    c = re.sub(PLACEHOLDERS, '', b2, flags=re.S)
    c = re.sub(r'^-{3,}$', '', c, flags=re.M)
    return n, b2, c, tags


def sents(x):
    x = re.sub(r'[#*>|\-]', '', x)
    return {s.strip() for s in re.split(r'[.!?]\s|\n', x) if len(s.strip()) >= 12}


def load_volumes() -> dict:
    """태그가 실제로 검색되는 말인지 보려고 검색량을 읽는다.

    2026-09-27 4편 작성에서 태그 10개 중 4개가 검색되지 않는 조합어였다
    (워크넷구직등록·수급자격신청·실업급여첫입금). 본문에서 그럴듯하게 만들어낸
    말이라 눈으로는 안 걸러진다.

    ⚠ 이 CSV는 시드에서 확장한 집합이지 전체 키워드 사전이 아니다. `홈택스`처럼
    검색량이 큰 말도 들어 있지 않다. 따라서 **"CSV에 없음"을 "검색량 0"으로
    읽으면 안 되고**, 통과/실패 기준으로도 쓰지 않는다. 후보를 비교할 때
    참고하는 용도다.
    """
    if not os.path.exists(VOLUME_CSV):
        return {}
    with open(VOLUME_CSV, encoding='utf-8-sig') as f:
        return {r['keyword']: int(r['total']) for r in csv.DictReader(f) if r.get('total')}


def measure(path, tistory, volumes=None, bench=frozenset()):
    n, b, c, tags = parts(path)
    m = re.search(r'^제목: (.+)$', n, flags=re.M)
    if not m:
        return None
    # 표의 세로선과 구분선 행은 글자가 아니다
    # 글자 수를 셀 때만 뺀다. 구조 검사에는 세로선이 남아 있어야 표로 알아본다 —
    # 처음엔 c를 덮어써서 12편의 표가 82자짜리 '문장'으로 잡혔다.
    counted = re.sub(r'^\s*\|.*$', lambda t: '' if re.fullmatch(r'[\s|:\-]+', t.group()) else t.group().replace('|', ''),
                     c, flags=re.M)
    counted = re.sub(r'^> ?', '', BOX_RE.sub('', counted), flags=re.M)     # 박스의 `>`와 종류 표지도 글자가 아니다
    boxes = [box_lines(blk)[0] for blk in re.split(r'\n\s*\n', b) if is_box(blk)]
    tables = sum(is_table(blk) for blk in re.split(r'\n\s*\n', b) if blk.strip())
    r = {
        "title": m.group(1),
        "tables": tables,
        "boxes": boxes,
        "thumb": bool(re.search(r'^- 썸네일 문구:\s*\S', n, flags=re.M)),
        "chars": len(counted.strip()),
        "heads": len(re.findall(r'^## ', b, flags=re.M)),
        "images": len(re.findall(r'\[이미지', b)),
        "exp": len(re.findall(r'\[경험 한 줄', b)),
        "links": len(re.findall(r'\[내부 링크', b)),
        "tags": tags,
        "vol": {t: volumes.get(t.lstrip('#')) for t in tags} if volumes else {},
        "dup": sents(c) & tistory,
        "bench_dup": sents(c) & bench,
        "stale": [f"{k}→{v}" for k, v in STALE_TERMS.items()
                  if re.search(f'(?<!옛 ){k}', c)],
        "cover_kw": (re.findall(r'^- 대표사진 검색어:\s*(.+?)\s*$', n, flags=re.M) or [None])[0],
        "structure": structure_issues(c, target_keyword(n)),
        "judged": not (num := re.match(r'\d+', os.path.basename(path))) or int(num.group()) >= NEW_RULES_FROM,
        "geo": geo_queries(n),
        "geo_required": not num or int(num.group()) >= GEO_FROM,
        "new_format": not num or int(num.group()) >= LENGTH_FROM,
        "template": bool(num) and int(num.group()) >= TEMPLATE_FROM,
        "thumb_type": memo_value(n, '썸네일 유형'),
    }
    if r["template"]:          # 소제목 9개 중 번호 1~5만 본문 구간이다 — 분량·시각 요소·소제목 문구는 그 다섯으로 본다
        r["format"] = format_issues(r["chars"], 5, r["images"], tables, r["thumb"], LENGTH_TEMPLATE)
        r["format"] += heading_issues(re.findall(r'^## [1-5]\. (.+?)\s*$', b, flags=re.M))
        r["format"] += template_issues(n, b, c, target_keyword(n))
    elif r["new_format"]:
        r["format"] = format_issues(r["chars"], r["heads"], r["images"], tables, r["thumb"])
        if num and int(num.group()) >= HEAD_RULES_FROM:
            r["format"] += heading_issues(re.findall(r'^## (.+?)\s*$', b, flags=re.M))
    else:       # 11편까지는 발행 당시 기준 그대로
        lo, hi = LENGTH_OLD
        r["format"] = [] if lo <= r["chars"] <= hi else [f"분량 {r['chars']}자 ({lo}~{hi}자)"]
    return r


def same_cover_kw(results: dict) -> list:
    """대표사진 검색어가 같은 원고 쌍. 2026-09-28 1·3편이 같은 검색어라
    suggest_cover.py 후보 12장이 똑같이 나왔다 — 같은 사진을 두 글에 쓰게 된다."""
    seen, pairs = {}, []
    for name, kw in results.items():
        if kw and kw in seen:
            pairs.append((seen[kw], name))
        seen.setdefault(kw, name)
    return pairs


def passes(r):
    return (not r["format"] and (r["template"] or 3 <= r["heads"] <= (6 if r["new_format"] else 5)) and r["images"] >= 2
            and r["exp"] >= 1 and r["links"] >= 1 and 8 <= len(r["tags"]) <= 12
            and not r["dup"] and not r["bench_dup"] and not r["stale"]
            and not (r["judged"] and r["structure"])
            and not (r["geo_required"] and len(r["geo"]) < MIN_GEO_QUERIES))


def selftest():
    """실제 원고에 쓰는 표기법 그대로 넣어 카운트가 맞는지 본다."""
    doc = (
        "제목: 테스트 제목\n\n---\n\n"
        "[이미지 ①: `assets/x.png` — 제작 완료]\n\n"
        "도입 문단입니다. 고용24 구직등록(옛 워크넷)을 합니다.\n\n"
        "[경험 한 줄 ①]\n\n"
        "## 소제목 하나\n\n본문입니다.\n\n"
        "[이미지 ②: **직접 캡처 필요** — 어쩌고]\n\n"
        "## 소제목 둘\n\n본문입니다.\n\n"
        "## 소제목 셋\n\n본문입니다.\n\n"
        "[내부 링크: 아래 문장을 쓰고 줄을 바꾼 뒤 이 주소를 붙여넣으면 카드가 생성됩니다\n"
        "            ⚠ 문장 중간에 붙여넣지 말 것 → https://blog.naver.com/education_blog/1]\n\n"
        "아래 글을 보세요.\n\n"
        "[경험 한 줄 ② | A안(사실): 후보 문장은 글자 수에 들어가지 않습니다. | B안(해당될 때만): 이 문장도 마찬가지입니다.]\n\n"
        "#태그1 #태그2 #태그3 #태그4 #태그5 #태그6 #태그7 #태그8 #태그9 #태그10\n\n"
        "---\n\n## 작성 메모 (발행 시 삭제)\n\n- 메모는 세지 않는다\n"
        "- 대표사진 검색어: 퇴사, 취업 | job interview\n"
        "- GEO 질의: 실업급여 수급기간 알바 | 실업급여 수급기간 해외여행\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        open(path, "w", encoding="utf-8").write(doc)
        r = measure(path, set())

    assert r["title"] == "테스트 제목", r["title"]
    assert r["images"] == 2, f"이미지 {r['images']}"
    assert r["exp"] == 2, f"경험 {r['exp']}"
    assert r["links"] == 1, f"내부링크 {r['links']}"
    assert r["heads"] == 3, f"소제목 {r['heads']}"
    assert len(r["tags"]) == 10, f"태그 {len(r['tags'])}"
    # 플레이스홀더·태그·작성 메모가 글자수에 섞이면 안 된다 (본문은 100자 남짓)
    assert r["stale"] == [], f"옛 워크넷 표기까지 잡았다: {r['stale']}"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        open(path, "w", encoding="utf-8").write(doc.replace("(옛 워크넷)", " 워크넷"))
        assert measure(path, set())["stale"] == ["워크넷→고용24"], "현행처럼 쓴 워크넷을 놓쳤다"
    assert r["chars"] < 120, f"플레이스홀더가 글자수에 섞였다: {r['chars']}"
    assert r["cover_kw"] == "퇴사, 취업 | job interview", r["cover_kw"]
    assert r["geo"] == ["실업급여 수급기간 알바", "실업급여 수급기간 해외여행"], r["geo"]
    assert geo_queries("- GEO 질의: 하나만\n") == ["하나만"] and geo_queries("메모 없음") == []
    assert same_cover_kw({"01": "a | x", "02": "b | y", "03": "a | x", "04": None, "05": None}) == [("01", "03")]

    # 문장 분리: 소수점·날짜·전화번호에서 끊기면 안 된다
    assert split_sentences("보험료율은 7.19%입니다. 개정일은 2019. 8. 27.이고 번호는 1577-1000입니다. 끝났나요? 네.") == [
        "보험료율은 7.19%입니다.", "개정일은 2019. 8. 27.이고 번호는 1577-1000입니다.", "끝났나요?", "네."]

    good = ("실업급여 수급기간은 2026년 기준 120일에서 270일입니다.\n\n## 소제목\n\n"
            "가입기간이 **1년**을 넘으면 늘어납니다. 나이도 봅니다.\n\n- 1년 미만 — **120일**\n- 10년 이상 — **240일**\n")
    assert structure_issues(good, "실업급여수급기간") == [], structure_issues(good, "실업급여수급기간")

    def has(body, word, kw="키워드"):
        return any(word in i for i in structure_issues(body, kw))
    base = "키워드는 2026년에 3일입니다.\n\n## 소제목\n\n"
    assert has("도입부입니다 2026.\n\n## 소제목\n\n본문.", "목표 키워드")
    assert has("키워드 설명입니다.\n\n## 소제목\n\n2026년 본문.", "도입부에 숫자")
    assert has("키워드는 3일입니다.\n\n## 소제목\n\n본문.", "기준 연도")
    assert has(base + "가" * 81 + "입니다.", f"{HARD_SENT}자 넘는")
    assert has(base + "\n\n".join("나" * 61 + "입니다." for _ in range(3)), f"{MAX_SENT}자 넘는")
    assert not has(base + "\n\n".join("나" * 61 + "입니다." for _ in range(2)), f"{MAX_SENT}자 넘는")
    assert has(base + "하나입니다. 둘입니다. 셋입니다. 넷입니다.", "문단이 4문장")
    assert has(base + "**하나**와 **둘**을 같이 강조합니다.", "볼드가 둘 이상")
    assert not has(base + "- 첫 줄 **하나**\n- 둘째 줄 **둘**", "볼드가 둘 이상")   # 목록은 줄마다 하나씩 허용
    assert has(base + "**" + "다" * 31 + "**", f"{MAX_BOLD}자를 넘는")

    # 표: 구분선 행을 빼고 읽고, 문장·볼드 한도는 적용하지 않으며, 4열은 막는다
    tbl = "| 가입기간 | 50세 미만 | 50세 이상 |\n|---|:---:|---|\n| 1년 미만 | **120일** | **120일** |"
    assert is_table(tbl) and not is_table("| 표처럼 시작하지만\n본문 줄")
    assert table_rows(tbl) == [["가입기간", "50세 미만", "50세 이상"], ["1년 미만", "**120일**", "**120일**"]]
    assert not has(base + tbl, "볼드가 둘 이상") and not has(base + tbl, "열")
    assert has(base + "| a | b | c | d |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |", "4열")

    # 박스: 줄 단위로 보고(목록처럼), 표지는 글자 수에 안 들며, 요약의 숫자는 본문에 있어야 한다
    bx = "> [요약] 월세 공제 한눈에\n> - 한도는 **연 120일**\n> - 기준은 **1년**"
    assert all(is_box(f"> [{k}] 제목\n> 줄") for k in ("요약", "주의", "안내", "출처", "질문"))
    assert is_box(bx) and not is_box("> 그냥 인용문") and not is_box("> [요약] 제목\n본문 줄")
    assert box_lines(bx) == ["월세 공제 한눈에", "- 한도는 **연 120일**", "- 기준은 **1년**"]
    assert structure_issues(good + "\n" + bx, "실업급여수급기간") == []          # 120·1 모두 본문에 있다
    assert has(base + bx, "본문에 없다: 1, 120")
    assert not has(base + bx.replace("요약", "주의"), "본문에 없다")               # 수치 대조는 요약만
    assert has(base + "> [요약] 제목\n" + "\n".join("> - 줄" for _ in range(7)), "요약 박스가 7줄")
    assert same_box_title({"14": ["가", "나"], "15": ["다"], "16": ["나"]}) == [("14", "16", "나")]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        open(path, "w", encoding="utf-8").write(doc.replace("[경험 한 줄 ①]", "[경험 한 줄 ①]\n\n> [안내] 가\n> - 나"))
        bxr = measure(path, set())
    assert bxr["boxes"] == ["가"] and bxr["tables"] == 0, (bxr["boxes"], bxr["tables"])
    assert bxr["chars"] == r["chars"] + len("\n\n가\n- 나"), (bxr["chars"], r["chars"])     # `>`·[안내]는 글자 수에 안 든다

    # 14편부터의 소제목 문구: 길이와 같은 말로 시작하는 반복
    assert heading_issues(["퇴사하는 달에 회사가 먼저 정산합니다", "서류는 원천징수영수증부터", "재취업 안 했다면 5월에 직접 신고"]) == []
    assert any("23자" in i for i in heading_issues(["가" * 23]))
    assert heading_issues(["가" * MAX_HEAD]) == []
    same = heading_issues(["연말정산 월세 공제", "연말정산 월세 환급", "연말정산 월세 서류", "월세 한도"])
    assert len(same) == 1 and "3개가 '연말정산'" in same[0], same
    assert heading_issues(["연말정산 월세 공제", "연말정산 월세 환급", "월세 한도"]) == []          # 2개까지는 허용
    for n, want in (("13", False), ("14", True)):          # 13편까지는 발행 당시 기준 그대로
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, f"{n}_t.md")
            open(path, "w", encoding="utf-8").write(doc)   # 소제목 셋이 모두 '소제목'으로 시작한다
            assert any("'소제목'" in i for i in measure(path, set())["format"]) == want, n

    # 12편부터의 분량·시각 요소 기준
    assert format_issues(2000, 4, 4, 1, True) == []
    assert any("분량" in i for i in format_issues(1499, 4, 4, 1, True))
    assert any("분량" in i for i in format_issues(2501, 4, 4, 1, True))
    assert any("시각 요소 4개" in i for i in format_issues(2000, 4, 3, 1, True))     # 소제목 4개면 5개 필요
    assert any("썸네일 문구" in i for i in format_issues(2000, 4, 4, 1, False))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.md")
        open(path, "w", encoding="utf-8").write(doc.replace("## 소제목 둘\n\n본문입니다.", "## 소제목 둘\n\n" + tbl)
                                                + "- 썸네일 문구: 윗줄 | 아랫줄\n")
        t = measure(path, set())
    assert (t["tables"], t["thumb"]) == (1, True), (t["tables"], t["thumb"])
    assert not any("볼드가 둘 이상" in i for i in t["structure"]), t["structure"]   # 파일로 읽어도 표는 표로 본다
    assert "|" not in str(t["chars"]) and t["chars"] < 160, t["chars"]        # 세로선·구분선은 글자 수에 안 든다

    # 15편부터의 벤치마크 템플릿 — 원고에 실제로 쓰는 표기 그대로
    sec = "\n\n".join(
        f"## {i}. 소제목{'일이삼사오'[i - 1]} 결론입니다\n\n[이미지 {'②③④⑤⑥'[i - 1]}: 카드]\n\n본문은 6% 감액입니다.\n\n"
        f"| 구분 | 값 |\n|---|---|\n| 조기 | **6%** |\n\n🪙 살림 메모: 1년당 기준입니다.\n\n결론 한 줄입니다.\n\n---"
        for i in range(1, 6))
    tdoc = (
        "제목: 2026 국민연금 수령나이 | 조기수령 vs 연기수령, 5년 당기면 얼마나 깎일까 확인할 5가지\n\n---\n\n"
        "\"국민연금 일찍 받으면 손해 아니에요?\"\n\n"
        "[이미지 ①: 썸네일]\n\n"
        "국민연금 수령나이는 2026년 기준 63세입니다. 1년 당겨 받으면 6% 줄어듭니다.\n\n"
        f"> [요약] {SUMMARY_TITLE}\n> - 수령나이 63세\n> - 1년당 6% 감액\n> - 최대 30%\n> - 연기 1년당 7.2%\n> - 최대 36%\n\n"
        f"{sec}\n\n"
        "## 오늘 바로 할 살림 체크\n\n- 출생연도 확인\n- 예상 연금액 조회\n\n"
        "## 오늘의 살림 정리\n\n당겨 받으면 줄어듭니다.\n\n"
        "## 🐷 새싹돼지 Q&A\n\n> [질문] 다시 늦출 수 있나요?\n> 조건이 있습니다.\n\n"
        "## 근거 자료\n\n- 국민연금법 제61조, 국민연금공단\n\n"
        "#국민연금수령나이 #국민연금 #조기수령 #연기수령 #노령연금 #국민연금감액 #국민연금조기수령 #국민연금연기\n\n"
        "---\n\n## 작성 메모 (발행 시 삭제)\n\n"
        "- 썸네일 유형: scene\n- 글 유형: 선택·비교형\n"
        "- 썸네일 장면: a woman holding a phone at a kitchen table, warm evening light\n"
        "- 썸네일 문구: 일찍 받으면 손해? | 2026 국민연금 수령나이 총정리\n\n"
        "### 수치 근거\n\n| 항목 | 값 | 출처·식 | 확인일 | 상태 |\n|---|---|---|---|---|\n"
        "| 수령나이 | 63세 | 국민연금법 | 2026-10-14 | VERIFIED |\n| 조기 감액 | 1년당 6%, 최대 30% | 공단 | 2026-10-14 | VERIFIED |\n"
        "| 연기 가산 | 7.2%, 최대 36% | 공단 | 2026-10-14 | VERIFIED |\n| 건보료 영향 | 3% | 블로그 | 2026-10-14 | UNVERIFIED |\n"
    )

    def tissues(src, num="15"):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, f"{num}_t.md")
            open(path, "w", encoding="utf-8").write(src)
            n_, b_, c_, _ = parts(path)
            return template_issues(n_, b_, c_, target_keyword(n_)), measure(path, set())

    ti, tm = tissues(tdoc)
    assert ti == [], ti
    assert tm["template"] and not tissues(tdoc, "14")[1]["template"]                   # 14편까지는 템플릿 판정이 없다
    assert any("분량" in i for i in tm["format"]) and not any("시각 요소" in i for i in tm["format"]), tm["format"]

    def fails(old, new, word):
        assert old in tdoc, old
        got = tissues(tdoc.replace(old, new, 1))[0]
        assert any(word in i for i in got), (word, got)
    fails('"국민연금 일찍 받으면 손해 아니에요?"', "국민연금 일찍 받으면 손해일까요.", "따옴표로 감싼 질문")
    fails("[이미지 ①: 썸네일]\n\n", "", "[이미지 ①]")
    fails("## 오늘의 살림 정리", "## 마무리", "`## 오늘의 살림 정리`")
    fails("## 오늘 바로 할 살림 체크", "## 6. 오늘 바로 할 살림 체크", "번호 소제목")     # 15편 발행 때 6을 뺐다
    assert any("근거 자료" in i for i in tissues(tdoc.replace("## 🐷 새싹돼지 Q&A", "## 임시").replace(
        "## 근거 자료", "## 🐷 새싹돼지 Q&A").replace("## 임시", "## 근거 자료"))[0])        # 근거 자료는 맨 끝
    fails("## 3. 소제목삼", "## 소제목삼", "번호 소제목")
    fails("제목: 2026 국민연금", "제목: 국민연금", "앞 15자에 연도")
    fails("확인할 5가지", "확인할 5가지와 그 밖의 여러 이야기", "제목 6")
    fails("5년 당기면 얼마나 깎일까 확인할 5가지", "당기면 얼마나 깎일까 확인할 여러 가지", "연도 말고 숫자")
    fails("얼마나 깎일까", "무조건 깎일까", "금지어")
    fails("> - 최대 36%", "> - 최대 36%\n> - 여섯째 줄 7%", "5줄")
    fails("> - 수령나이 63세", "> - 수령나이 확인", "줄마다 숫자")
    fails(f"> [요약] {SUMMARY_TITLE}", "> [요약] 한눈에 보기", "요약 박스 제목")
    fails("\n\n🪙 살림 메모: 1년당 기준입니다.", "", "살림 메모")
    fails("본문은 6% 감액입니다.", "본문은 9% 감액입니다.", "근거 표에 없는 수치: 9")
    fails("본문은 6% 감액입니다.", "본문은 3% 감액입니다.", "UNVERIFIED 수치")
    fails("| 공단 | 2026-10-14 | VERIFIED |\n| 연기", "| 공단 | 2026-10-14 | 계산 |\n| 연기", "계산 행에 식이 없다")
    fails("### 수치 근거", "### 근거", "수치 근거` 표가 없다")
    fails("- 국민연금법 제61조, 국민연금공단", "- 아래 글 참고", "근거 자료에")
    fails("- 썸네일 유형: scene", "- 썸네일 유형: photo", "썸네일 유형")
    fails("- 글 유형: 선택·비교형", "- 글 유형: 기타", "글 유형")
    fails("warm evening light", "warm evening light, 국민연금", "한글·숫자")
    fails("일찍 받으면 손해?", "일찍 받으면 정말 손해일까요?", "12자")
    fails("일찍 받으면 손해?", "일찍은 못 받습니다", "단정 표현")
    fails("- 썸네일 유형: scene", "- 썸네일 유형: card", "8~12자")
    card = tdoc.replace("- 썸네일 유형: scene", "- 썸네일 유형: card\n- 썸네일 강조 숫자: 6% | 9년 예시").replace(
        "일찍 받으면 손해? | 2026 국민연금 수령나이 총정리", "국민연금 일찍 받으면 | 6% 줄 수 있어요")
    assert tissues(card)[0] == [], tissues(card)[0]
    assert any("강조 숫자" in i for i in tissues(card.replace("강조 숫자: 6%", "강조 숫자: 8%"))[0])
    assert thumb_streak({"15": "card", "16": "card", "17": "card", "18": "scene"}, True) == ["17"]
    assert thumb_streak({"15": "card", "16": "scene", "17": "card", "14": None}, True) == []
    if not CARD_ENABLED:      # card 보류 중: scene 3연속은 통과, card 원고는 막는다
        assert thumb_streak({"15": "scene", "16": "scene", "17": "scene"}) == []
        assert card_paused({"15": "scene", "16": "card", "14": None}) == ["16"]
    assert same_box_title({"15": [SUMMARY_TITLE], "16": [SUMMARY_TITLE]}) == []        # 템플릿 고정 제목은 중복으로 안 본다
    print("selftest ok")


def fetch_benchmark(n=50) -> int:
    """벤치마크 블로그 최근 n편 본문 → BENCH_DIR/{logNo}.txt. 문장을 베끼지 않았는지 대조하는 데만 쓴다(gitignore)."""
    import requests
    from verify_naver import parse
    rss = requests.get(f'https://rss.blog.naver.com/{BENCH_BLOG}.xml', timeout=15).text
    nos = list(dict.fromkeys(re.findall(rf'blog\.naver\.com/{BENCH_BLOG}/(\d+)', rss)))[:n]
    if not nos:
        raise RuntimeError(f'{BENCH_BLOG} RSS에서 글 번호를 못 읽었다 — RSS 형식이 바뀌었을 수 있다')
    os.makedirs(BENCH_DIR, exist_ok=True)
    for no in nos:
        html = requests.get(f'https://m.blog.naver.com/{BENCH_BLOG}/{no}', headers={'User-Agent': 'Mozilla/5.0'}, timeout=15).text
        open(f'{BENCH_DIR}/{no}.txt', 'w', encoding='utf-8').write(parse(html)['text'])
    print(f'{len(nos)}편 → {BENCH_DIR}')
    return 0


def main():
    tistory = sents("".join(open(f, encoding='utf-8').read()
                            for f in glob.glob('_workspace/02_blog_post_*.md')))
    volumes = load_volumes()
    if not volumes:
        print(f'⚠ {VOLUME_CSV} 없음 — 태그 검색량 검사를 건너뜁니다\n')
    bench = sents("".join(open(f, encoding='utf-8').read() for f in glob.glob(f'{BENCH_DIR}/*.txt')))
    allok = True
    cover_kws, box_titles, thumb_kinds = {}, {}, {}
    for p in sorted(glob.glob('content/naver/*.md')):
        r = measure(p, tistory, volumes, bench)
        if r is None:          # 제목 줄이 없으면 원고가 아니다(메모·프롬프트 파일)
            continue
        cover_kws[os.path.basename(p)] = r["cover_kw"]
        box_titles[os.path.basename(p)] = r["boxes"]
        thumb_kinds[os.path.basename(p)] = r["thumb_type"]
        if r["template"] and not bench:
            print(f'⚠ {BENCH_DIR} 비어 있음 — 벤치마크 문장 중복을 못 봤다. `check_naver.py --fetch-benchmark` 후 다시 실행')
        ok = passes(r)
        allok &= ok
        print(('OK   ' if ok else 'CHECK'), os.path.basename(p))
        print(f"       {r['chars']}자 / 소제목 {r['heads']} / 이미지 {r['images']} / 표 {r['tables']}"
              f"{' / 박스 ' + str(len(r['boxes'])) if r['boxes'] else ''}"
              f" / 경험 {r['exp']} / 내부링크 {r['links']}"
              f" / 태그 {len(r['tags'])} / 티스토리 중복 {len(r['dup'])}")
        print(f"       제목: {r['title']}")
        known = {t: v for t, v in r["vol"].items() if v}
        if known:
            top = sorted(known.items(), key=lambda x: -x[1])[:4]
            unknown = len(r["vol"]) - len(known)
            line = ' '.join(f'{t}({v:,})' for t, v in top)
            print(f'       검색량 상위: {line}'
                  + (f' · 나머지 {unknown}개는 CSV 미수록(미확인)' if unknown else ''))
        for t in r["stale"]:
            print('         옛 명칭:', t)
        if r["geo_required"] and len(r["geo"]) < MIN_GEO_QUERIES:
            print(f'         GEO: 작성 메모에 `- GEO 질의: a | b` 줄이 없거나 {MIN_GEO_QUERIES}개 미만이다')
        for t in r["format"]:
            print('         형식:', t)
        if r["judged"]:
            for t in r["structure"]:
                print('         구조:', t)
        elif r["structure"]:
            print(f'         (발행됨 — 판정 제외) 구조 {len(r["structure"])}건')
        for d in list(r["dup"])[:3]:
            print('         중복:', d[:55])
        for d in list(r["bench_dup"])[:3]:
            print('         벤치마크 문장과 같다:', d[:55])
    for a, b in same_cover_kw(cover_kws):
        allok = False
        print(f'CHECK 대표사진 검색어가 같다: {a} = {b} — 후보가 똑같이 나온다')
    for name in thumb_streak(thumb_kinds):
        allok = False
        print(f'CHECK 썸네일 유형이 3편 연속 같다: {name}까지')
    for name in card_paused(thumb_kinds):
        allok = False
        print(f'CHECK {name} — card 썸네일은 보류 중이다(CARD_ENABLED). scene으로 만든다')
    for a, b, t in same_box_title(box_titles):
        allok = False
        print(f'CHECK 박스 제목이 같다: {a} = {b} — "{t}"')
    print('\n전체 통과' if allok else '\n확인 필요')
    return 0 if allok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--fetch-benchmark" in sys.argv:
        sys.exit(fetch_benchmark())
    else:
        sys.exit(main())
