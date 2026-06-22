import requests, re

# Try numeric URL first
for url in [
    "https://j2gblog.tistory.com/107",
    "https://j2gblog.tistory.com/entry/%ED%87%B4%EC%A7%81%EC%97%B0%EA%B8%88-%EB%94%94%ED%8F%B4%ED%8A%B8%EC%98%B5%EC%85%98-%EC%88%98%EC%9D%B5%EB%A5%A0,-%EA%B7%B8%EB%83%A5-%EC%95%88%EC%A0%95%ED%98%95%EC%97%90-%EB%91%90%EB%A9%B4-%EA%B4%9C%EC%B0%AE%EC%9D%84%EA%B9%8C",
]:
    r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
    print(f"URL: {url[:60]}...")
    print(f"Status: {r.status_code}, Final URL: {r.url}")
    if r.status_code == 200:
        m2 = re.search(r"property=[\"']og:image[\"']\s+content=[\"']([^\"']+)[\"']", r.text)
        if not m2:
            m2 = re.search(r"content=[\"']([^\"']+)[\"']\s+property=[\"']og:image[\"']", r.text)
        if m2:
            print(f"OG Image: {m2.group(1)}")
        else:
            print("OG Image: NOT FOUND")
    print()
