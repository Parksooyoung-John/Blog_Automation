import requests, re
headers = {"User-Agent": "Mozilla/5.0"}
posts = {
    "단일종목레버리지": "https://j2gblog.tistory.com/63",
    "밸류업ETF": "https://j2gblog.tistory.com/64",
}
for name, url in posts.items():
    r = requests.get(url, timeout=10, headers=headers)
    m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
    if not m:
        m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
    print(name + ": " + (m.group(1) if m else "NOT FOUND"))
