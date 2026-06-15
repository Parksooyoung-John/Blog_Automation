"""발행된 포스트 63, 64의 내부 링크 카드 img src 현황 확인"""
import requests, re, urllib.parse

HEADERS = {"User-Agent": "Mozilla/5.0"}

# 알려진 정상 썸네일 fname 키
KNOWN_THUMBS = {
    "r8r7D": "월배당ETF /59",
    "0F5CX": "계좌별ETF세금 /60",
    "EzdyU": "ISA /14 (국민성장ISA도 이 키)",
    "cvSXo6": "단일종목레버리지ETF /63",
    "L0Qse": "밸류업ETF /64",
    "bF0dDG": "사회초년생ISA연금IRP /43",
    "db5W7W": "연금저축vsIRP /15",
}

def extract_fname(src):
    """daumcdn URL에서 fname= 파라미터 추출"""
    try:
        decoded = urllib.parse.unquote(src)
        m = re.search(r'/dna/([^/]+)/', decoded)
        if m:
            return m.group(1)
    except:
        pass
    return "unknown"

def check_post(post_id):
    url = f"https://j2gblog.tistory.com/{post_id}"
    r = requests.get(url, timeout=10, headers=HEADERS)
    html = r.text

    section_m = re.search(r'함께 읽으면 좋은 글([\s\S]{0,4000})', html)
    if not section_m:
        print(f"[/{post_id}] '함께 읽으면 좋은 글' 섹션 없음")
        return

    section = section_m.group(1)
    imgs = re.findall(r'src="(https://img1\.daumcdn[^"]+)"', section)
    hrefs = re.findall(r'href="(https://j2gblog\.tistory\.com[^"]+)"', section)

    print(f"\n[/{post_id}]")
    for i, (href, src) in enumerate(zip(hrefs, imgs)):
        fname = extract_fname(src)
        label = KNOWN_THUMBS.get(fname, f"알 수 없음 ({fname})")
        slug = href.split("/entry/")[-1][:40] if "/entry/" in href else href
        print(f"  카드 {i+1}: {slug}")
        print(f"    thumb fname: {fname} → {label}")
        ok = "✅" if fname not in ["EzdyU"] else "❌ ISA 이미지 오사용"
        print(f"    상태: {ok}")
        print()

check_post(63)
check_post(64)
