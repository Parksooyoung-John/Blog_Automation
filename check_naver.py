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


def template_issues(md: str, body: str, text: str, keyword, quality: bool = False, v2: bool = False) -> list:
    """15편부터의 벤치마크 템플릿. body: 플레이스홀더가 남은 본문, text: 플레이스홀더를 뺀 본문. → 문제 설명 목록

    quality(27편~): 섹션 고정 순서·번호 1~5 대신 quality_issues()가 구조를 본다.
    """
    issues = []
    blocks = [x.strip() for x in re.split(r'\n\s*\n', body) if x.strip() and not re.fullmatch(r'-{3,}', x.strip())]
    title = re.search(r'^제목: (.+)$', md, re.M).group(1).strip()

    # G1 순서: 훅 → 썸네일 → (도입) → 요약 → 1~5 → 6 체크 → 정리 → 근거 → Q&A
    if not blocks or not re.fullmatch(r'"[^"\n]{2,40}\?"', blocks[0]):
        issues.append('본문 첫 줄이 따옴표로 감싼 질문("…?", 40자 이하)이 아니다')
    if len(blocks) < 2 or not blocks[1].startswith('[이미지 ①'):
        issues.append('질문 바로 다음이 [이미지 ①] 썸네일이 아니다')
    order = [("요약 박스", lambda x: is_box(x) and BOX_RE.match(x).group(1) == '요약')]
    if not quality:
        order += [(f"## {i}.", lambda x, i=i: x.startswith(f'## {i}. ')) for i in range(1, 6)]
        order += [(f"## {h}", lambda x, h=h: x == f'## {h}') for h in FIXED_HEADS]
    pos = 0
    for name, ok in order:
        i = next((k for k in range(pos, len(blocks)) if ok(blocks[k])), None)
        if i is None:
            issues.append(f'템플릿 순서: `{name}`이(가) 없거나 앞 블록보다 먼저 나온다')
        else:
            pos = i + 1
    # G4 번호 소제목은 정확히 1~5 (27편부터는 1부터 이어지는 3~6개)
    nums = re.findall(r'^## (\d+)\. ', body, flags=re.M)
    if quality:
        if not (QUALITY_SECTIONS[0] <= len(nums) <= QUALITY_SECTIONS[1] and nums == [str(i) for i in range(1, len(nums) + 1)]):
            issues.append(f'번호 소제목이 {", ".join(nums) or "없음"} — 1부터 이어지는 {QUALITY_SECTIONS[0]}~{QUALITY_SECTIONS[1]}개')
        heads = re.findall(r'^## (.+?)\s*$', body, flags=re.M)
        if heads and heads[-1] != '근거 자료':
            issues.append('`## 근거 자료`가 맨 끝 소제목이 아니다')
    elif nums != [str(i) for i in range(1, 6)]:
        issues.append(f'번호 소제목이 {", ".join(nums) or "없음"} — 1~5여야 한다')

    # G2 제목
    if v2:      # 길이는 v2_issues가 경고만 한다. 일정형 제목에는 연도 말고 숫자가 없을 수 있다
        if keyword and not 0 <= title.replace(' ', '').find(keyword) < 30:
            issues.append(f'제목 앞 30자에 목표 키워드({keyword})가 없다')
        if '|' in title:
            issues.append('제목 구분자는 `｜` 또는 `:`')
    else:
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
    if kind not in (THUMB_TYPES + V2_THUMBS if v2 else THUMB_TYPES):
        issues.append(f'작성 메모 `- 썸네일 유형:`이 {"·".join(THUMB_TYPES)} 중 하나가 아니다')
    if post_type not in POST_TYPES:
        issues.append(f'작성 메모 `- 글 유형:`이 {"·".join(POST_TYPES)} 중 하나가 아니다')
    lines = thumb_lines(md)
    if lines:
        a, b = lines
        if kind == 'card' and not (8 <= len(a) <= 12 and 8 <= len(b) <= 12):
            issues.append(f'card 썸네일 문구는 두 줄 각 8~12자 (지금 {len(a)}·{len(b)}자)')
        elif not v2 and (len(a) > 12 or len(b) > 22):      # 30편부터는 v2_thumb_issues가 본다
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


# 품질 강화(2026-10-28, 27편부터). 근거: Donsallimpyo_Harness_Content_Quality_Upgrade.md + 사용자 YAML 규칙.
# 15~26편이 같은 제목 꼬리("확인할 5가지")·표 5개·태그 10개로 찍혀 나왔고, [경험 한 줄] A안이 AI가 쓴 1인칭이었다.
QUALITY_FROM = 27
QUALITY_SECTIONS = (3, 6)
MAX_TABLES = 3
MAX_INFO_BOXES = 2                  # 요약·안내·주의 합계. [질문]은 FAQ_RANGE가 따로 센다
FAQ_RANGE = (2, 3)
TAG_RANGE = (3, 5)
BANNED_SUFFIX = ("확인할 5가지", "총정리")
TITLE_REPEAT = (2, 5)               # 같은 제목 뼈대는 새 글 포함 최근 5편 중 2편까지
# ponytail: 조건어 목록 휴리스틱 — 구체 상황이 있는데 걸리지 않는 제목이 나오면 목록을 늘린다
SITUATION_RE = re.compile(r'받는|사는|있는|없는|넘는|넘으면|했을 때|하면|못 받|안 받|맞벌이|퇴사|이직|중인|후에|전에|때')
ORIGINALITY = ("primary_source_comparison", "verified_calculation", "verified_screen_path", "real_experience")
FIRST_PERSON_RE = re.compile(r'(?<![가-힣])(저는|제가|저도|저희|나는|내가)(?![가-힣])|직접 (신청|사용|받아|해) ?보|해 ?보니|더라고요|더라구요'
                             r'|실제로 환급받았|담당자에게 (확인|물어) ?보니|세무서에 문의해 ?보니')
PRIMARY_DOMAINS = ("nts.go.kr", "hometax.go.kr", "law.go.kr", "korea.kr", "gov.kr", "bokjiro.go.kr", "nps.or.kr",
                   "nhis.or.kr", "ei.go.kr", "work24.go.kr", "moel.go.kr", "mohw.go.kr", "moef.go.kr", "comwel.or.kr")
GUARANTEE_RE = re.compile(r'무조건 (받|환급|돌려)|100% (환급|받|돌려)|반드시 (받|환급)을? 수|확실히 (받|환급)')
CLICK_RE = re.compile(r'광고.{0,8}(클릭|눌러)|클릭해 주세요')
HYPOTHETICAL_RE = re.compile(r'가상|예시|계산 예|가정')
# V2(2026-10-31, 30편부터) — 최신성·제목. 명세 NAVER_BLOG_HARNESS_TOPIC_FRESHNESS_TITLE_CA_V2.md. 29편이 열린 서비스를 "열리기 전"으로 썼다.
V2_FROM = 30
V2_THUMBS = ("number", "compare", "action")      # 코드로 글자를 얹는 정보 카드. scene은 AI 배경 + 코드 글자로만 쓴다
CATEGORY_COLORS = {"tax": "#006064", "pension": "#2e7d32", "support": "#5b2c6f", "warning": "#a0461a", "card": "#1a3c6e"}
MASCOT_POSES = ("explain", "calculator", "check", "warning", "curious")
MAX_SCENE_IN_9 = 3
JUDGE_COPY_RE = re.compile(r'\d|O|X|vs|될까|되나|가능|불가|계산|확인|수정|신청|오픈|조건|기준|차이')
FRESH_HOURS = 24
TITLE_SOFT = (25, 40)               # 명세 7.5 권장 범위. 표시 환경마다 달라 탈락시키지 않고 경고만 한다
INTENTS = ("definition", "how_to", "calculation", "decision", "comparison", "warning_correction", "event_opening", "experience_review")
TIME_ROW_RE = re.compile(r'개통|기간|마감|기한|신청일|지급일|일정|시행')
PRESS_SOURCE_RE = re.compile(r'기사|보도|블로그|이코노미|뉴스|일보|신문|티스토리')
RELATIVE_RE = re.compile(r'아직|곧 |내일부터|작년|지난해|어제|이번 주')
YEAR_MIX_RE = re.compile(r'(20\d\d)년 귀속[^.\n]{0,30}\1년 (?:1월|초)')
UNOPENED_RE = re.compile(r'아직.{0,12}(개통|발표|공지|공고)|(개통|발표|공지|공고)\S* ?(소식을 )?확인하지 못')


def title_skeleton(title: str) -> str:
    """제목 뼈대 — 키워드가 놓이는 `|` 앞을 지우고 숫자를 N으로. `확인할 5가지`류 꼬리가 반복되는지 본다."""
    tail = re.split(r'[|｜:]', title, maxsplit=1)[-1]
    tail = re.sub(r'\d+(?:[.,]\d+)*', 'N', tail)
    return re.sub(r'.*[?？]\s*', '?', tail).strip()      # 질문 뒤 꼬리가 반복의 정체다


def section_skeleton(body: str) -> list:
    """소제목 구성 — 번호는 #, 고정 소제목은 그대로, 나머지는 *."""
    out = []
    for h in re.findall(r'^## (.+?)\s*$', body, flags=re.M):
        out.append('#' if re.match(r'\d+\. ', h) else h if h in FIXED_HEADS else '*')
    return out


def card_numbers(body: str) -> dict:
    """원고가 참조한 카드 → 카드 글자의 숫자. 카드 출처 줄(sub)은 뺀다."""
    names = re.findall(r'assets/naver_img/(\d+_[^`\s\]]+?)\.png', body)
    names = [n for n in names if not n.split('_', 1)[1].startswith('썸네일')]
    if not names:
        return {}
    from make_naver_images import CARDS
    out = {}
    for n in names:
        c = CARDS.get(n)
        if c is None:
            continue
        strs = [c.args[0]] + [x for a in c.args[2:] for x in (a if isinstance(a, (list, tuple)) else [a])]
        flat = [y for x in strs for y in (x if isinstance(x, tuple) else [x]) if isinstance(y, str)]
        out[n] = _nums(' '.join(flat))
    return out


def quality_issues(md: str, body: str, text: str, tags: list, v2: bool = False) -> list:
    """27편부터의 품질 규칙. body: 플레이스홀더가 남은 본문, text: 플레이스홀더를 뺀 본문. → 문제 설명 목록"""
    issues = []
    title = re.search(r'^제목: (.+)$', md, re.M).group(1).strip()
    blocks = [x.strip() for x in re.split(r'\n\s*\n', body) if x.strip()]

    issues += [f'제목 꼬리 금지: {s}' for s in BANNED_SUFFIX if s in title]
    if not v2 and not SITUATION_RE.search(title):      # 30편부터는 title_gate가 본다. `10월 28일 오픈`처럼 조건어 없는 일정형 제목이 있다
        issues.append('제목에 구체 상황(받는·사는·넘으면·했을 때 등)이 없다')

    tables = sum(is_table(b) for b in blocks)
    if tables > MAX_TABLES:
        issues.append(f'표 {tables}개 ({MAX_TABLES}개 이하)')
    kinds = [BOX_RE.match(b).group(1) for b in blocks if is_box(b)]
    info = sum(k in ('요약', '안내', '주의') for k in kinds)
    if info > MAX_INFO_BOXES:
        issues.append(f'요약·안내·주의 박스 {info}개 ({MAX_INFO_BOXES}개 이하)')
    faq = kinds.count('질문')
    if not FAQ_RANGE[0] <= faq <= FAQ_RANGE[1]:
        issues.append(f'FAQ(`> [질문]`) {faq}개 ({FAQ_RANGE[0]}~{FAQ_RANGE[1]}개)')
    if not TAG_RANGE[0] <= len(tags) <= TAG_RANGE[1]:
        issues.append(f'태그 {len(tags)}개 ({TAG_RANGE[0]}~{TAG_RANGE[1]}개)')

    # 고유 근거 — 하나 이상, 값마다 뒷받침이 있어야 한다
    rows = facts(md)
    sources = re.findall(r'^- 출처:.*$', md, flags=re.M)
    primary = [s for s in sources if any(d in s for d in PRIMARY_DOMAINS)]
    modes = [m.strip() for m in (memo_value(md, '고유 근거') or '').split('|') if m.strip()]
    real = bool((memo_value(md, '실제 경험') or '').strip())
    if not any(m in ORIGINALITY for m in modes):
        issues.append(f'EVIDENCE_REQUIRED — 작성 메모 `- 고유 근거:`가 {" · ".join(ORIGINALITY)} 중 하나 이상이 아니다')
    for m in modes:
        if m not in ORIGINALITY:
            issues.append(f'고유 근거 값이 목록에 없다: {m}')
        elif m == 'verified_calculation' and not any(r[4] == '계산' and _nums(r[1]) & _nums(text) for r in rows):
            issues.append('verified_calculation인데 본문에 쓰인 `계산` 행이 없다')
        elif m == 'primary_source_comparison' and not (len(primary) >= 2 and tables >= 1):
            issues.append('primary_source_comparison인데 1차 출처 2개 + 비교표가 없다')
        elif m == 'verified_screen_path' and not (re.search(r'\d{4}-\d\d-\d\d', memo_value(md, '화면 확인') or '')
                                                  and re.search(r'\[이미지[^\]]*캡처', body)):
            issues.append('verified_screen_path인데 `- 화면 확인: YYYY-MM-DD`나 캡처 이미지 자리가 없다')
        elif m == 'real_experience' and not real:
            issues.append('real_experience인데 `- 실제 경험:`(사용자가 쓴 경험)이 비어 있다')

    # 허위 1인칭 — 본문은 실제 경험 메모가 있을 때만, [경험 한 줄] A안은 항상 3인칭
    if not real and (m := FIRST_PERSON_RE.search(text)):
        issues.append(f'경험 입력 없이 1인칭 체험 표현: "{m.group(0)}" — 공식자료·가상 사례 표현으로 바꾼다')
    for a in re.findall(r'\[경험 한 줄[^\]]*?A안[^:]*:\s*([^|\]]+)', body):
        if FIRST_PERSON_RE.search(a):
            issues.append(f'[경험 한 줄] A안이 1인칭이다: {a.strip()[:24]}… — A안은 3인칭만')

    if len(primary) < 2:
        issues.append(f'1차 기관 출처(`- 출처:` 중 {PRIMARY_DOMAINS[0]} 등) {len(primary)}개 (2개 이상)')

    # 가상 사례 표시 — 항목에 `가상`·`사례`·`예`를 적은 계산 행의 값이 나오는 섹션에는 가상·예시라고 쓴다.
    # 출생연도처럼 공식 값에서 계산만 한 행은 가상 사례가 아니라서 뺀다.
    verified = set().union(*(_nums(r[1]) for r in rows if r[4] == 'VERIFIED'))
    calc = set().union(*(_nums(r[1]) for r in rows if r[4] == '계산' and re.search(r'가상|사례|예', r[0]))) - verified
    for sec in text.split('\n## ')[1:]:
        used = {x.group(1) for x in UNIT_NUM.finditer(sec)}
        if used & calc and not HYPOTHETICAL_RE.search(sec):
            issues.append(f'계산 값이 있는 섹션에 가상 사례·예시 표시가 없다: {sec.splitlines()[0][:20]}')

    # "아직 안 열렸다"류는 쓰는 날 다시 찾았다는 기록이 있어야 한다 — 29편이 10-28에 열린 서비스를 10-30에 미개통으로 썼다
    if (m := UNOPENED_RE.search(text)) and not re.match(r'\d{4}-\d\d-\d\d \| \S', memo_value(md, '일정 재확인') or ''):
        issues.append(f'"{m.group(0)}" — 올해 이름·날짜로 다시 검색하고 `- 일정 재확인: YYYY-MM-DD | 검색어`를 적는다')

    # Hard Block
    if m := GUARANTEE_RE.search(text):
        issues.append(f'결과 보장 표현: "{m.group(0)}"')
    if m := CLICK_RE.search(text):
        issues.append(f'광고·클릭 유도 표현: "{m.group(0)}"')
    for name, nums in card_numbers(body).items():
        if nums - _nums(text):
            issues.append(f'카드에만 있는 숫자({name}): {", ".join(sorted(nums - _nums(text)))} — 본문에도 쓴다')
    return issues


def freshness_time(md: str):
    """`- 최신성 재확인: YYYY-MM-DD HH:MM | 검색어 | 출처` → datetime. 세 칸이 다 없으면 None."""
    import datetime
    parts = [x.strip() for x in (memo_value(md, '최신성 재확인') or '').split('|')]
    if len(parts) < 3 or not all(parts):
        return None
    try:
        return datetime.datetime.strptime(parts[0], '%Y-%m-%d %H:%M')
    except ValueError:
        return None


def title_gate_issue(path: str, title: str) -> list:
    """원고 제목이 title_gate가 고른 제목과 같아야 한다. 판정 결과 파일은 `_titles/NN.json`."""
    import json
    name = os.path.basename(path)[:2]
    gate = os.path.join(os.path.dirname(path), '_titles', f'{name}.json')
    if not os.path.exists(gate):
        return [f'제목 게이트 결과가 없다: _titles/{name}.json — `title_gate.py {name}`']
    selected = json.load(open(gate, encoding='utf-8')).get('selected_title', '')
    if selected != title:
        return [f'원고 제목이 게이트 선정 제목과 다르다: {selected or "선정 없음"}']
    return []


def v2_thumb_issues(md: str, text: str) -> list:
    """30편부터의 대표사진 카피. SEO 제목과 분리하고, 숫자는 제목·본문과 같아야 한다."""
    issues = []
    title = re.search(r'^제목: (.+)$', md, re.M).group(1).strip()
    kind = memo_value(md, '썸네일 유형')
    lines = thumb_lines(md)
    if not lines:
        return ['작성 메모 `- 썸네일 문구: 메인 | 서브`가 없다']
    main, sub = (re.sub(r'\s', '', x) for x in lines)
    squeezed = re.sub(r'[\s|｜:]', '', title)
    if len(main) + len(sub) >= 0.8 * len(squeezed) or (main + sub) in squeezed:
        issues.append('REJECT_TITLE_COPY_AS_THUMBNAIL — SEO 제목을 그대로 넣었다. 메인 12자 내외 + 서브 한 줄로 다시 쓴다')
    if len(main) > 12:
        issues.append(f'메인 카피 {len(main)}자 (12자 이내)')
    if len(sub) > 14:
        issues.append(f'서브 카피 {len(sub)}자 (한 줄 14자 이내)')
    if not JUDGE_COPY_RE.search(lines[0]):
        issues.append('메인 카피에 숫자·판정·행동이 없다')
    big = (memo_value(md, '썸네일 강조 숫자') or '').split('|')[0].strip()
    if kind in ('number', 'action') and not big:
        issues.append(f'{kind}인데 `- 썸네일 강조 숫자:`가 없다')
    if missing := unit_nums(' '.join(lines) + ' ' + big) - unit_nums(title + ' ' + text):
        issues.append('BLOCKED_THUMBNAIL_FACT_MISMATCH — 제목·본문에 없는 숫자: ' + ', '.join(a + b for a, b in sorted(missing)))
    if memo_value(md, '카테고리 색') not in CATEGORY_COLORS:
        issues.append(f'작성 메모 `- 카테고리 색:`이 {" · ".join(CATEGORY_COLORS)} 중 하나가 아니다')
    if memo_value(md, '돼지 자세') not in MASCOT_POSES + ('없음',):
        issues.append(f'작성 메모 `- 돼지 자세:`가 {" · ".join(MASCOT_POSES)} · 없음 중 하나가 아니다')
    if kind == 'scene' and not memo_value(md, 'AI 사용 이유'):
        issues.append('scene인데 `- AI 사용 이유:`가 없다 — 숫자·표·사물로 안 되는 이유를 적는다')
    return issues


def thumb_v2_repeat(rows: dict) -> list:
    """편 번호 → (유형, 돼지 자세). 30편부터 최근 9개 AI 3개 초과·같은 유형/자세 3연속이면 → [(편, 이유)]."""
    seq = sorted((int(k), v) for k, v in rows.items() if v[0])
    out = []
    for i, (n, (kind, pose)) in enumerate(seq):
        if n < V2_FROM:
            continue
        window = [v for _, v in seq[max(0, i - 8):i + 1]]
        if kind == 'scene' and sum(k == 'scene' for k, _ in window) > MAX_SCENE_IN_9:
            out.append((n, f'최근 9개 중 AI 대표사진이 {MAX_SCENE_IN_9}개를 넘는다 — 숫자·비교·자격 카드로 만든다'))
        last3 = [v for _, v in seq[max(0, i - 2):i + 1]]
        if len(last3) == 3 and len({k for k, _ in last3}) == 1:
            out.append((n, f'대표사진 유형 {kind}이(가) 3연속이다'))
        if len(last3) == 3 and pose and pose != '없음' and all(p == pose for _, p in last3):
            out.append((n, f'돼지 자세 {pose}이(가) 3연속이다'))
    return out


def unit_nums(s: str) -> set:
    return {(m.group(1), m.group(2).replace(' ', '')) for m in UNIT_NUM.finditer(s)
            if not (m.group(2) == '년' and re.fullmatch(r'20\d\d', m.group(1)))}


def v2_issues(md: str, body: str, text: str) -> tuple:
    """30편부터의 최신성·제목 규칙. → (실패 목록, 경고 목록)"""
    issues, warns = [], []
    title = re.search(r'^제목: (.+)$', md, re.M).group(1).strip()

    # 날짜·기간은 1차 기관 근거 — 기사·블로그는 변경 사실을 찾는 데만 쓴다(명세 6.1)
    for r in facts(md):
        if r[4] == 'VERIFIED' and TIME_ROW_RE.search(r[0] + r[1]) and PRESS_SOURCE_RE.search(r[2]):
            issues.append(f'BLOCKED_NEEDS_REVIEW — 일정 근거가 기사·블로그뿐이다: {r[0]} ({r[2][:24]})')
    if freshness_time(md) is None:
        issues.append('작성 메모 `- 최신성 재확인: YYYY-MM-DD HH:MM | 검색어 | 출처`가 없다')

    # 제목의 숫자·단위는 본문에 그대로 있어야 한다 (2년과 2개월 충돌)
    for n, u in sorted(unit_nums(title) - unit_nums(text)):
        issues.append(f'BLOCKED_NEEDS_REVIEW — 제목의 {n}{u}이(가) 본문에 없다')
    if m := YEAR_MIX_RE.search(text):
        issues.append(f'귀속연도와 신고연도가 섞였다: {m.group(0)[:30]}')

    intent = memo_value(md, '검색 의도')
    if intent not in INTENTS:
        issues.append(f'작성 메모 `- 검색 의도:`가 {" · ".join(INTENTS)} 중 하나가 아니다')
    if len([x for x in (memo_value(md, '보조 의도') or '').split('|') if x.strip()]) > 2:
        issues.append('보조 의도는 2개까지다')

    if not TITLE_SOFT[0] <= len(title) <= TITLE_SOFT[1]:
        warns.append(f'제목 {len(title)}자 (권장 {TITLE_SOFT[0]}~{TITLE_SOFT[1]}자, 핵심은 앞 30자)')
    warns += [f'상대 표현 — 발행일에 다시 볼 것: {ln.strip()[:40]}'
              for ln in text.split('\n') if RELATIVE_RE.search(ln) and not ln.startswith('|')]
    return issues, warns


def title_repeat(titles: dict) -> list:
    """편 번호 순 제목 → 27편부터, 새 글 포함 최근 5편 중 같은 뼈대가 3편 이상인 원고."""
    seq = sorted((int(k), v) for k, v in titles.items() if v)
    keep, win = TITLE_REPEAT
    out = []
    for i, (n, t) in enumerate(seq):
        if n < QUALITY_FROM:
            continue
        sk = title_skeleton(t)
        if sum(title_skeleton(x) == sk for _, x in seq[max(0, i - win + 1):i + 1]) > keep:
            out.append(n)
    return out


def section_repeat(skels: dict) -> list:
    """편 번호 순 소제목 구성 → 27편부터, 바로 앞 편과 구성이 같은 원고."""
    seq = sorted((int(k), v) for k, v in skels.items() if v)
    return [n for (p, a), (n, b) in zip(seq, seq[1:]) if n >= QUALITY_FROM and a == b]


# scene 썸네일 구도(2026-10-16). 15~17편이 전부 '식탁에 앉아 턱 괴기'로 나왔다 — 작성 메모 `- 썸네일 구도:`에서
# 하나를 고르고, 바로 앞 편과 같은 구도는 막는다. 값은 make_naver_images가 프롬프트에 넣는 영어 촬영 지시다.
COMPOSITION_FROM = 16      # 15편은 구도 줄 없이 발행됐다
COMPOSITIONS = {
    "상반신 클로즈업": "close-up of one person from the chest up, facing the viewer, expressive face, softly blurred background",
    "서서 걷는 장면": "full-body shot of the person standing or walking, for example on a street, in a hallway or at a building entrance",
    "창가 옆모습": "side view of the person standing by a large window in natural daylight",
    "소파에 기댄 자세": "wide room view of the person leaning back on a sofa in a relaxed posture",
    "마주 앉은 두 사람": "two people facing each other and talking, over-the-shoulder view",
    "위에서 내려다본 책상": "top-down view of a desk with hands holding papers or a phone; faces are not the focus",
    "야외 장면": "outdoor scene such as a park, a bus stop, a parking lot or in front of a building",
    "창구 앞": "person standing at a service counter or reception desk, seen from the side",
}


def composition_repeat(comps: dict) -> list:
    """편 번호 순 구도 → 바로 앞 편과 같은 구도를 쓴 원고. 구도 줄이 없는 편(15편 이전)은 건너뛴다."""
    seq = [(k, v) for k, v in sorted(comps.items()) if v]
    return [seq[i][0] for i in range(1, len(seq)) if seq[i][1] == seq[i - 1][1]]


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
        "quality": bool(num) and int(num.group()) >= QUALITY_FROM,
        "skeleton": section_skeleton(b),
        "v2": bool(num) and int(num.group()) >= V2_FROM,
        "warn": [],
        "thumb_type": memo_value(n, '썸네일 유형'),
        "composition": memo_value(n, '썸네일 구도'),
    }
    if r["template"]:          # 소제목 9개 중 번호 1~5만 본문 구간이다 — 분량·시각 요소·소제목 문구는 그 다섯으로 본다
        numbered = re.findall(r'^## \d+\. (.+?)\s*$' if r["quality"] else r'^## [1-5]\. (.+?)\s*$', b, flags=re.M)
        r["format"] = format_issues(r["chars"], len(numbered) if r["quality"] else 5, r["images"], tables, r["thumb"],
                                    LENGTH_TEMPLATE)
        r["format"] += heading_issues(numbered)
        r["format"] += template_issues(n, b, c, target_keyword(n), r["quality"], r["v2"])
        if r["quality"]:
            r["format"] += quality_issues(n, b, c, tags, r["v2"])
        if r["v2"]:
            fails_, r["warn"] = v2_issues(n, b, c)
            r["format"] += fails_ + title_gate_issue(path, r["title"].strip()) + v2_thumb_issues(n, c)
        if int(num.group()) >= COMPOSITION_FROM and r["thumb_type"] == "scene" and r["composition"] not in COMPOSITIONS:
            r["format"].append(f'작성 메모 `- 썸네일 구도:`가 목록에 없다 — {" · ".join(COMPOSITIONS)}')
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
            and r["exp"] >= 1 and r["links"] >= 1 and (r["quality"] or 8 <= len(r["tags"]) <= 12)
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
    # 썸네일 구도: 바로 앞 편과 같으면 막고, 16편부터는 목록에 있어야 한다
    assert composition_repeat({"15": None, "16": "야외 장면", "17": "야외 장면", "18": "창구 앞"}) == ["17"]
    assert composition_repeat({"16": "야외 장면", "17": "창구 앞", "18": "야외 장면"}) == []
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "16_t.md")
        open(path, "w", encoding="utf-8").write(tdoc)          # tdoc은 scene인데 구도 줄이 없다
        assert any("썸네일 구도" in i for i in measure(path, set())["format"])
        open(path, "w", encoding="utf-8").write(tdoc + "- 썸네일 구도: 야외 장면\n")
        assert not any("썸네일 구도" in i for i in measure(path, set())["format"])
    if not CARD_ENABLED:      # card 보류 중: scene 3연속은 통과, card 원고는 막는다
        assert thumb_streak({"15": "scene", "16": "scene", "17": "scene"}) == []
        assert card_paused({"15": "scene", "16": "card", "14": None}) == ["16"]
    assert same_box_title({"15": [SUMMARY_TITLE], "16": [SUMMARY_TITLE]}) == []        # 템플릿 고정 제목은 중복으로 안 본다

    # 27편부터의 품질 규칙 — 표 3·박스 2·FAQ 2·태그 4, 고유 근거·1차 출처·가상 표시
    qsec = "\n\n".join(
        f"## {i}. 소제목{'일이삼사'[i - 1]} 결론입니다\n\n[이미지 {'②③④⑤'[i - 1]}: 카드]\n\n본문은 6% 감액입니다.\n\n"
        + ("| 구분 | 값 |\n|---|---|\n| 조기 | **6%** |\n\n🪙 살림 메모: 1년당 기준입니다.\n\n" if i <= 3 else "")
        + "결론 한 줄입니다.\n\n---" for i in range(1, 5))
    qdoc = (
        "제목: 2026 국민연금 일찍 받는 사람 | 5년 당기면 얼마나 깎일까? 63세 기준으로 계산\n\n---\n\n"
        "\"국민연금 일찍 받으면 손해 아니에요?\"\n\n[이미지 ①: 썸네일]\n\n"
        "국민연금 수령나이는 2026년 기준 63세입니다. 1년 당겨 받으면 6% 줄어듭니다.\n\n"
        f"> [요약] {SUMMARY_TITLE}\n> - 수령나이 63세\n> - 1년당 6% 감액\n> - 최대 30%\n> - 연기 1년당 7.2%\n> - 최대 36%\n\n"
        f"{qsec}\n\n"
        "## 가상 사례로 계산하면\n\n가상 사례입니다. 월 100만원이면 70만원을 받습니다.\n\n"
        "[경험 한 줄 ① | A안(사실 — 그대로 써도 됨): 공식자료에서 가장 헷갈리는 부분은 감액률입니다. | B안(실제로 그랬을 때만): 저는 공단에 문의한 적이 있어요.]\n\n"
        "## 🐷 새싹돼지 Q&A\n\n> [질문] 다시 늦출 수 있나요?\n> 조건이 있습니다.\n\n> [질문] 감액은 평생인가요?\n> 그렇습니다.\n\n"
        "## 근거 자료\n\n- 국민연금법 제61조, 국민연금공단\n\n"
        "#국민연금수령나이 #국민연금 #조기수령 #노령연금\n\n"
        "---\n\n## 작성 메모 (발행 시 삭제)\n\n"
        "- 썸네일 유형: scene\n- 글 유형: 선택·비교형\n- 썸네일 구도: 야외 장면\n"
        "- 썸네일 장면: a woman holding a phone at a kitchen table, warm evening light\n"
        "- 썸네일 문구: 일찍 받으면 손해? | 2026 국민연금 수령나이\n"
        "- 고유 근거: verified_calculation | primary_source_comparison\n"
        "- 출처: 국민연금공단 | 조기노령연금 | https://www.nps.or.kr/a | 2026-10-28\n"
        "- 출처: 정책브리핑 | 연금 안내 | https://www.korea.kr/b | 2026-10-28\n\n"
        "### 수치 근거\n\n| 항목 | 값 | 출처·식 | 확인일 | 상태 |\n|---|---|---|---|---|\n"
        "| 수령나이 | 63세 | 국민연금법 | 2026-10-14 | VERIFIED |\n| 조기 감액 | 1년당 6%, 최대 30% | 공단 | 2026-10-14 | VERIFIED |\n"
        "| 연기 가산 | 7.2%, 최대 36% | 공단 | 2026-10-14 | VERIFIED |\n"
        "| 가상 사례 수령액 | 월 100만원 → 70만원 | 100 × (1 − 0.3) = 70 | 2026-10-28 | 계산 |\n"
    )

    def qissues(src, num="27"):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, f"{num}_t.md")
            open(path, "w", encoding="utf-8").write(src)
            n_, b_, c_, tg = parts(path)
            return quality_issues(n_, b_, c_, tg) + template_issues(n_, b_, c_, target_keyword(n_), True), measure(path, set())

    qi, qm = qissues(qdoc)
    assert qi == [], qi
    assert qm["quality"] and not qissues(qdoc, "26")[1]["quality"]                      # 26편까지는 품질 규칙이 없다

    def qfails(old, new, word):
        assert old in qdoc, old
        got = qissues(qdoc.replace(old, new, 1))[0]
        assert any(word in i for i in got), (word, got)
    qfails("63세 기준으로 계산", "확인할 5가지", "제목 꼬리 금지")
    qfails("일찍 받는 사람", "조기수령", "구체 상황")
    qfails("결론 한 줄입니다.\n\n---\n\n## 4.", "| a | b |\n|---|---|\n| 1 | 2 |\n\n🪙 살림 메모: 표.\n\n---\n\n## 4.", "표 4개")
    qfails("## 근거 자료", "> [안내] 안내\n> - 줄\n\n> [주의] 주의\n> - 줄\n\n## 근거 자료", "박스 3개")
    qfails("> [질문] 감액은 평생인가요?", "> [질문] 셋?\n> 네.\n\n> [질문] 넷?\n> 네.\n\n> [질문] 감액은 평생인가요?", "FAQ(`> [질문]`) 4개")
    qfails("#노령연금", "#노령연금 #가 #나", "태그 6개")
    qfails("- 출처: 정책브리핑 | 연금 안내 | https://www.korea.kr/b", "- 출처: 블로그 | 후기 | https://blog.naver.com/x", "1차 기관 출처")
    qfails("- 고유 근거: verified_calculation | primary_source_comparison", "- 고유 근거: 없음", "EVIDENCE_REQUIRED")
    qfails("- 고유 근거: verified_calculation", "- 고유 근거: real_experience", "실제 경험")
    # T1 경험 입력 없이 1인칭 → 실패, 실제 경험 메모가 있으면 통과
    qfails("가상 사례입니다. 월", "제가 직접 신청해 보니 월", "1인칭 체험")
    qfails("가장 헷갈리는 부분은 감액률입니다.", "계산해 보니 감액이 크더라고요.", "A안이 1인칭")
    assert not any("1인칭" in i for i in qissues(qdoc.replace("가상 사례입니다. 월", "제가 직접 신청해 보니 월").replace(
        "- 고유 근거:", "- 실제 경험: 2025년에 공단에 직접 신청했다\n- 고유 근거:"))[0])
    # T2 가상 사례 값이 나오는 섹션에 가상·예시 표시가 없으면 실패
    qfails("## 가상 사례로 계산하면\n\n가상 사례입니다.", "## 받는 돈 계산\n\n정리하면 이렇습니다.", "가상 사례·예시 표시")
    assert qissues(qdoc.replace("가상 사례입니다.", "정리하면 이렇습니다."))[0] == []      # 소제목에 가상이 있으면 된다
    # T7·Hard Block
    qfails("조건이 있습니다.", "아직 개통 소식을 확인하지 못했습니다.", "일정 재확인")
    assert not any("일정 재확인" in i for i in qissues(qdoc.replace("조건이 있습니다.", "아직 개통 소식을 확인하지 못했습니다.").replace(
        "- 고유 근거:", "- 일정 재확인: 2026-10-31 | 2026 연말정산 미리보기 개통\n- 고유 근거:"))[0])
    qfails("조건이 있습니다.", "무조건 받을 수 있습니다.", "결과 보장")
    qfails("조건이 있습니다.", "광고를 클릭해 주세요.", "클릭 유도")
    qfails("## 근거 자료\n\n- 국민연금법", "## 근거 자료\n\n- 국민연금법 제61조\n\n## 덧붙임\n\n- 국민연금법", "맨 끝")
    import make_naver_images as mi        # 카드에만 있는 숫자 (T7)
    try:
        mi.CARDS["99_시험"] = mi.hero_card("#000", "감액 6%", "출처 2024", "45", "만원", "설명 30%", "끝")
        qfails("[이미지 ②: 카드]", "[이미지 ②: `assets/naver_img/99_시험.png` — 제작 완료]", "카드에만 있는 숫자(99_시험): 45")
        mi.CARDS["99_시험"] = mi.hero_card("#000", "감액 6%", "출처 2024", "30", "%", "설명 63세", "끝")
        assert qissues(qdoc.replace("[이미지 ②: 카드]", "[이미지 ②: `assets/naver_img/99_시험.png`]"))[0] == []
    finally:
        del mi.CARDS["99_시험"]
    # 제목 뼈대는 새 글 포함 최근 5편 중 2편까지, 소제목 구성은 바로 앞 편과 달라야 한다
    t5 = "2026 A | 무엇? 확인할 5가지"
    assert title_skeleton(t5) == "?확인할 N가지" == title_skeleton("2026 B | 다른 질문? 확인할 3가지")
    assert title_repeat({"25": t5, "26": t5, "27": "2026 C | 질문? 확인할 4가지"}) == [27]
    assert title_repeat({"24": t5, "25": "x | 다른 꼬리", "26": "y | 또 다른", "27": "2026 C | 질문? 확인할 4가지"}) == []
    assert title_repeat({"20": t5, "21": t5, "22": "a", "23": "b", "24": "c", "25": "d", "26": "e", "27": t5}) == []
    assert section_repeat({"26": ["#", "#"], "27": ["#", "#"]}) == [27]
    assert section_repeat({"25": ["#"], "26": ["#"], "27": ["#", "*"]}) == []          # 26편 이전은 판정하지 않는다
    # 30편부터의 최신성·제목 — 29편 실제 사고를 고정한다
    vdoc = qdoc.replace("제목: 2026 국민연금 일찍 받는 사람 | 5년 당기면 얼마나", "제목: 2026 국민연금 일찍 받는 사람｜당기면 얼마나").replace(
        "- 고유 근거:", "- 검색 의도: decision\n- 최신성 재확인: 2026-10-31 14:00 | 국민연금 조기수령 2026 | https://www.nps.or.kr/a\n- 고유 근거:")

    def vissues(src):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "30_t.md")
            open(path, "w", encoding="utf-8").write(src)
            n_, b_, c_, tg = parts(path)
            return v2_issues(n_, b_, c_)[0] + template_issues(n_, b_, c_, target_keyword(n_), True, True) + quality_issues(n_, b_, c_, tg, True)

    assert vissues(vdoc) == [], vissues(vdoc)
    assert any("권장" in w for w in v2_issues(vdoc.replace("당기면 얼마나 깎일까? 63세 기준으로 계산", "63세 기준으로 계산하면 조기수령이 얼마나 줄어드는지 비교합니다"), "", "")[1])     # 길이는 경고
    assert not any("구체 상황" in i for i in vissues(vdoc.replace("일찍 받는 사람", "조기수령")))                 # 조건어 강제 해제

    def vfails(old, new, word):
        assert old in vdoc, old
        got = vissues(vdoc.replace(old, new, 1))
        assert any(word in i for i in got), (word, got)
    vfails("사람｜", "사람 | ", "구분자")
    vfails("- 최신성 재확인: 2026-10-31 14:00 | 국민연금 조기수령 2026 | https://www.nps.or.kr/a\n", "", "최신성 재확인")
    vfails("| 국민연금 조기수령 2026 | https://www.nps.or.kr/a", "| 검색어만", "최신성 재확인")
    vfails("- 검색 의도: decision", "- 검색 의도: 기타", "검색 의도")
    vfails("- 검색 의도: decision", "- 검색 의도: decision\n- 보조 의도: how_to | comparison | definition", "보조 의도")
    vfails("| 수령나이 | 63세 | 국민연금법 |", "| 신청 기간 | 63세 | 더데일리이코노미 기사 |", "일정 근거가 기사")    # 29편의 기간 근거
    vfails("63세 기준으로 계산", "63세 기준 7년 계산", "제목의 7년")                                                # 2년/2개월 충돌
    vfails("조건이 있습니다.", "2026년 귀속은 2026년 1월에 정산합니다.", "귀속연도")
    with tempfile.TemporaryDirectory() as d:
        p_ = os.path.join(d, "30_t.md")
        assert any("결과가 없다" in i for i in title_gate_issue(p_, "제목"))
        os.makedirs(os.path.join(d, "_titles"))
        open(os.path.join(d, "_titles", "30.json"), "w", encoding="utf-8").write('{"selected_title": "제목"}')
        assert title_gate_issue(p_, "제목") == [] and any("다르다" in i for i in title_gate_issue(p_, "다른 제목"))
    # TEST-THUMB — 대표사진 카피
    tmd = ("제목: 2026 맞벌이 연말정산｜부양가족은 누구에게? 카드 25% 계산\n\n본문 25%와 2개월입니다.\n\n## 작성 메모\n\n"
           "- 썸네일 유형: number\n- 썸네일 문구: 카드 25% 계산 | 맞벌이 누구 카드?\n- 썸네일 강조 숫자: 25%\n- 카테고리 색: tax\n- 돼지 자세: calculator\n")
    tbody = "본문 25%와 2개월입니다."
    assert v2_thumb_issues(tmd, tbody) == [], v2_thumb_issues(tmd, tbody)
    t1 = tmd.replace("카드 25% 계산 | 맞벌이 누구 카드?", "2026 맞벌이 연말정산 | 부양가족은 누구에게? 카드 25% 계산")     # 001 제목 복사
    assert any("REJECT_TITLE_COPY" in i for i in v2_thumb_issues(t1, tbody))
    t5 = tmd.replace("문구: 카드 25% 계산", "문구: 기한 2년 확인")                                                               # 005 숫자 불일치
    assert any("FACT_MISMATCH" in i and "2년" in i for i in v2_thumb_issues(t5, tbody))
    assert any("판정·행동" in i for i in v2_thumb_issues(tmd.replace("문구: 카드 25% 계산", "문구: 맞벌이 카드"), tbody))
    assert any("강조 숫자" in i for i in v2_thumb_issues(tmd.replace("- 썸네일 강조 숫자: 25%\n", ""), tbody))
    assert any("AI 사용 이유" in i for i in v2_thumb_issues(tmd.replace("유형: number", "유형: scene"), tbody))
    assert any("카테고리 색" in i for i in v2_thumb_issues(tmd.replace("색: tax", "색: red"), tbody))
    # 002 최근 9개 AI 3개 초과 — 21~29편이 전부 scene이라 30편 scene은 막힌다
    past = {str(n): ("scene", None) for n in range(21, 30)}
    assert any("AI 대표사진" in w for n, w in thumb_v2_repeat({**past, "30": ("scene", "explain")}) if n == 30)
    assert not any("AI 대표사진" in w for _, w in thumb_v2_repeat({**past, "30": ("number", "explain")}))
    assert any("3연속" in w for _, w in thumb_v2_repeat({"30": ("number", "a"), "31": ("number", "b"), "32": ("number", "c")}))
    assert any("돼지 자세" in w for _, w in thumb_v2_repeat({"30": ("number", "a"), "31": ("compare", "a"), "32": ("action", "a")}))
    assert freshness_time("- 최신성 재확인: 2026-10-31 14:00 | q | s\n").hour == 14 and freshness_time("없음") is None
    assert title_skeleton("2026 A｜무엇? 확인할 5가지") == "?확인할 N가지" == title_skeleton("2026 A: 무엇? 확인할 3가지")
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
    from pipeline import post_issues      # pipeline이 이 모듈을 가져오므로 함수 안에서 불러온다
    tistory = sents("".join(open(f, encoding='utf-8').read()
                            for f in glob.glob('_workspace/02_blog_post_*.md')))
    volumes = load_volumes()
    if not volumes:
        print(f'⚠ {VOLUME_CSV} 없음 — 태그 검색량 검사를 건너뜁니다\n')
    bench = sents("".join(open(f, encoding='utf-8').read() for f in glob.glob(f'{BENCH_DIR}/*.txt')))
    allok = True
    cover_kws, box_titles, thumb_kinds, comps, titles, skels, looks = {}, {}, {}, {}, {}, {}, {}
    for p in sorted(glob.glob('content/naver/*.md')):
        r = measure(p, tistory, volumes, bench)
        if r is None:          # 제목 줄이 없으면 원고가 아니다(메모·프롬프트 파일)
            continue
        cover_kws[os.path.basename(p)] = r["cover_kw"]
        box_titles[os.path.basename(p)] = r["boxes"]
        thumb_kinds[os.path.basename(p)] = r["thumb_type"]
        comps[os.path.basename(p)] = r["composition"]
        if num := re.match(r'\d+', os.path.basename(p)):
            titles[num.group()], skels[num.group()] = r["title"], r["skeleton"]
            looks[num.group()] = (r["thumb_type"], memo_value(open(p, encoding='utf-8').read(), '돼지 자세'))
        if r["template"] and not bench:
            print(f'⚠ {BENCH_DIR} 비어 있음 — 벤치마크 문장 중복을 못 봤다. `check_naver.py --fetch-benchmark` 후 다시 실행')
        fails, warns = post_issues(p)       # 25편부터: 클러스터·출처 기록·글 간 유사도 (pipeline.py)
        ok = passes(r) and not fails
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
        for t in r["warn"]:
            print('         경고:', t)
        for t in r["format"]:
            print('         형식:', t)
        if r["judged"]:
            for t in r["structure"]:
                print('         구조:', t)
        elif r["structure"]:
            print(f'         (발행됨 — 판정 제외) 구조 {len(r["structure"])}건')
        for t in fails:
            print('         파이프라인:', t)
        for t in warns:
            print('         경고:', t)
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
    for name in composition_repeat(comps):
        allok = False
        print(f'CHECK {name} — 썸네일 구도가 바로 앞 편과 같다. 다른 구도를 고른다')
    for name in card_paused(thumb_kinds):
        allok = False
        print(f'CHECK {name} — card 썸네일은 보류 중이다(CARD_ENABLED). scene으로 만든다')
    for n in title_repeat(titles):
        allok = False
        print(f'CHECK {n}편 — 제목 뼈대가 최근 5편 중 {TITLE_REPEAT[0]}편을 넘게 같다: {title_skeleton(titles[str(n).zfill(2)])}')
    for n, why in thumb_v2_repeat(looks):
        allok = False
        print(f'CHECK {n}편 — {why}')
    for n in section_repeat(skels):
        allok = False
        print(f'CHECK {n}편 — 소제목 구성이 바로 앞 편과 같다. 섹션 순서를 바꾼다')
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
