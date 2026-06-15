import requests, re

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 단일종목 레버리지 ETF - 물음표/특수문자 제거 버전 시도
test_urls = [
    "https://j2gblog.tistory.com/entry/단일종목-레버리지-ETFETNi란",
    "https://j2gblog.tistory.com/entry/단일종목-레버리지-ETF-ETN이란",
    "https://j2gblog.tistory.com/entry/단일종목-레버리지-ETF-ETN이란-구조와-투자-전-반드시-알아야-할-위험",
]

for url in test_urls:
    r = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
    print(f"status={r.status_code} final={r.url[:100]}")
    if r.status_code == 200:
        m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
        if not m:
            m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
        if m:
            print(f"  OG: {m.group(1)[:150]}")
        break

# 전체 OG URL 출력
print("\n=== 확보된 썸네일 ===")
confirmed = {
    "월배당ETF_url": "https://j2gblog.tistory.com/entry/월배당-ETF-고를-때-확인할-5가지-—-분배율만-보면-안-되는-이유",
    "계좌별ETF세금_url": "https://j2gblog.tistory.com/entry/계좌별-ETF-세금-차이-—-일반계좌·ISA·연금저축에서-달라지는-것",
    "밸류업ETF_url": "https://j2gblog.tistory.com/entry/밸류업-ETF에-관심이-높아진-이유-—-기업가치-제고-정책과-ETF-선택-기준",
}
for name, url in confirmed.items():
    r = requests.get(url, timeout=10, headers=headers)
    m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
    if not m:
        m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
    if m:
        print(f"{name}:\n  {m.group(1)}\n")
