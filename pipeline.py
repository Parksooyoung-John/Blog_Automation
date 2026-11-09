"""블로그 파이프라인 — 후보 점수화, 발행 상태 기록, 내부링크 추천, 글 간 유사도, 글 단위 성과.

    python -X utf8 pipeline.py score [--register]     # _candidates.csv 채점 (7점 이상 후보, 5~6 보류, 4 이하 폐기)
    python -X utf8 pipeline.py start 후보ID            # 후보 → 새 편 번호를 받고 DRAFT
    python -X utf8 pipeline.py status NN 상태 [logNo]  # 상태 이동 (순서 강제, APPROVED는 사람이 터미널에서만)
    python -X utf8 pipeline.py list                    # 발행 상태·포트폴리오 비율
    python -X utf8 pipeline.py links NN                # 내부링크 후보·넣을 문단·기존 글 수정 후보·후속 글
    python -X utf8 pipeline.py sync                    # 라이브 목록에서 logNo·발행일 채우기
    python -X utf8 pipeline.py linkcheck               # 발행 글의 내부 링크가 살아 있는 글을 가리키는지
    python -X utf8 pipeline.py perf                    # 24h·7d·28d·30d 점검 대상
    python -X utf8 pipeline.py perf add NN 24h views=9 search_in=1 search_kw=키워드 ...
    python -X utf8 pipeline.py queries add metric=query post=28 query=수정신고 방법 source=캡처.png
    python -X utf8 pipeline.py queries import 파일.csv  # 같은 열 이름의 CSV
    python -X utf8 pipeline.py queries trend           # 완료된 같은 길이 기간끼리만 비교
    python -X utf8 pipeline.py queries plan            # 검색어 묶음 → 기존 글 대조 → UPDATE·NEW·HOLD
    python -X utf8 pipeline.py --selftest

상태 기록의 목적은 "APPROVED 이전에는 붙여넣기 파일도 안 만든다"를 코드로 막는 것이다(naver_paste.page_for).
글 단위 성과등급은 manager.py의 방문자 판정과 별개이고 그 기준을 바꾸지 않는다.
"""
import csv
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIR = ROOT / "content" / "naver"
LEDGER, CANDS, PERF = DIR / "_pipeline.csv", DIR / "_candidates.csv", DIR / "_perf.csv"

LEDGER_COLS = ["post", "status", "cluster", "role", "portfolio", "primary_kw", "score", "approved", "logno", "published"]
CAND_COLS = ["id", "cluster", "order", "role", "keyword", "intent", "volume", "serp_fresh", "geo_cited",
             "official", "diff", "season", "score", "decision", "status", "post", "track"]     # track: 빈칸·core | seasonal
PERF_COLS = ["post", "checkpoint", "date", "views", "visitors", "search_in", "search_kw", "home_in", "avg_time",
             "likes", "comments", "link_clicks", "threads_in", "flag", "grade",
             "thumb_changed_at", "title_changed", "impressions", "ctr", "body_changed_at", "change_kind"]     # 대표사진 효과 기록. 노출수가 없으면 클릭률을 쓰지 않는다

# 순서 있는 본선. SCHEDULED는 예약발행을 쓸 때만 거친다.
FLOW = ["IDEA", "RESEARCHING", "DRAFT", "SEO_REVIEW", "HUMAN_REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED"]
ALLOWED = {
    "DRAFT": {"SEO_REVIEW", "FACT_CHECK_REQUIRED", "EVIDENCE_REQUIRED", "QA_BLOCKED", "REJECTED"},
    "FACT_CHECK_REQUIRED": {"DRAFT", "RESEARCHING", "REJECTED"},
    "EVIDENCE_REQUIRED": {"DRAFT", "RESEARCHING", "REJECTED"},     # 고유 근거(경험·계산·1차 출처 분석)가 없다
    "QA_BLOCKED": {"DRAFT", "SEO_REVIEW", "REJECTED"},             # check_naver 실패
    "SEO_REVIEW": {"HUMAN_REVIEW", "DRAFT", "FACT_CHECK_REQUIRED", "EVIDENCE_REQUIRED", "QA_BLOCKED", "REJECTED"},
    "HUMAN_REVIEW": {"APPROVED", "DRAFT", "FACT_CHECK_REQUIRED", "REJECTED"},
    "APPROVED": {"SCHEDULED", "PUBLISHED", "HUMAN_REVIEW"},
    "SCHEDULED": {"PUBLISHED", "HUMAN_REVIEW"},
    "PUBLISHED": {"PERFORMANCE_REVIEW"},
    "PERFORMANCE_REVIEW": {"UPDATE_REQUIRED", "MERGE_REQUIRED", "RETIRED", "PUBLISHED"},
    "UPDATE_REQUIRED": {"HUMAN_REVIEW", "MERGE_REQUIRED", "PUBLISHED"},
    "MERGE_REQUIRED": {"UPDATE_REQUIRED", "RETIRED"},
    "RETIRED": set(),
    "REJECTED": set(),
}
PASTE_OK = {"HUMAN_REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED", "PERFORMANCE_REVIEW", "UPDATE_REQUIRED"}
LIVE = {"PUBLISHED", "PERFORMANCE_REVIEW", "UPDATE_REQUIRED", "MERGE_REQUIRED"}
# 품질 강화 문서(2026-10-28)의 상태 이름 — 같은 뜻의 기존 이름으로 받는다(CSV는 기존 이름 그대로)
ALIASES = {"READY_FOR_APPROVAL": "HUMAN_REVIEW", "MONITORING": "PERFORMANCE_REVIEW",
           "REFRESH_REQUIRED": "UPDATE_REQUIRED", "RESEARCH": "RESEARCHING"}
MIN_GAP_HOURS = 36         # 발행 간격 (YAML publishing.min_interval_hours)
MAX_PER_WEEK = 3           # 최근 7일 발행 수 (YAML publishing.max_posts_per_week)
LIVE_MATCH_MIN = 0.35      # 발행 때 고친 제목을 같은 글로 볼 2글자 조각 겹침 (27편 원고·라이브가 이 근처다)
PORTFOLIO = {"검색": 0.70, "홈피드": 0.20, "수익": 0.10}
RULES_FROM = 25            # 클러스터·유사도·출처 기록 규칙을 판정에 넣는 첫 편 (24편까지는 발행됨)
SCOPE = re.compile(r"연말정산|세액공제|소득공제|세금|연금|노후|장려금|지원금|실업급여|건강보험|고용보험|부양가족|인적공제")
# Topic Authority(품질 강화 문서 7절, 100점): 직장인 가족 돈 문제 30 · 세금·연금·지원금 25 · 내부 링크 20 · 공식 근거 15 · 고유 사례 10
FAMILY_MONEY = re.compile(r"부모|자녀|배우자|맞벌이|가족|직장인|월급|급여|연봉|퇴사|이직|생활비|공제|환급|지원|수당|보험료|월세|연말정산")
OFF_TOPIC = re.compile(r"드라마|예능|연예|아이돌|가수|배우 |스포츠|축구|야구|결말|사건|사고|맛집|여행|게임")
ACCEPT_AT, HOLD_AT = 75, 60
CHECKPOINTS = {"24h": 1, "7d": 7, "14d": 14, "28d": 28, "30d": 30}
SEASON_FIT = re.compile(r"난방|관리비|공과금|전기요금|가스요금|직구|블랙프라이데이|할인|소비|생활비|장보기|물가|절약|환율|관세")
TRACK_TARGET = {"core": 0.80, "seasonal": 0.20}     # 2026-11-09 노션 계획의 내부 실험값. 네이버 노출 기준이 아니다
GRACE_DAYS = 3
BOILER_MIN = 5             # 같은 문단이 이만큼 글에 그대로 있으면 템플릿 고정 문구로 본다(복사한 문단이 면제되지 않게 크게 잡는다)
SIM_TITLE, SIM_BODY, SIM_Q = 0.70, 0.60, 0.70
AI_PHRASES = ("총정리해 보겠습니다", "꼭 확인하세요", "지금부터 알아보겠습니다", "도움이 되셨기를 바랍니다",
              "결론적으로", "한눈에 알아보겠습니다")
BAN_TITLE = ("무조건", "100%", "역대급")


def read_csv(path, cols):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{c: r.get(c, "") for c in cols} for r in csv.DictReader(f)]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def num_of(x) -> int:
    return int(re.match(r"\d+", Path(str(x)).name).group())


def post_file(nn) -> Path:
    hits = sorted(DIR.glob(f"{int(nn):02d}_*.md"))
    if not hits:
        raise SystemExit(f"content/naver/{int(nn):02d}_*.md 원고가 없다")
    return hits[0]


# ---- 유사도 -------------------------------------------------------------

def grams(s: str, n=2) -> set:
    s = re.sub(r"[\s\W_]+", "", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: str, b: str, n=2) -> float:
    x, y = grams(a, n), grams(b, n)
    return len(x & y) / len(x | y) if x | y else 0.0


def contain(small: str, big: str) -> float:
    """small의 글자 조각 중 big에도 있는 비율 — 후보 키워드가 기존 글에 얼마나 덮이는가."""
    x = grams(small)
    return len(x & grams(big)) / len(x) if x else 0.0


def blocks_of(md: str) -> list:
    """본문(작성 메모 앞)의 문단들. 제목·구분선·태그 줄은 뺀다."""
    body = md.split("## 작성 메모")[0]
    out = []
    for b in re.split(r"\n\s*\n", body):
        b = b.strip()
        if b and not b.startswith(("제목:", "#")) and not re.fullmatch(r"-{3,}", b) and not b.startswith("[이미지"):
            out.append(b)
        elif b.startswith("## "):
            out.append(b)
    return out


def boilerplate(corpus: dict) -> set:
    """여러 글에 그대로 있는 문단 = 템플릿 고정 문구(소제목·Q&A 틀·공유 유도 등). 손으로 목록을 두지 않는다."""
    seen = {}
    for md in corpus.values():
        for b in set(blocks_of(md)):
            seen[b] = seen.get(b, 0) + 1
    return {b for b, n in seen.items() if n >= BOILER_MIN}


def prose(md: str, boiler: set) -> list:
    return [b for b in blocks_of(md) if b not in boiler and not b.startswith("## ")]


def title_of(md: str) -> str:
    m = re.search(r"^제목: (.+)$", md, re.M)
    return m.group(1).strip() if m else ""


def first_sentence(md: str, boiler: set) -> str:
    for b in prose(md, boiler):
        if not b.startswith(('"', ">", "|", "-")):
            return re.split(r"(?<=[.!?])\s", b, maxsplit=1)[0]
    return ""


def last_summary(md: str) -> str:
    m = re.search(r"## 오늘의 살림 정리\s*\n+(.+?)(?:\n## |\n---|\Z)", md.split("## 작성 메모")[0], re.S)
    return m.group(1).strip().splitlines()[-1] if m else ""


def questions(md: str) -> list:
    return [re.sub(r"^> ?\[질문\] ?", "", b.splitlines()[0]).strip() for b in blocks_of(md) if b.startswith("> [질문]")]


def numbered_heads(md: str) -> list:
    return [re.sub(r"^\d+\.\s*", "", h) for h in re.findall(r"^## \d+\. (.+)$", md.split("## 작성 메모")[0], re.M)]


def thumb_text(md: str) -> str:
    m = re.search(r"^- 썸네일 문구:\s*(.+)$", md, re.M)
    return re.sub(r"[\s/|]+", "", m.group(1)) if m else ""


def similarity_issues(md: str, prior: dict, boiler: set) -> list:
    """새 원고 vs 앞선 글들(prior: {이름: md}, 최근 20편). → 문제 목록. 템플릿 고정 문구는 boiler로 뺀다."""
    issues = []
    mine = prose(md, boiler)
    my_text = "".join(mine)
    for name, old in prior.items():
        if (j := jaccard(title_of(md), title_of(old))) >= SIM_TITLE:
            issues.append(f"제목이 {name}와 {j:.0%} 비슷하다 ({SIM_TITLE:.0%} 이상은 발행 중단)")
        old_text = "".join(prose(old, boiler))
        if my_text and old_text and (j := jaccard(my_text, old_text, 3)) >= SIM_BODY:
            issues.append(f"본문이 {name}와 {j:.0%} 비슷하다 ({SIM_BODY:.0%} 이상은 재작성)")
        a, b = first_sentence(md, boiler), first_sentence(old, boiler)
        if a and a == b:
            issues.append(f"도입 첫 문장이 {name}와 같다")
        a, b = last_summary(md), last_summary(old)
        if a and a == b:
            issues.append(f"결론(오늘의 살림 정리 마지막 줄)이 {name}와 같다")
        if (h := numbered_heads(md)) and h == numbered_heads(old):
            issues.append(f"번호 소제목 순서·문구가 {name}와 같다")
        if (t := thumb_text(md)) and t == thumb_text(old):
            issues.append(f"썸네일 문구가 {name}와 같다")
        for q in questions(md):
            if any(jaccard(q, o) >= SIM_Q for o in questions(old)):
                issues.append(f"Q&A 질문이 {name}와 겹친다: {q[:30]}")
    for p in AI_PHRASES:
        n_here = md.split("## 작성 메모")[0].count(p)
        recent = sum(p in o.split("## 작성 메모")[0] for o in list(prior.values())[-5:])
        if n_here > 1 or (n_here and recent >= 2):
            issues.append(f"AI 문체 표현 반복: \"{p}\" (이 글 {n_here}회, 최근 5편 중 {recent}편)")
    return issues


def intro_sig(md: str, boiler: set) -> tuple:
    """도입 3문단의 첫 어절. 연속 3편이 같으면 경고(템플릿 판정 10-30 전이라 실패로 올리지 않는다)."""
    ps = [b for b in prose(md, boiler) if not b.startswith(('"', ">", "|", "-"))][:3]
    return tuple(p.split()[0] if p.split() else "" for p in ps)


# ---- 원고 필수 항목 (RULES_FROM편부터) --------------------------------------

def memo_line(md: str, key: str):
    m = re.search(rf"^- {re.escape(key)}:\s*(.+?)\s*$", md, re.M)
    return m.group(1) if m else None


def source_lines(md: str) -> list:
    """`- 출처: 기관 | 페이지 제목 | URL | 확인일` → [(기관, 제목, URL, 확인일)]. 형식이 어긋난 줄은 빈칸이 된다."""
    out = []
    for m in re.finditer(r"^- 출처:\s*(.+)$", md, re.M):
        parts = [x.strip() for x in m.group(1).split("|")] + [""] * 4
        out.append(tuple(parts[:4]))
    return out


def required_issues(md: str, ledger: dict) -> list:
    """요청서 9·10·11·13절의 필수 기록. ledger: {편번호(int): 행}."""
    issues = []
    port = memo_line(md, "포트폴리오")
    if port not in PORTFOLIO:
        issues.append(f"작성 메모 `- 포트폴리오:`가 {'·'.join(PORTFOLIO)} 중 하나가 아니다")
    cluster = memo_line(md, "클러스터")
    if not cluster:
        issues.append("작성 메모 `- 클러스터:`가 없다 (없으면 `없음`)")
    diffs = [x for x in (memo_line(md, "차별화 요소") or "").split("|") if x.strip()]
    if len(diffs) < 2:
        issues.append("작성 메모 `- 차별화 요소:`가 2개 미만이다 (a | b)")
    if not memo_line(md, "적용 기준일"):
        issues.append("작성 메모 `- 적용 기준일:`이 없다")
    src = source_lines(md)
    if len(src) < 2:
        issues.append("작성 메모 `- 출처: 기관 | 페이지 제목 | URL | 확인일` 줄이 2개 미만이다")
    for s in src:
        if not (s[0] and s[1] and re.match(r"https?://", s[2]) and re.fullmatch(r"20\d\d-\d\d-\d\d", s[3])):
            issues.append(f"출처 줄 형식 오류(기관|제목|URL|YYYY-MM-DD): {'|'.join(s)[:50]}")
    if any(r[4] == "UNVERIFIED" for r in _facts(md)):
        issues.append("수치 근거에 UNVERIFIED가 있다 — 상태를 FACT_CHECK_REQUIRED로 두고 사용자에게 전달한다")
    if cluster and cluster != "없음":
        targets = [t.strip() for t in re.split(r"[|,]", memo_line(md, "내부 링크 대상") or "") if t.strip()]
        if len(targets) < 2:
            issues.append("클러스터 글은 `- 내부 링크 대상: 12 | 15` 2~3개가 필요하다")
        for t in targets:
            row = ledger.get(int(t)) if t.isdigit() else None
            if not row or row["status"] not in LIVE:
                issues.append(f"내부 링크 대상 {t}편이 발행된 글이 아니다 (미발행 글로 링크 금지)")
        if any(r.get("cluster") == cluster and r["status"] in LIVE for r in ledger.values()) and                 not any(ledger.get(int(t), {}).get("cluster") == cluster for t in targets if t.isdigit()):
            issues.append("같은 클러스터의 발행된 글이 있는데 내부 링크 대상에 하나도 없다")
        if len(re.findall(r"\[내부 링크", md.split("## 작성 메모")[0])) < 2:
            issues.append("본문에 `[내부 링크 …]` 자리가 2개 미만이다")
    title = title_of(md)
    issues += [f"제목 금지어: {w}" for w in BAN_TITLE if w in title]
    return issues


def _facts(md: str) -> list:
    import check_naver
    return check_naver.facts(md)


def load_ledger() -> dict:
    return {num_of(r["post"]): r for r in read_csv(LEDGER, LEDGER_COLS)}


def corpus_before(nn: int, limit=20) -> dict:
    files = sorted(p for p in DIR.glob("[0-9][0-9]_*.md") if num_of(p) < nn)[-limit:]
    return {p.name[:2] + "편": p.read_text(encoding="utf-8") for p in files}


def post_issues(path) -> tuple:
    """check_naver가 부르는 진입점. → (실패 목록, 경고 목록). RULES_FROM 이전 편은 ([], [])."""
    nn = num_of(path)
    if nn < RULES_FROM:
        return [], []
    md = Path(path).read_text(encoding="utf-8")
    prior = corpus_before(nn)
    boiler = boilerplate({**prior, "self": md})
    fails = required_issues(md, load_ledger()) + similarity_issues(md, prior, boiler)
    warns = []
    sigs = [intro_sig(o, boiler) for o in list(prior.values())[-2:]] + [intro_sig(md, boiler)]
    if len(sigs) == 3 and sigs[0] == sigs[1] == sigs[2]:
        warns.append("도입 구조가 3편 연속 같다 (템플릿 판정 10-30 전이라 경고)")
    return fails, warns


# ---- 점수 --------------------------------------------------------------

def to_int(x, default=0):
    try:
        return int(str(x).replace(",", ""))
    except ValueError:
        return default


def score_seasonal(c: dict, titles: dict, today) -> tuple:
    """시즌 후보 → (점수, 항목별, 결정). 브랜드 30·관측 수요 25·고유 가치 25·시의성 10·제작 가능성 10.
    관측 수요가 비어 있으면 숫자로 포장하지 않고 점수 없이 HOLD다(2026-11-09 노션 계획)."""
    kw = c["keyword"]
    if OFF_TOPIC.search(kw):
        return 0, {"주제 무관": 0}, "REJECTED"
    if not (c["volume"] or c["serp_fresh"] or c["geo_cited"]):
        return "", {"수요 근거": "미확인"}, "HOLD"
    parts = {"브랜드": 30 if SEASON_FIT.search(kw) or FAMILY_MONEY.search(kw) or SCOPE.search(kw) else 0, "수요": 25,
             "고유가치": 25 if c["diff"] == "1" else 0, "시의성": 10 if str(today.month) in c["season"].split("|") else 0,
             "제작": 10 if c["official"] == "1" else 0}
    total = sum(parts.values())
    if total < ACCEPT_AT:
        return total, parts, "HOLD" if total >= HOLD_AT else "REJECTED"
    cover = max((contain(kw, t) for t in titles.values()), default=0)
    return total, parts, "UPDATE_EXISTING" if cover >= 0.70 else "CREATE_NEW"


def track_counts(rows: list, n: int = 10) -> dict:
    """최근 n편 → {core: 편수, seasonal: 편수}. 원고의 `- 콘텐츠 트랙:`을 읽고, 없으면 core다."""
    out = {"core": 0, "seasonal": 0}
    for r in rows[-n:]:
        try:
            md = post_file(r["post"]).read_text(encoding="utf-8")
        except (SystemExit, OSError):
            continue
        out["seasonal" if (memo_line(md, "콘텐츠 트랙") or "").strip() == "seasonal" else "core"] += 1
    return out


def score_one(c: dict, ledger_rows: list, titles: dict, today) -> tuple:
    """후보 한 줄 → (점수 100점, 항목별, 결정). 사람 판단 항목(official·diff)은 CSV 값을 그대로 읽는다.

    결정: REJECTED · HOLD · UPDATE_EXISTING(의도 70% 이상 겹침) · EXPAND_HUB(허브와 60~70%) ·
    CREATE_SUPPORTING_POST(클러스터 spoke) · CREATE_NEW. 뒤의 둘만 `start`할 수 있다(상태 IDEA).
    """
    if c.get("track") == "seasonal":
        return score_seasonal(c, titles, today)
    kw = c["keyword"]
    if OFF_TOPIC.search(kw):
        return 0, {"주제 무관": 0}, "REJECTED"
    live = any(r["cluster"] == c["cluster"] and r["status"] in LIVE for r in ledger_rows) if c["cluster"] else False
    parts = {
        # SCOPE도 본다 — FAMILY_MONEY만 봤더니 근로장려금·퇴직금 세금 후보가 50점으로 폐기됐다(2026-10-30)
        "가족돈": 30 if c["cluster"] or FAMILY_MONEY.search(kw) or SCOPE.search(kw) else 0,
        "세금연금": 25 if SCOPE.search(kw) else 0,
        "링크": 20 if live else 10 if c["cluster"] else 0,
        "공식": 15 if c["official"] == "1" else 0,
        "차별": 10 if c["diff"] == "1" else 0,
    }
    total = sum(parts.values())
    if total < ACCEPT_AT:
        return total, parts, "HOLD" if total >= HOLD_AT else "REJECTED"
    best, cover = max(((k, contain(kw, t)) for k, t in titles.items()), key=lambda x: x[1], default=("", 0))
    if cover >= 0.70:
        return total, parts, "UPDATE_EXISTING"
    hubs = {r["post"] for r in ledger_rows if r.get("role") == "hub"}
    if cover >= 0.60 and best in hubs:       # 0.5로는 클러스터 공통어(연말정산 부양가족)만 겹친 bg-09·10이 걸렸다
        return total, parts, "EXPAND_HUB"
    return total, parts, "CREATE_SUPPORTING_POST" if c["cluster"] and c["role"] == "spoke" else "CREATE_NEW"


STARTABLE = {"CREATE_SUPPORTING_POST", "CREATE_NEW"}


def existing_titles() -> dict:
    """발행된 글 → 제목 + 소제목 + 목표 키워드. 후보가 이 안에 70% 이상 들어 있으면 같은 검색 의도로 본다."""
    out = {}
    for p in DIR.glob("[0-9][0-9]_*.md"):
        md = p.read_text(encoding="utf-8")
        out[p.name[:2]] = title_of(md) + " " + " ".join(re.findall(r"^## (.+)$", md.split("## 작성 메모")[0], re.M)) \
            + " " + (memo_line(md, "목표 키워드") or "")
    return out


def cmd_score(args, today=None):
    today = today or datetime.date.today()
    rows, ledger = read_csv(CANDS, CAND_COLS), read_csv(LEDGER, LEDGER_COLS)
    titles = existing_titles()
    for c in rows:
        if c["status"] in ("drafted", "REJECTED") or c["post"]:
            continue
        total, parts, decision = score_one(c, ledger, titles, today)
        c["score"], c["decision"] = str(total), decision
        if "--register" in args or not c["status"]:
            c["status"] = "IDEA" if decision in STARTABLE else decision
        print(f"{c['id']:<8}{total:>3}{'점' if total != '' else '  '} {decision:<23}{c['keyword']}  " + " ".join(f"{k}{v}" for k, v in parts.items()))
    write_csv(CANDS, CAND_COLS, rows)


def cmd_start(args):
    cid = args[0]
    rows, ledger = read_csv(CANDS, CAND_COLS), read_csv(LEDGER, LEDGER_COLS)
    c = next((r for r in rows if r["id"] == cid), None)
    if not c or c["status"] != "IDEA":
        raise SystemExit(f"{cid}: IDEA 상태의 후보가 아니다 ({ACCEPT_AT}점 이상, 새 글로 판정된 것만 시작한다)")
    if c["decision"] not in STARTABLE:      # `score`는 --register 없이 상태를 덮지 않는다 — 결정이 새 글이 아니면 막는다
        raise SystemExit(f"{cid}: 판정이 {c['decision']}이다 — 새 글이 아니라 기존 글 수정·허브 확장 대상이다")
    nn = max([num_of(r["post"]) for r in ledger] + [num_of(p) for p in DIR.glob("[0-9][0-9]_*.md")]) + 1
    ledger.append({"post": f"{nn:02d}", "status": "DRAFT", "cluster": c["cluster"], "role": c["role"],
                   "portfolio": "검색", "primary_kw": c["keyword"], "score": c["score"], "approved": "",
                   "logno": "", "published": ""})
    c["status"], c["post"] = "drafted", f"{nn:02d}"
    write_csv(LEDGER, LEDGER_COLS, ledger)
    write_csv(CANDS, CAND_COLS, rows)
    print(f"{cid} → {nn:02d}편 DRAFT. 원고는 content/naver/{nn:02d}_*.md 로 쓴다")
    print(slot_text(ledger))


# ---- 상태 --------------------------------------------------------------

def check_move(cur: str, new: str, logno: str = "", tty: bool = False):
    """상태 이동 규칙. 문제가 있으면 ValueError."""
    if new not in ALLOWED.get(cur, set()):
        raise ValueError(f"{cur} → {new} 이동은 허용되지 않는다 (허용: {', '.join(sorted(ALLOWED.get(cur, []))) or '없음'})")
    if new == "APPROVED" and not tty:
        raise ValueError("APPROVED는 사용자가 터미널에서 직접 입력해야 한다 (확인 질문에 답이 필요하다)")
    if new == "PUBLISHED" and cur in ("APPROVED", "SCHEDULED") and not re.fullmatch(r"\d{9,}", logno):
        raise ValueError("PUBLISHED로 옮기려면 logNo(주소 끝의 긴 숫자)를 함께 넣는다")


def cmd_status(args):
    nn, new = int(args[0]), ALIASES.get(args[1].upper(), args[1].upper())
    logno = args[2] if len(args) > 2 else ""
    rows = read_csv(LEDGER, LEDGER_COLS)
    r = next((x for x in rows if num_of(x["post"]) == nn), None)
    if not r:
        raise SystemExit(f"{nn:02d}편이 _pipeline.csv에 없다 (후보는 `start`로 시작한다)")
    tty = sys.stdin.isatty()
    if new == "APPROVED" and tty and input(f"{nn:02d}편을 승인하고 발행해도 됩니까? (승인 입력): ").strip() != "승인":
        raise SystemExit("승인하지 않았다")
    if new == "HUMAN_REVIEW":
        import check_naver
        res = check_naver.measure(str(post_file(nn)), set(), None, frozenset())
        fails, _ = post_issues(post_file(nn))
        if not check_naver.passes(res) or fails:
            probs = fails + res["format"] + res["structure"]
            nxt = "EVIDENCE_REQUIRED" if any("EVIDENCE_REQUIRED" in x for x in probs) else "QA_BLOCKED"
            raise SystemExit("HUMAN_REVIEW로 올리려면 check_naver가 통과해야 한다:\n  " + "\n  ".join(probs or ["check_naver 확인 필요"])
                             + f"\n→ `pipeline.py status {nn:02d} {nxt}`로 기록하고 고친 뒤 다시 올린다")
    # 확인 질문·검수를 기다리는 사이 다른 명령이 장부에 쓴 줄을 덮어쓰지 않게 쓰기 직전에 다시 읽는다
    # (2026-11-04 `status 32 APPROVED`가 그 사이 `start`가 넣은 33편 줄을 지웠다)
    rows = read_csv(LEDGER, LEDGER_COLS)
    r = next(x for x in rows if num_of(x["post"]) == nn)
    try:
        check_move(r["status"], new, logno, tty)
    except ValueError as e:
        raise SystemExit(str(e))
    r["status"] = new
    if new == "APPROVED":
        r["approved"] = datetime.date.today().isoformat()
    if logno:
        r["logno"] = logno
    if new == "PUBLISHED" and not r["published"]:
        now = datetime.datetime.now()
        slot = next_publish_slot([x for x in rows if x is not r], now)
        if slot > now:
            print(f"⚠ 발행 간격 초과 — {slot:%Y-%m-%d %H:%M} 이후가 맞았다 ({MIN_GAP_HOURS}시간 · 7일 {MAX_PER_WEEK}편). 기록은 남긴다")
        r["published"] = f"{now:%Y-%m-%d %H:%M}"
    write_csv(LEDGER, LEDGER_COLS, rows)
    print(f"{nn:02d}편 → {new}")


def published_at(s: str):
    """`YYYY-MM-DD HH:MM` 또는 날짜만(sync 이전 기록)."""
    # ponytail: 날짜만 있는 옛 기록은 0시로 잡아 간격을 짧게 본다 — `sync`를 돌리면 시각이 채워진다
    return datetime.datetime.fromisoformat(s if len(s) > 10 else s + " 00:00")


def next_publish_slot(rows: list, now):
    """가장 빠른 발행 가능 시각 — 마지막 발행 + 36시간, 그리고 최근 7일 3편 한도.
    상태가 아니라 발행 시각으로 센다 — 25·26편은 HUMAN_REVIEW인 채 발행돼 상태로 세면 빠졌다(2026-10-28)."""
    times = sorted({published_at(r["published"]) for r in rows if r["published"]}, reverse=True)
    slot = now
    if times:
        slot = max(slot, times[0] + datetime.timedelta(hours=MIN_GAP_HOURS))
    if len(times) >= MAX_PER_WEEK:
        slot = max(slot, times[MAX_PER_WEEK - 1] + datetime.timedelta(days=7))
    return slot


def early_slot(rows: list, r: dict, when):
    """r이 when에 발행됐을 때, 그 앞 글들 기준 발행 가능 시각이 더 늦으면 그 시각. 지켰으면 None."""
    when = when.replace(tzinfo=None)      # 라이브 시각은 KST aware, 장부 시각은 KST naive다
    before = [x for x in rows if x is not r and x["published"] and published_at(x["published"]) < when]
    slot = next_publish_slot(before, when)
    return slot if slot > when else None


def slot_text(rows: list, now=None) -> str:
    """발행 가능 시각 안내. 장부만 보면 안 된다 — 27~29편이 발행됐는데 장부에 없어 "10-31 이후"라고 잘못 안내했다."""
    now = now or datetime.datetime.now()
    try:
        from verify_naver import recent
        live = [{"published": f"{p['when']:%Y-%m-%d %H:%M}"} for p in recent(10)]
        basis = "라이브 기준"
    except Exception as e:      # 네트워크·응답 형식 문제여도 원고 작업은 멈추지 않는다. 기준을 밝힌다
        live, basis = [], f"라이브를 못 읽어 장부 기준: {type(e).__name__}"
    slot = next_publish_slot(list(rows) + live, now)
    return (f"발행 가능 시각: {'지금' if slot <= now else f'{slot:%Y-%m-%d %H:%M} 이후'}"
            f" ({MIN_GAP_HOURS}시간 간격 · 7일 {MAX_PER_WEEK}편, {basis})")


def check_naver_v2_from() -> int:
    from check_naver import V2_FROM     # check_naver가 이 모듈을 가져오므로 함수 안에서 불러온다
    return V2_FROM


def fresh_gate(md: str, now):
    """2차 최신성 검사(업로드 직전). 재확인이 없거나 24시간을 넘겼으면 붙여넣기 파일을 만들지 않는다."""
    from check_naver import FRESH_HOURS, freshness_time
    t = freshness_time(md)
    if t is None or (now - t).total_seconds() > FRESH_HOURS * 3600:
        raise SystemExit(f"최신성 재확인이 {'없다' if t is None else f'{t:%m-%d %H:%M}로 {FRESH_HOURS}시간을 넘겼다'} — "
                         "개통·기간·금액을 공식 출처로 다시 보고 `- 최신성 재확인:` 줄을 고친 뒤 만든다")


def paste_gate(nn: int):
    """naver_paste.page_for가 부른다. 원고가 승인 흐름에 올라와 있지 않으면 붙여넣기 파일을 만들지 않는다.
    발행 가능 시각은 막지 않고 알린다 — 붙여넣기 파일은 미리 만들어 둘 수 있어야 한다."""
    if nn < RULES_FROM:
        return
    ledger = load_ledger()
    r = ledger.get(nn)
    if not r:
        raise SystemExit(f"{nn:02d}편이 _pipeline.csv에 없다 — `pipeline.py start`로 시작한 글만 붙여넣기 파일을 만든다")
    if r["status"] not in PASTE_OK:
        raise SystemExit(f"{nn:02d}편 상태가 {r['status']}이다 — HUMAN_REVIEW 이상(check_naver 통과)일 때 만든다")
    if not r["published"]:
        print(slot_text(ledger.values()))
    if nn >= check_naver_v2_from():
        fresh_gate(post_file(nn).read_text(encoding="utf-8"), datetime.datetime.now())


def cmd_list(_args=None):
    rows = read_csv(LEDGER, LEDGER_COLS)
    for r in rows[-12:]:
        print(f"{r['post']}  {r['status']:<20}{r['portfolio']:<4}{r['cluster']:<14}{r['primary_kw']}")
    new = [r for r in rows if num_of(r["post"]) >= RULES_FROM]
    print(f"\n전체 {len(rows)}편 · 25편 이후 {len(new)}편 (목표 비율 검색 70 / 홈피드 20 / 수익 10)")
    for k, v in PORTFOLIO.items():
        n = sum(r["portfolio"] == k for r in new)
        print(f"  {k}: {n}편" + (f" ({n / len(new):.0%})" if new else ""))
    if new and sum(r["portfolio"] == "수익" for r in new) / len(new) > PORTFOLIO["수익"]:
        print("  ⚠ 수익형이 10%를 넘었다")
    tc = track_counts(rows)
    print(f"\n최근 {sum(tc.values())}편 트랙: core {tc['core']} / seasonal {tc['seasonal']} "
          f"(내부 실험값 core 80 / seasonal 20 — 네이버 노출 기준이 아니다. 맞는 시즌 주제가 없으면 채우지 않는다)")


# ---- 내부링크 -------------------------------------------------------------

def link_candidates(nn: int, ledger: list, titles: dict) -> dict:
    me = next(r for r in ledger if num_of(r["post"]) == nn)
    sibs = [r for r in ledger if r["cluster"] and r["cluster"] == me["cluster"] and num_of(r["post"]) != nn]
    live = sorted((r for r in sibs if r["status"] in LIVE),
                  key=lambda r: (r["role"] != "hub", -contain(me["primary_kw"], titles.get(r["post"], ""))))
    return {"link": live[:3], "update": live, "next": [r for r in sibs if r["status"] not in LIVE]}


def anchor(r: dict) -> str:
    """링크 문구 = 그 글 제목의 앞부분(연도·부제 뺀 것). 태그형 키워드(공백 없음)는 문구로 어색하다."""
    t = re.sub(r"^20\d\d\s*", "", title_of(post_file(r["post"]).read_text(encoding="utf-8")))
    return re.split(r"\s*[|,]\s*", t)[0] or r["primary_kw"]


def cmd_links(args):
    nn = int(args[0])
    ledger = read_csv(LEDGER, LEDGER_COLS)
    titles = existing_titles()
    c = link_candidates(nn, ledger, titles)
    md = post_file(nn).read_text(encoding="utf-8")
    heads = re.findall(r"^## (\d+\. .+)$", md.split("## 작성 메모")[0], re.M)
    sections = [x for x in re.split(r"^## ", md.split("## 작성 메모")[0], flags=re.M)[1:] if re.match(r"\d+\. ", x)]
    print(f"{nn:02d}편 내부링크 후보 (같은 클러스터, 발행된 글):")
    for r in c["link"]:
        best = max(range(len(sections)), key=lambda i: contain(r["primary_kw"], sections[i]), default=None)
        where = sections[best].splitlines()[0] if best is not None and sections else "도입 문단 다음"
        print(f"  {r['post']}편 (logNo {r['logno'] or '미확인'}) 앵커: \"{anchor(r)}\" · 넣을 곳: ## {where}")
    if len(c["link"]) < 2:
        print("  ⚠ 발행된 같은 클러스터 글이 2개 미만이다 — 클러스터 글 규칙(내부 링크 2~3)은 비클러스터 발행 글로 나머지를 채운다")
    print("발행 후 링크 추가를 검토할 기존 글 (수정·재발행은 사용자 승인 필요):")
    for r in c["update"]:
        print(f"  {r['post']}편 {r['primary_kw']}")
    me = next(r for r in ledger if num_of(r["post"]) == nn)
    todo = sorted((x for x in read_csv(CANDS, CAND_COLS) if x["cluster"] == me["cluster"] and x["status"] == "IDEA"),
                  key=lambda x: to_int(x["order"]))
    print("같은 클러스터의 후속 글:", ", ".join(f"{x['id']} {x['keyword']}" for x in todo[:3]) or "없음")


def live_inlinks(html: str) -> set:
    return set(re.findall(r"education_blog/(\d{9,})", html)) | set(re.findall(r"logNo=(\d{9,})", html))


def broken_links(pages: dict, live_lognos: set) -> list:
    """pages: {logNo: html}. 우리 글이 가리키는 logNo가 목록에 없으면 (출처, 대상). 자기 자신은 제외."""
    return [(src, t) for src, h in pages.items() for t in sorted(live_inlinks(h)) if t != src and t not in live_lognos]


def cmd_linkcheck(_args=None):
    from verify_naver import _get
    ledger = read_csv(LEDGER, LEDGER_COLS)
    lognos = {r["logno"] for r in ledger if r["logno"] and r["status"] in LIVE}
    if not lognos:
        raise SystemExit("logNo가 있는 발행 글이 없다 — `pipeline.py sync`를 먼저 돌린다")
    pages = {}
    for n in sorted(lognos):
        resp = _get(f"https://m.blog.naver.com/education_blog/{n}")
        if resp.status_code != 200 or len(resp.text) < 5000:      # 작은 응답 = 삭제·비공개 안내 페이지로 본다
            print(f"⚠ {n}: 응답 {resp.status_code}, {len(resp.text)}자 — 삭제·비공개 가능성")
            continue
        pages[n] = resp.text
    bad = broken_links(pages, lognos)
    for src, t in bad:
        print(f"CHECK {src} → {t}: 발행 목록에 없는 글로 가는 링크 (삭제·비공개·오타) — 수정 후보")
    print("깨진 링크 의심 없음" if not bad else f"\n수정 후보 {len(bad)}건 (수정은 사용자 승인 후)")


def norm_title(t: str) -> str:
    return re.sub(r"[\s|｜:]", "", t)


def match_live(rows: list, titles: dict, live: list) -> dict:
    """글 → 라이브 글. logNo → 제목(구분자·공백 무시) → 비슷한 제목 순서로 찾고, 한 라이브 글은 한 번만 쓴다.
    사용자가 발행하면서 제목을 고치면 정확 대조로 못 찾아 27~29편이 발행된 줄 몰랐다(2026-10-31)."""
    by_logno = {p["logNo"]: p for p in live}
    out = {r["post"]: by_logno[r["logno"]] for r in rows if r["logno"] in by_logno}
    used = {p["logNo"] for p in out.values()} | {r["logno"] for r in rows if r["logno"]}
    rest = [r for r in rows if r["post"] not in out and not r["logno"]]
    for r in rest:
        p = next((x for x in live if x["logNo"] not in used and norm_title(x["title"]) == norm_title(titles[r["post"]])), None)
        if p:
            out[r["post"]] = p
            used.add(p["logNo"])
    for r in rest:
        if r["post"] in out:
            continue
        cand = [(jaccard(norm_title(titles[r["post"]]), norm_title(x["title"])), x["logNo"], x) for x in live if x["logNo"] not in used]
        if cand and max(cand, key=lambda c: c[0])[0] >= LIVE_MATCH_MIN:
            out[r["post"]] = max(cand, key=lambda c: c[0])[2]
            used.add(out[r["post"]]["logNo"])
    return out


def cmd_sync(_args=None):
    from verify_naver import recent
    rows = read_csv(LEDGER, LEDGER_COLS)
    live = []
    for page in range(1, 6):
        got = recent(30, page)
        live += got
        if len(got) < 30:
            break
    titles = {r["post"]: title_of(post_file(r["post"]).read_text(encoding="utf-8")) for r in rows}
    matched = match_live(rows, titles, live)
    for r in rows:
        p = matched.get(r["post"])
        if p and (not r["logno"] or len(r["published"]) <= 10):      # 발행 간격을 보려고 시각까지 넣는다
            fresh = not r["published"]
            r["logno"], r["published"] = p["logNo"], f"{p['when']:%Y-%m-%d %H:%M}"
            # 간격 경고는 `status PUBLISHED`가 시각을 처음 쓸 때만 떴다. sync가 먼저 채우면 건너뛰어
            # 33편이 32편 2시간 뒤에 발행됐는데 아무것도 알리지 않았다(2026-11-05)
            slot = early_slot(rows, r, p["when"]) if fresh else None
            if slot:
                print(f"⚠ {r['post']}편: 발행 간격 초과 — {p['when']:%Y-%m-%d %H:%M}에 발행됐는데 {slot:%Y-%m-%d %H:%M} 이후가 맞았다 "
                      f"({MIN_GAP_HOURS}시간 · 7일 {MAX_PER_WEEK}편)")
        if p and norm_title(p["title"]) != norm_title(titles[r["post"]]) and num_of(r["post"]) >= RULES_FROM:
            print(f"⚠ {r['post']}편: 라이브 제목이 원고와 다르다 — {p['title'].strip()}")
    write_csv(LEDGER, LEDGER_COLS, rows)
    print(f"logNo {sum(bool(r['logno']) for r in rows)}/{len(rows)}편 확인")
    for r in rows:      # 발행 뒤 제목을 고친 글(6·14편)은 제목 대조로 못 찾는다 — 조용히 넘기지 않고 알린다
        if not r["logno"]:
            print(f"⚠ {r['post']}편: 라이브 목록에서 제목이 일치하는 글이 없다 — logNo를 손으로 채운다")
        elif r["status"] not in LIVE:     # APPROVED는 사람만 넣으므로 상태를 대신 바꾸지 않는다
            print(f"⚠ {r['post']}편: 라이브에 있는데 상태가 {r['status']}이다 — 사용자가 `status {r['post']} APPROVED` 후 "
                  f"`status {r['post']} PUBLISHED {r['logno']}`로 기록한다")


# ---- 성과 -------------------------------------------------------------------

def grade(p: dict, avg_views: float) -> str:
    """요청서 15절. 검색 유입 발생 여부가 조회수보다 먼저다."""
    if p["flag"]:
        return "E"
    views, search = to_int(p["views"]), to_int(p["search_in"])
    react = to_int(p["home_in"]) + to_int(p["likes"]) + to_int(p["comments"])
    if search > 0:
        return "A" if avg_views and views >= 1.5 * avg_views else "B"
    return "C" if react > 0 else "D"


def due_checkpoints(published: str, done: set, today) -> list:
    d = datetime.date.fromisoformat(published[:10])
    age = (today - d).days      # 발행 직후 값이 아니면 의미가 없으니 점검 기한이 지난 칸은 묻지 않는다
    return [k for k, days in CHECKPOINTS.items() if days <= age <= days + GRACE_DAYS and k not in done]


def cmd_perf(args, today=None):
    today = today or datetime.date.today()
    rows = read_csv(PERF, PERF_COLS)
    if args[:1] == ["add"]:
        nn, cp = int(args[1]), args[2]
        if cp not in CHECKPOINTS:
            raise SystemExit(f"체크포인트는 {'·'.join(CHECKPOINTS)}")
        rec = {c: "" for c in PERF_COLS}
        rec.update(post=f"{nn:02d}", checkpoint=cp, date=today.isoformat())
        for kv in args[3:]:
            k, _, v = kv.partition("=")
            if k not in PERF_COLS:
                raise SystemExit(f"알 수 없는 지표: {k}")
            rec[k] = v
        if rec["ctr"] and not rec["impressions"]:
            raise SystemExit("노출수 없이 클릭률을 기록하지 않는다 (추정 금지)")
        same = [to_int(r["views"]) for r in rows if r["checkpoint"] == cp and r["views"]]
        rec["grade"] = grade(rec, sum(same) / len(same) if same else 0)
        rows = [r for r in rows if not (r["post"] == rec["post"] and r["checkpoint"] == cp)] + [rec]
        write_csv(PERF, PERF_COLS, rows)
        print(f"{rec['post']}편 {cp} 등급 {rec['grade']}")
        if rec["search_kw"]:
            # 예전에는 검색어마다 후보를 하나씩 만들었다 — 검색어마다 글 하나가 된다. 관측으로만 쌓고 `queries plan`이 묶는다
            qrows = read_csv(QUERIES, QUERY_COLS)
            for kw in rec["search_kw"].split("|"):
                if kw.strip():
                    qrows, _ = add_query(qrows, {"captured_at": rec["date"], "metric": "query", "post": rec["post"],
                                                 "query": kw.strip(), "source": f"perf add {cp}", "note": "기간·건수 미기재"})
            write_csv(QUERIES, QUERY_COLS, qrows)
            print(f"검색 유입 키워드 \"{rec['search_kw']}\" → {QUERIES.name}에 기록. `queries plan`으로 기존 글과 대조한다")
        if cp == "30d" and rec["grade"] in ("D", "C") and not to_int(rec["search_in"]):
            print("30일간 검색 유입 없음 → 제목·도입·검색 의도 재검토 (삭제하지 않는다, UPDATE_REQUIRED 후보)")
        return
    done = {(r["post"], r["checkpoint"]) for r in rows}
    for r in read_csv(LEDGER, LEDGER_COLS):
        if r["status"] in LIVE and r["published"]:
            d = due_checkpoints(r["published"], {k for p, k in done if p == r["post"]}, today)
            if d:
                print(f"{r['post']}편 {r['primary_kw'][:24]:<24} 발행 {r['published']} — 점검 대상: {', '.join(d)}")


# ---- 실제 유입 검색어 (2026-11-06) ----------------------------------------
# 통계 캡처를 손으로 옮긴다. 화면에 없는 값은 비워 두고, 비율로 건수를 역산하지 않는다.

QUERIES, GROUPS = DIR / "_queries.csv", DIR / "_query_groups.csv"
QUERY_COLS = ["captured_at", "period_start", "period_end", "period_type", "complete", "metric", "post", "query",
              "count", "share", "source", "note"]
QUERY_KEY = ("period_start", "period_end", "period_type", "metric", "post", "query", "source")
QUERY_METRICS = {"views", "visitors", "search_in", "query"}
GROUP_COLS = ["group_id", "queries", "intent", "observations", "post", "overlap", "decision", "reason", "boundary",
              "title_thumb", "related"]
INTENTS = [("오류·누락", r"수정|정정|잘못|오류|누락|경정"), ("금액·계산", r"얼마|계산|금액|세율|가산세"),
           ("기한·일정", r"기한|기간|언제|마감"), ("절차·신청", r"방법|신청|홈택스|하는\s?법|절차"),
           ("자격·가능", r"조건|대상|가능|될까|되나"), ("비교·선택", r"vs|차이|비교"),
           ("예외 상황", r"같은\s?날|해외|알바|집체|심리검사")]
RELATED_AT = 0.20      # `실업급여 5차`↔`5차 실업인정`이 0.25다. 병합이 아니라 관련 표시라 낮게 둔다


def add_query(rows: list, rec: dict) -> tuple:
    """→ (rows, 추가했나). 같은 캡처를 다시 넣으면 중복으로 본다."""
    rec = {c: (rec.get(c) or "").strip() for c in QUERY_COLS}
    if rec["metric"] not in QUERY_METRICS:
        raise ValueError(f"metric은 {'·'.join(sorted(QUERY_METRICS))} 중 하나다: {rec['metric']}")
    if rec["post"]:
        rec["post"] = f"{num_of(rec['post']):02d}"
    key = tuple(rec[k] for k in QUERY_KEY)
    if any(tuple(r[k] for k in QUERY_KEY) == key for r in rows):
        return rows, False
    return rows + [rec], True


def intent_of(q: str) -> str:
    """낱말이 나오는 순서대로 의도를 잇는다. `수정신고 방법`은 오류·누락+절차·신청이다."""
    hits = sorted((m.start(), name) for name, pat in INTENTS for m in [re.search(pat, q)] if m)
    return "+".join(dict.fromkeys(n for _, n in hits)) or "미분류"


def group_queries(rows: list) -> list:
    """검색어 → 묶음. 공백을 지운 글자가 같거나 낱말 집합이 같을 때만 묶는다. 비슷한 것은 related로만 남긴다."""
    groups = []
    for r in rows:
        if r["metric"] != "query" or not r["query"]:
            continue
        q = r["query"]
        flat, words = re.sub(r"\s+", "", q), frozenset(q.split())
        g = next((g for g in groups if flat in g["flat"] or words in g["words"]), None)
        if not g:
            g = {"flat": set(), "words": set(), "queries": [], "rows": []}
            groups.append(g)
        g["flat"].add(flat)
        g["words"].add(words)
        if q not in g["queries"]:
            g["queries"].append(q)
        g["rows"].append(r)
    for i, g in enumerate(groups, 1):
        g["id"], g["intent"] = f"q{i:02d}", intent_of(g["queries"][0])
        g["obs"] = len({(r["period_start"], r["period_end"], r["post"], r["source"]) for r in g["rows"]})
    for g in groups:
        a = min(g["flat"])
        g["related"] = [h["id"] for h in groups if h is not g and jaccard(a, min(h["flat"])) >= RELATED_AT]
    return groups


def judge_group(g: dict, bodies: dict, titles: dict) -> dict:
    """묶음 → UPDATE·NEW·HOLD와 근거. 원고는 읽기만 한다. 제목·대표사진은 늘 keep이다."""
    landed = [r["post"] for r in g["rows"] if r["post"]]
    text = " ".join(g["queries"])
    best, cover = max(((k, contain(text, t)) for k, t in titles.items()), key=lambda x: x[1], default=("", 0))
    post = max(set(landed), key=landed.count) if landed else best if cover >= 0.70 else ""
    out = {"group_id": g["id"], "queries": " | ".join(g["queries"]), "intent": g["intent"], "observations": str(g["obs"]),
           "post": post, "overlap": f"{cover:.2f}" if not landed else "유입", "title_thumb": "keep",
           "related": " ".join(g["related"])}
    if post:
        body = re.sub(r"\s+", "", bodies.get(post, ""))
        missing = [w for w in dict.fromkeys(w for q in g["queries"] for w in q.split()) if re.sub(r"\s+", "", w) not in body]
        if missing:
            return {**out, "decision": "UPDATE", "reason": f"{post}편 본문에 없는 낱말: {', '.join(missing)}",
                    "boundary": f"{post}편의 질문 안에서 본문 보완만 제안한다. 새 글로 쪼개지 않는다"}
        return {**out, "decision": "HOLD", "reason": f"{post}편 본문이 이미 이 낱말을 모두 다룬다",
                "boundary": f"{post}편과 같은 질문 — 새 글이면 중복이다"}
    if g["obs"] >= 2:
        return {**out, "decision": "NEW", "reason": f"맞는 글 없음(최대 겹침 {best}편 {cover:.2f}), 관측 {g['obs']}회. 공식 근거 확인 전(official=?)",
                "boundary": f"가장 가까운 글은 {best}편 — 그 글이 답하지 않는 상황만 다룬다"}
    return {**out, "decision": "HOLD", "reason": "맞는 글이 없고 관측이 1회뿐이다", "boundary": "관측이 더 쌓이면 다시 본다"}


def query_trend(rows: list) -> tuple:
    """→ (비교 줄, 제외 행 수). 기간이 있고 집계가 끝났고 건수가 있는 행끼리, 같은 길이의 바로 앞 기간과만 비교한다."""
    nums = [r for r in rows if r["metric"] != "query"]
    ok = [r for r in nums if r["period_start"] and r["period_end"] and r["complete"] == "Y" and r["count"]]
    lines = []
    for key in sorted({(r["metric"], r["post"], r["period_type"]) for r in ok}):
        seq = sorted((r for r in ok if (r["metric"], r["post"], r["period_type"]) == key), key=lambda r: r["period_start"])
        for a, b in zip(seq, seq[1:]):
            span = lambda r: (datetime.date.fromisoformat(r["period_end"]) - datetime.date.fromisoformat(r["period_start"])).days
            if span(a) != span(b) or datetime.date.fromisoformat(b["period_start"]) - datetime.date.fromisoformat(a["period_end"]) != datetime.timedelta(days=1):
                continue
            prev, cur = to_int(a["count"]), to_int(b["count"])
            lines.append((key[0], key[1] or "전체", b["period_start"], b["period_end"], prev, cur,
                          f"{(cur - prev) / prev:+.0%}" if prev else "-"))
    return lines, len(nums) - len(ok)


def post_bodies() -> dict:
    return {p.name[:2]: p.read_text(encoding="utf-8").split("## 작성 메모")[0] for p in DIR.glob("[0-9][0-9]_*.md")}


def cmd_queries(args):
    rows = read_csv(QUERIES, QUERY_COLS)
    sub = args[0] if args else "plan"
    if sub in ("add", "import"):
        if sub == "add":
            recs = [dict(kv.partition("=")[::2] for kv in args[1:])]
        else:
            with open(args[1], encoding="utf-8-sig", newline="") as f:
                recs = list(csv.DictReader(f))
        added = 0
        for rec in recs:
            unknown = set(rec) - set(QUERY_COLS)
            if unknown:
                raise SystemExit(f"알 수 없는 열: {', '.join(sorted(unknown))}")
            rec.setdefault("captured_at", f"{datetime.datetime.now():%Y-%m-%d %H:%M}")
            rows, ok = add_query(rows, rec)
            added += ok
            if not ok:
                print(f"중복이라 넣지 않았다: {rec.get('metric')} {rec.get('post')} {rec.get('query')} {rec.get('period_start')}")
        write_csv(QUERIES, QUERY_COLS, rows)
        print(f"{added}행 추가 · 전체 {len(rows)}행")
    elif sub == "trend":
        lines, skipped = query_trend(rows)
        for m, p, a, b, prev, cur, pct in lines:
            print(f"{m:<10}{p:<5}{a}~{b}  {prev} → {cur}  {pct}")
        print(f"추세 제외 {skipped}행 (기간·완료 여부·건수 불명) — 참고 신호로만 쓴다")
    elif sub == "plan":
        out = [judge_group(g, post_bodies(), existing_titles()) for g in group_queries(rows)]
        write_csv(GROUPS, GROUP_COLS, out)
        for o in out:
            print(f"{o['group_id']} {o['decision']:<6} {o['post'] or '-':<3} [{o['intent']}] {o['queries']}  — {o['reason']}"
                  + (f"  (관련: {o['related']})" if o["related"] else ""))
        print(f"→ {GROUPS.name}. NEW는 공식 근거를 확인한 뒤 사람이 _candidates.csv에 넣는다(자동으로 넣지 않는다)")
    else:
        raise SystemExit("queries add key=value ... | queries import 파일.csv | queries trend | queries plan")


# ---- 자체 시험 ----------------------------------------------------------

def selftest():
    # 상태 전이
    check_move("HUMAN_REVIEW", "APPROVED", tty=True)
    for cur, new, kw in [("DRAFT", "PUBLISHED", {}), ("HUMAN_REVIEW", "APPROVED", {"tty": False}),
                         ("APPROVED", "PUBLISHED", {"logno": ""}), ("REJECTED", "DRAFT", {})]:
        try:
            check_move(cur, new, **kw)
            raise AssertionError(f"{cur}→{new}이 통과했다")
        except ValueError:
            pass
    check_move("APPROVED", "PUBLISHED", "224452380631")
    assert PASTE_OK.isdisjoint({"IDEA", "DRAFT", "SEO_REVIEW", "FACT_CHECK_REQUIRED", "REJECTED"})

    # 점수 — 조건이 붙은 질문형 롱테일은 통과, 대표 키워드는 보류 이하
    today = datetime.date(2026, 10, 24)
    led = [{"post": "12", "cluster": "부양가족", "status": "PUBLISHED", "role": "hub"}]
    good = dict(keyword="국민연금 받는 부모님 연말정산 인적공제 가능할까", cluster="부양가족", role="spoke", geo_cited="3",
                serp_fresh="10", official="1", diff="1", season="11|12|1")
    short = dict(keyword="연말정산", cluster="", role="", geo_cited="", serp_fresh="10", official="0", diff="0", season="1")
    s1, p1, d1 = score_one(good, led, {}, today)
    s2, _, d2 = score_one(short, led, {}, today)
    assert s1 == 100 and d1 == "CREATE_SUPPORTING_POST", (s1, p1, d1)
    assert d2 in ("HOLD", "REJECTED") and s2 < ACCEPT_AT, (s2, d2)
    assert score_one({**good, "cluster": "", "role": ""}, led, {}, today)[2] == "CREATE_NEW"
    for core in ("근로장려금 기한 후 신청 방법", "퇴직금 세금 계산 방법", "기초연금 수급 기준"):    # 클러스터 밖 핵심 주제가 폐기되면 안 된다
        assert score_one({**good, "keyword": core, "cluster": "", "role": ""}, led, {}, today)[0] >= ACCEPT_AT, core
    # T3 기존 글과 의도가 70% 이상 겹치면 새 글 대신 업데이트, 허브와 60~70%면 허브 확장
    _, _, d3 = score_one(good, led, {"12": "국민연금 받는 부모님 연말정산 인적공제 가능할까 부양가족"}, today)
    assert d3 == "UPDATE_EXISTING"
    half = {"12": "국민연금 받는 부모님 연말정산 공제"}
    assert 0.6 <= contain(good["keyword"], half["12"]) < 0.7, contain(good["keyword"], half["12"])
    assert score_one(good, led, half, today)[2] == "EXPAND_HUB"
    assert score_one(good, led, {"12": "국민연금 받는 부모님 결과"}, today)[2] == "CREATE_SUPPORTING_POST"   # 공통어만 겹침
    # T4 인기 있지만 무관한 키워드
    # 시즌 후보 — 관측 수요가 없으면 점수 없이 보류, 있으면 시즌 가중치로 채점
    sea = {c: "" for c in CAND_COLS}
    sea.update(id="hs-01", keyword="난방비 절약 외출모드", track="seasonal", diff="1", official="1", season=str(today.month))
    assert score_one(sea, led, {}, today)[:3:2] == ("", "HOLD"), "수요 근거 미확인은 숫자로 포장하지 않는다"
    got = score_one({**sea, "serp_fresh": "7"}, led, {}, today)
    assert got[0] == 100 and got[2] == "CREATE_NEW", got
    assert score_one({**sea, "serp_fresh": "7", "keyword": "인기 드라마 결말"}, led, {}, today)[2] == "REJECTED"
    s4, _, d4 = score_one({**short, "keyword": "인기 드라마 결말"}, led, {}, today)
    assert s4 < HOLD_AT and d4 == "REJECTED"
    assert ALIASES["READY_FOR_APPROVAL"] == "HUMAN_REVIEW" and set(ALIASES.values()) <= set(ALLOWED) | {"RESEARCHING"}
    check_move("DRAFT", "EVIDENCE_REQUIRED")
    check_move("QA_BLOCKED", "DRAFT")
    check_move("PERFORMANCE_REVIEW", "RETIRED")

    # 발행 간격 — 마지막 발행 + 36시간, 최근 7일 3편
    now = datetime.datetime(2026, 10, 28, 12, 0)

    def pub(*ts):
        return [{"status": "PUBLISHED", "published": t} for t in ts]
    assert next_publish_slot(pub("2026-10-26 23:00"), now) == now                        # 37시간 지났다
    led = [{"post": "32", "published": "2026-11-04 22:02"}, {"post": "33", "published": ""}]
    assert early_slot(led, led[1], datetime.datetime(2026, 11, 5, 0, 3)) == datetime.datetime(2026, 11, 6, 10, 2), "33편: 2시간 뒤 발행은 경고"
    assert early_slot(led, led[1], datetime.datetime(2026, 11, 6, 11, 0)) is None
    kst = datetime.timezone(datetime.timedelta(hours=9))      # sync는 라이브의 aware 시각을 넘긴다 — naive만 시험해 첫 실행에서 TypeError가 났다
    assert early_slot(led, led[1], datetime.datetime(2026, 11, 5, 0, 3, tzinfo=kst)) == datetime.datetime(2026, 11, 6, 10, 2)
    assert next_publish_slot(pub("2026-10-27 01:00"), now) == datetime.datetime(2026, 10, 28, 13, 0)   # 35시간 → 1시간 뒤
    assert next_publish_slot(pub("2026-10-27", "2026-10-24 09:00"), now) == now          # 날짜만 있는 기록은 0시
    three = pub("2026-10-22 09:00", "2026-10-24 09:00", "2026-10-26 09:00")      # 7일 안에 3편 → 4편째는 첫 글 + 7일
    assert next_publish_slot(three, now) == datetime.datetime(2026, 10, 29, 9, 0)
    assert next_publish_slot([{"status": "HUMAN_REVIEW", "published": ""}], now) == now
    assert next_publish_slot([{"status": "HUMAN_REVIEW", "published": "2026-10-27 20:00"}], now) > now   # 상태와 무관하게 센다

    # 2차 최신성 — 24시간 넘은 재확인은 붙여넣기 파일을 막는다
    fm = "- 최신성 재확인: 2026-10-28 12:00 | 미리보기 2026 | https://www.nts.go.kr/x\n"
    assert fresh_gate(fm, now) is None
    for bad_md, at in ((fm, now + datetime.timedelta(hours=24, minutes=1)), ("메모 없음", now)):
        try:
            fresh_gate(bad_md, at)
            raise AssertionError("낡은 재확인이 통과했다")
        except SystemExit:
            pass

    # 라이브 대조 — 발행 때 고친 제목(27편 실제 사례)도 찾고, 다른 글과 섞지 않는다
    t27 = "2026 맞벌이 부부 연말정산 부양가족 공제 | 카드 합산 안 될 때 누가 올릴까? 25% 계산"
    t28 = "2026 연말정산 부양가족 잘못 공제했을 때 | 경정청구와 수정신고, 5년·2년 기한은?"
    live_ = [{"logNo": "1", "title": "2026 맞벌이 연말정산｜부양가족 공제는 누가? 카드 25% 기준까지"},
             {"logNo": "2", "title": "2026 연말정산 부양가족 잘못 공제했을 때｜경정청구와 수정신고, 5년·2년 기한은?"},
             {"logNo": "3", "title": "실업급여 이직확인서 받는 법"}]
    rows_ = [{"post": "27", "logno": ""}, {"post": "28", "logno": ""}, {"post": "30", "logno": ""}]
    got = match_live(rows_, {"27": t27, "28": t28, "30": "자녀 세액공제 금액 개정 내용"}, live_)
    assert got["28"]["logNo"] == "2" and got["27"]["logNo"] == "1" and "30" not in got, got
    assert next_publish_slot(pub("2026-10-27 01:00", "2026-10-27 01:00"), now) == datetime.datetime(2026, 10, 28, 13, 0)  # 장부·라이브 중복은 한 번만
    three2 = pub("2026-10-26 09:00", "2026-10-26 09:00", "2026-10-24 09:00", "2026-10-22 09:00")
    assert next_publish_slot(three2, now) == datetime.datetime(2026, 10, 29, 9, 0)

    # 유사도 — 제목·본문·도입·질문 재사용을 잡고, 고정 문구는 오탐하지 않는다
    fixed = "공유하고 싶은 분께 이 글을 보내 주세요.\n"

    def doc(title, intro, body, q, last):
        return (f"제목: {title}\n\n---\n\n\"질문?\"\n\n[이미지 ①: x]\n\n{intro}\n\n## 1. 소제목 {title[:6]}\n\n{body}\n\n"
                f"## 오늘의 살림 정리\n\n{fixed}{last}\n\n## 🐷 새싹돼지 Q&A\n\n> [질문] {q}\n> 답변입니다.\n\n"
                f"## 작성 메모\n- 썸네일 문구: 가 | 나{title[-4:]}\n")
    a = doc("2026 연말정산 부양가족 기준 소득 100만원", "부양가족 소득금액이 100만원 이하여야 공제를 받습니다.", "본문 가나다라마바사 아자차카타파하" * 6, "부모님도 되나요?", "마지막 줄 A")
    b = doc("2026 월세 세액공제 총급여 7천만원 한도", "월세 공제는 총급여 구간이 중요합니다.", "전혀 다른 내용입니다 사과 바나나 딸기 포도" * 6, "전입신고는 언제?", "마지막 줄 B")
    c = doc("2026 연말정산 부양가족 기준 소득 100만원", "부양가족 소득금액이 100만원 이하여야 공제를 받습니다.", "본문 가나다라마바사 아자차카타파하" * 6, "부모님도 되나요?", "마지막 줄 A")
    boiler = boilerplate({"a": a, "b": b, "c": c, "d": a, "e": b})
    assert similarity_issues(b, {"01편": a}, boiler) == [], similarity_issues(b, {"01편": a}, boiler)
    got = " ".join(similarity_issues(c, {"01편": a}, boiler))
    for key in ("제목이", "본문이", "도입 첫 문장", "결론", "Q&A 질문", "썸네일 문구"):
        assert key in got, key
    assert any("AI 문체" in x for x in similarity_issues(b.replace("전혀 다른", "결론적으로 결론적으로 전혀 다른"), {}, boiler))

    # 필수 기록
    good_memo = ("제목: t\n\n본문 [내부 링크 ①] [내부 링크 ②]\n\n## 작성 메모\n- 포트폴리오: 검색\n- 클러스터: 부양가족\n- 차별화 요소: 비교표 | 가능·불가능 판정\n"
                 "- 적용 기준일: 2026-10-24\n- 내부 링크 대상: 12 | 15\n"
                 "- 출처: 국세청 | 연말정산 안내 | https://www.nts.go.kr/x | 2026-10-24\n"
                 "- 출처: 법제처 | 소득세법 제50조 | https://www.law.go.kr/y | 2026-10-24\n"
                 "[내부 링크 ①]\n[내부 링크 ②]\n")
    led2 = {12: {"status": "PUBLISHED", "cluster": "부양가족"}, 15: {"status": "PUBLISHED", "cluster": ""}}
    assert required_issues(good_memo, led2) == [], required_issues(good_memo, led2)
    assert any("클러스터의 발행된 글" in x for x in required_issues(good_memo.replace("12 | 15", "15 | 15"), led2))
    bad = good_memo.replace("검색", "광고").replace("| 가능·불가능 판정", "").replace("https://www.nts.go.kr/x", "없음")
    got = " ".join(required_issues(bad, {12: {"status": "PUBLISHED"}, 15: {"status": "DRAFT"}}))
    for key in ("포트폴리오", "차별화", "출처 줄 형식", "15편이 발행된 글이 아니다"):
        assert key in got, key

    # 성과 등급
    base = {"flag": "", "views": "0", "search_in": "0", "home_in": "0", "likes": "0", "comments": "0"}
    assert grade({**base, "views": "20", "search_in": "1"}, 10) == "A"
    assert grade({**base, "views": "10", "search_in": "1"}, 10) == "B"
    assert grade({**base, "home_in": "3"}, 10) == "C" and grade(base, 10) == "D"
    assert grade({**base, "flag": "중복위험", "search_in": "5"}, 10) == "E"
    assert due_checkpoints("2026-10-01", {"24h"}, datetime.date(2026, 10, 9)) == ["7d"]
    assert "28d" in due_checkpoints("2026-10-01", {"24h", "7d"}, datetime.date(2026, 10, 29)), "대표사진 효과는 7일·28일로 본다"
    assert {"thumb_changed_at", "title_changed", "impressions", "ctr"} <= set(PERF_COLS)
    assert due_checkpoints("2026-10-01", set(), datetime.date(2026, 10, 20)) == []

    # 링크 점검 — 목록에 없는 logNo로 가는 링크만 잡는다
    h = '<a href="https://blog.naver.com/education_blog/224000000001">a</a> <a href="https://blog.naver.com/education_blog/224000000009">b</a>'
    assert broken_links({"224000000002": h}, {"224000000001", "224000000002"}) == [("224000000002", "224000000009")]
    assert post_issues(sorted(DIR.glob("[0-9][0-9]_*.md"))[0]) == ([], [])        # 24편 이전 글은 새 규칙 대상이 아니다
    assert paste_gate(24) is None
    # 실제 유입 검색어 — 날짜 없는 캡처, 중복, 묶음, 판정
    q = lambda **k: {"metric": "query", **k}
    rows, ok = add_query([], q(post="28", query="수정신고 방법", source="a.png"))
    rows, dup = add_query(rows, q(post="28", query="수정신고 방법", source="a.png"))
    assert ok and not dup and len(rows) == 1, "같은 캡처 재입력은 중복"
    rows, _ = add_query(rows, {"metric": "views", "post": "", "share": "12%", "source": "b.png"})
    assert rows[-1]["count"] == "", "비율로 건수를 역산하지 않는다"
    wk = [{"metric": "views", "period_type": "week", "complete": "Y", "period_start": a, "period_end": b, "count": c, "source": "s"}
          for a, b, c in (("2026-10-19", "2026-10-25", "150"), ("2026-10-26", "2026-11-01", "186"))]
    for w in wk:
        rows, _ = add_query(rows, w)
    lines, skipped = query_trend(rows)
    assert len(lines) == 1 and lines[0][4:] == (150, 186, "+24%") and skipped == 1, (lines, skipped)
    for t in ("5차실업인정", "5차 실업인정", "실업급여 5차", "수정신고 가산세"):
        rows, _ = add_query(rows, q(post="", query=t, source="c.png"))
    gs = {g["queries"][0]: g for g in group_queries(rows)}
    assert gs["5차실업인정"]["queries"] == ["5차실업인정", "5차 실업인정"], "띄어쓰기만 다르면 한 묶음, 원문 둘 다 남긴다"
    assert "실업급여 5차" in gs and gs["실업급여 5차"]["id"] in gs["5차실업인정"]["related"], "비슷한 것은 관련 후보로만"
    assert gs["수정신고 방법"]["intent"] == "오류·누락+절차·신청" and gs["수정신고 가산세"]["intent"] == "오류·누락+금액·계산"
    bodies = {"28": "수정신고는 홈택스에서 합니다. 방법은 아래와 같습니다."}
    titles = {"28": "연말정산 부양가족 잘못 공제 수정신고", "19": "실업급여 구직활동 5차"}
    j = judge_group(gs["수정신고 방법"], bodies, titles)
    assert j["decision"] == "HOLD" and j["post"] == "28" and j["title_thumb"] == "keep", j
    j = judge_group(gs["수정신고 가산세"], {"28": bodies["28"]}, {"28": "연말정산 부양가족 수정신고 가산세"})
    assert j["decision"] == "UPDATE" and "가산세" in j["reason"] and j["title_thumb"] == "keep", j
    assert judge_group(gs["실업급여 5차"], {}, {"40": "근로장려금"})["decision"] == "HOLD", "맞는 글 없고 관측 1회면 보류"
    rows, _ = add_query(rows, q(post="", query="실업급여 5차", source="d.png", period_start="2026-11-02"))
    g = next(g for g in group_queries(rows) if g["queries"][0] == "실업급여 5차")
    assert judge_group(g, {}, {"40": "근로장려금"})["decision"] == "NEW", "독립 질문이 두 번 관측되면 새 글 후보"
    print("selftest ok")


COMMANDS = {"score": cmd_score, "start": cmd_start, "status": cmd_status, "list": cmd_list, "links": cmd_links,
            "linkcheck": cmd_linkcheck, "sync": cmd_sync, "perf": cmd_perf, "queries": cmd_queries}

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) > 1 and sys.argv[1] in COMMANDS:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    else:
        print(__doc__)
