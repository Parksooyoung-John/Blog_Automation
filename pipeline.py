"""블로그 파이프라인 — 후보 점수화, 발행 상태 기록, 내부링크 추천, 글 간 유사도, 글 단위 성과.

    python -X utf8 pipeline.py score [--register]     # _candidates.csv 채점 (7점 이상 후보, 5~6 보류, 4 이하 폐기)
    python -X utf8 pipeline.py start 후보ID            # 후보 → 새 편 번호를 받고 DRAFT
    python -X utf8 pipeline.py status NN 상태 [logNo]  # 상태 이동 (순서 강제, APPROVED는 사람이 터미널에서만)
    python -X utf8 pipeline.py list                    # 발행 상태·포트폴리오 비율
    python -X utf8 pipeline.py links NN                # 내부링크 후보·넣을 문단·기존 글 수정 후보·후속 글
    python -X utf8 pipeline.py sync                    # 라이브 목록에서 logNo·발행일 채우기
    python -X utf8 pipeline.py linkcheck               # 발행 글의 내부 링크가 살아 있는 글을 가리키는지
    python -X utf8 pipeline.py perf                    # 24h·7d·30d 점검 대상
    python -X utf8 pipeline.py perf add NN 24h views=9 search_in=1 search_kw=키워드 ...
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
             "official", "diff", "season", "score", "decision", "status", "post"]
PERF_COLS = ["post", "checkpoint", "date", "views", "visitors", "search_in", "search_kw", "home_in", "avg_time",
             "likes", "comments", "link_clicks", "threads_in", "flag", "grade"]

# 순서 있는 본선. SCHEDULED는 예약발행을 쓸 때만 거친다.
FLOW = ["IDEA", "RESEARCHING", "DRAFT", "SEO_REVIEW", "HUMAN_REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED"]
ALLOWED = {
    "DRAFT": {"SEO_REVIEW", "FACT_CHECK_REQUIRED", "REJECTED"},
    "FACT_CHECK_REQUIRED": {"DRAFT", "RESEARCHING", "REJECTED"},
    "SEO_REVIEW": {"HUMAN_REVIEW", "DRAFT", "FACT_CHECK_REQUIRED", "REJECTED"},
    "HUMAN_REVIEW": {"APPROVED", "DRAFT", "FACT_CHECK_REQUIRED", "REJECTED"},
    "APPROVED": {"SCHEDULED", "PUBLISHED", "HUMAN_REVIEW"},
    "SCHEDULED": {"PUBLISHED", "HUMAN_REVIEW"},
    "PUBLISHED": {"PERFORMANCE_REVIEW"},
    "PERFORMANCE_REVIEW": {"UPDATE_REQUIRED", "PUBLISHED"},
    "UPDATE_REQUIRED": {"HUMAN_REVIEW", "PUBLISHED"},
    "REJECTED": set(),
}
PASTE_OK = {"HUMAN_REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED", "PERFORMANCE_REVIEW", "UPDATE_REQUIRED"}
LIVE = {"PUBLISHED", "PERFORMANCE_REVIEW", "UPDATE_REQUIRED"}
PORTFOLIO = {"검색": 0.70, "홈피드": 0.20, "수익": 0.10}
RULES_FROM = 25            # 클러스터·유사도·출처 기록 규칙을 판정에 넣는 첫 편 (24편까지는 발행됨)
SCOPE = re.compile(r"연말정산|세액공제|소득공제|세금|연금|노후|장려금|지원금|실업급여|건강보험|고용보험|부양가족|인적공제")
INTENT = re.compile(r"\d|가능|언제|며칠|차이|조건|기준|기간|방법|되나|될까|vs|비교|없이")
CHECKPOINTS = {"24h": 1, "7d": 7, "30d": 30}
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


def season_ok(season: str, today) -> bool:
    months = {to_int(m) for m in season.split("|") if m.strip()}
    return bool(months & {today.month, today.month % 12 + 1, (today.month + 1) % 12 + 1})


def score_one(c: dict, ledger_rows: list, titles: dict, today) -> tuple:
    """후보 한 줄 → (점수, 항목별, 결정). 사람 판단 항목(official·diff)은 CSV 값을 그대로 읽는다."""
    kw = c["keyword"]
    words = kw.split()
    parts = {
        "관련성": 2 if c["cluster"] else 1 if SCOPE.search(kw) else 0,
        "의도": min(2, (len(words) >= 3) + bool(INTENT.search(kw))),
        "공략": min(2, (len(words) >= 4 or bool(re.search(r"\d", kw))) + (to_int(c["geo_cited"]) >= 3
                                                                        or 0 < to_int(c["serp_fresh"]) <= 7)),
        "공식": 1 if c["official"] == "1" else 0,
        "차별": 1 if c["diff"] == "1" else 0,
        "링크": 1 if c["cluster"] and any(r["cluster"] == c["cluster"] and r["status"] in LIVE for r in ledger_rows) else 0,
        "적시": 1 if season_ok(c["season"], today) else 0,
    }
    total = sum(parts.values())
    cover = max((contain(kw, t) for t in titles.values()), default=0)
    if cover >= 0.70:
        return total, parts, "UPDATE_EXISTING"
    return total, parts, "IDEA" if total >= 7 else "HOLD" if total >= 5 else "REJECTED"


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
            c["status"] = decision
        print(f"{c['id']:<8}{total:>2}점 {decision:<16}{c['keyword']}  " + " ".join(f"{k}{v}" for k, v in parts.items()))
    write_csv(CANDS, CAND_COLS, rows)


def cmd_start(args):
    cid = args[0]
    rows, ledger = read_csv(CANDS, CAND_COLS), read_csv(LEDGER, LEDGER_COLS)
    c = next((r for r in rows if r["id"] == cid), None)
    if not c or c["status"] != "IDEA":
        raise SystemExit(f"{cid}: IDEA 상태의 후보가 아니다 (7점 이상으로 채점된 것만 시작한다)")
    nn = max([num_of(r["post"]) for r in ledger] + [num_of(p) for p in DIR.glob("[0-9][0-9]_*.md")]) + 1
    ledger.append({"post": f"{nn:02d}", "status": "DRAFT", "cluster": c["cluster"], "role": c["role"],
                   "portfolio": "검색", "primary_kw": c["keyword"], "score": c["score"], "approved": "",
                   "logno": "", "published": ""})
    c["status"], c["post"] = "drafted", f"{nn:02d}"
    write_csv(LEDGER, LEDGER_COLS, ledger)
    write_csv(CANDS, CAND_COLS, rows)
    print(f"{cid} → {nn:02d}편 DRAFT. 원고는 content/naver/{nn:02d}_*.md 로 쓴다")


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
    nn, new = int(args[0]), args[1].upper()
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
            raise SystemExit("HUMAN_REVIEW로 올리려면 check_naver가 통과해야 한다:\n  " + "\n  ".join(fails or ["check_naver 확인 필요"]))
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
        r["published"] = datetime.date.today().isoformat()
    write_csv(LEDGER, LEDGER_COLS, rows)
    print(f"{nn:02d}편 → {new}")


def paste_gate(nn: int):
    """naver_paste.page_for가 부른다. 원고가 승인 흐름에 올라와 있지 않으면 붙여넣기 파일을 만들지 않는다."""
    if nn < RULES_FROM:
        return
    r = load_ledger().get(nn)
    if not r:
        raise SystemExit(f"{nn:02d}편이 _pipeline.csv에 없다 — `pipeline.py start`로 시작한 글만 붙여넣기 파일을 만든다")
    if r["status"] not in PASTE_OK:
        raise SystemExit(f"{nn:02d}편 상태가 {r['status']}이다 — HUMAN_REVIEW 이상(check_naver 통과)일 때 만든다")


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


def cmd_sync(_args=None):
    from verify_naver import recent
    rows = read_csv(LEDGER, LEDGER_COLS)
    live = []
    for page in range(1, 6):
        got = recent(30, page)
        live += got
        if len(got) < 30:
            break
    by_title = {p["title"].strip(): p for p in live}
    for r in rows:
        md = post_file(r["post"]).read_text(encoding="utf-8")
        p = by_title.get(title_of(md))
        if p and not r["logno"]:
            r["logno"], r["published"] = p["logNo"], f"{p['when']:%Y-%m-%d}"
    write_csv(LEDGER, LEDGER_COLS, rows)
    print(f"logNo {sum(bool(r['logno']) for r in rows)}/{len(rows)}편 확인")
    for r in rows:      # 발행 뒤 제목을 고친 글(6·14편)은 제목 대조로 못 찾는다 — 조용히 넘기지 않고 알린다
        if not r["logno"]:
            print(f"⚠ {r['post']}편: 라이브 목록에서 제목이 일치하는 글이 없다 — logNo를 손으로 채운다")


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
    d = datetime.date.fromisoformat(published)
    age = (today - d).days      # 발행 직후 값이 아니면 의미가 없으니 점검 기한이 지난 칸은 묻지 않는다
    return [k for k, days in CHECKPOINTS.items() if days <= age <= days + GRACE_DAYS and k not in done]


def cmd_perf(args, today=None):
    today = today or datetime.date.today()
    rows = read_csv(PERF, PERF_COLS)
    if args[:1] == ["add"]:
        nn, cp = int(args[1]), args[2]
        if cp not in CHECKPOINTS:
            raise SystemExit("체크포인트는 24h·7d·30d")
        rec = {c: "" for c in PERF_COLS}
        rec.update(post=f"{nn:02d}", checkpoint=cp, date=today.isoformat())
        for kv in args[3:]:
            k, _, v = kv.partition("=")
            if k not in PERF_COLS:
                raise SystemExit(f"알 수 없는 지표: {k}")
            rec[k] = v
        same = [to_int(r["views"]) for r in rows if r["checkpoint"] == cp and r["views"]]
        rec["grade"] = grade(rec, sum(same) / len(same) if same else 0)
        rows = [r for r in rows if not (r["post"] == rec["post"] and r["checkpoint"] == cp)] + [rec]
        write_csv(PERF, PERF_COLS, rows)
        print(f"{rec['post']}편 {cp} 등급 {rec['grade']}")
        if rec["search_kw"]:
            print(f"검색 유입 키워드 \"{rec['search_kw']}\" → _candidates.csv에 IDEA 후보로 추가, 연관 세부 글 2개를 `score`로 채점한다")
            cands = read_csv(CANDS, CAND_COLS)
            for kw in rec["search_kw"].split("|"):
                if kw.strip() and not any(c["keyword"] == kw.strip() for c in cands):
                    cands.append({**{c: "" for c in CAND_COLS}, "id": f"p{rec['post']}-{len(cands) + 1}",
                                  "keyword": kw.strip(), "intent": f"{rec['post']}편 검색 유입 {cp}"})
            write_csv(CANDS, CAND_COLS, cands)
        if cp == "30d" and rec["grade"] in ("D", "C") and not to_int(rec["search_in"]):
            print("30일간 검색 유입 없음 → 제목·도입·검색 의도 재검토 (삭제하지 않는다, UPDATE_REQUIRED 후보)")
        return
    done = {(r["post"], r["checkpoint"]) for r in rows}
    for r in read_csv(LEDGER, LEDGER_COLS):
        if r["status"] in LIVE and r["published"]:
            d = due_checkpoints(r["published"], {k for p, k in done if p == r["post"]}, today)
            if d:
                print(f"{r['post']}편 {r['primary_kw'][:24]:<24} 발행 {r['published']} — 점검 대상: {', '.join(d)}")


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
    led = [{"post": "12", "cluster": "부양가족", "status": "PUBLISHED"}]
    good = dict(keyword="국민연금 받는 부모님 연말정산 인적공제 가능할까", cluster="부양가족", geo_cited="3",
                serp_fresh="10", official="1", diff="1", season="11|12|1")
    short = dict(keyword="연말정산", cluster="", geo_cited="", serp_fresh="10", official="0", diff="0", season="1")
    s1, p1, d1 = score_one(good, led, {}, today)
    s2, _, d2 = score_one(short, led, {}, today)
    assert s1 >= 7 and d1 == "IDEA", (s1, p1)
    assert d2 in ("HOLD", "REJECTED") and s2 < s1
    _, _, d3 = score_one(good, led, {"12": "국민연금 받는 부모님 연말정산 인적공제 가능할까 부양가족"}, today)
    assert d3 == "UPDATE_EXISTING"

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
    assert due_checkpoints("2026-10-01", set(), datetime.date(2026, 10, 20)) == []

    # 링크 점검 — 목록에 없는 logNo로 가는 링크만 잡는다
    h = '<a href="https://blog.naver.com/education_blog/224000000001">a</a> <a href="https://blog.naver.com/education_blog/224000000009">b</a>'
    assert broken_links({"224000000002": h}, {"224000000001", "224000000002"}) == [("224000000002", "224000000009")]
    assert post_issues(sorted(DIR.glob("[0-9][0-9]_*.md"))[0]) == ([], [])        # 24편 이전 글은 새 규칙 대상이 아니다
    assert paste_gate(24) is None
    print("selftest ok")


COMMANDS = {"score": cmd_score, "start": cmd_start, "status": cmd_status, "list": cmd_list, "links": cmd_links,
            "linkcheck": cmd_linkcheck, "sync": cmd_sync, "perf": cmd_perf}

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif len(sys.argv) > 1 and sys.argv[1] in COMMANDS:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    else:
        print(__doc__)
