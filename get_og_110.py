import requests, re

r = requests.get("https://j2gblog.tistory.com/110", timeout=15, headers={"User-Agent": "Mozilla/5.0"})
print(f"Status: {r.status_code}")
m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
if not m:
    m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
if m:
    print(f"OG Image: {m.group(1)}")
else:
    print("OG Image: NOT FOUND")
    print(f"Final URL: {r.url}")
