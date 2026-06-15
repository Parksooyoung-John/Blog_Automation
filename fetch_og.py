import requests, re

urls = {
    "월배당ETF": "https://j2gblog.tistory.com/entry/월배당-ETF-고를-때-확인할-5가지---분배율만-보면-안-되는-이유",
    "계좌별ETF세금": "https://j2gblog.tistory.com/entry/계좌별-ETF-세금-차이---일반계좌-ISA-연금저축에서-달라지는-것",
    "단일종목레버리지": "https://j2gblog.tistory.com/entry/단일종목-레버리지-ETF-ETN이란----구조와-투자-전-반드시-알아야-할-위험",
    "밸류업ETF": "https://j2gblog.tistory.com/entry/밸류업-ETF에-관심이-높아진-이유---기업가치-제고-정책과-ETF-선택-기준",
}

# 실제 URL (인코딩 포함)
real_urls = {
    "월배당ETF": "https://j2gblog.tistory.com/entry/%EC%9B%94%EB%B0%B0%EB%8B%B9-ETF-%EA%B3%A0%EB%A5%BC-%EB%95%8C-%ED%99%95%EC%9D%B8%ED%95%A0-5%EA%B0%80%EC%A7%80",
    "계좌별ETF세금": "https://j2gblog.tistory.com/entry/%EA%B3%84%EC%A2%8C%EB%B3%84-ETF-%EC%84%B8%EA%B8%88-%EC%B0%A8%EC%9D%B4",
    "단일종목레버리지": "https://j2gblog.tistory.com/entry/%EB%8B%A8%EC%9D%BC%EC%A2%85%EB%AA%A9-%EB%A0%88%EB%B2%84%EB%A6%AC%EC%A7%80-ETF-ETN",
    "밸류업ETF": "https://j2gblog.tistory.com/entry/%EB%B0%B8%EB%A5%98%EC%97%85-ETF",
}

# 직접 접근
direct_urls = {
    "월배당ETF": "https://j2gblog.tistory.com/entry/월배당-ETF-고를-때-확인할-5가지-—-분배율만-보면-안-되는-이유",
    "계좌별ETF세금": "https://j2gblog.tistory.com/entry/계좌별-ETF-세금-차이-—-일반계좌·ISA·연금저축에서-달라지는-것",
    "단일종목레버리지": "https://j2gblog.tistory.com/entry/단일종목-레버리지-ETF·ETN이란?-—-구조와-투자-전-반드시-알아야-할-위험",
    "밸류업ETF": "https://j2gblog.tistory.com/entry/밸류업-ETF에-관심이-높아진-이유-—-기업가치-제고-정책과-ETF-선택-기준",
}

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

for name, url in direct_urls.items():
    try:
        r = requests.get(url, timeout=15, headers=headers)
        print(f"[{name}] status={r.status_code} url={r.url[:80]}")
        m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
        if not m:
            m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
        if m:
            print(f"  OG: {m.group(1)[:120]}")
        else:
            # kakaocdn 직접 탐색
            m2 = re.search(r'(https://img\d+\.daumcdn\.net/thumb/[^\s"\'<>]+)', r.text)
            if m2:
                print(f"  CDN: {m2.group(1)[:120]}")
            else:
                print("  NOT FOUND")
    except Exception as e:
        print(f"[{name}] ERROR: {e}")
