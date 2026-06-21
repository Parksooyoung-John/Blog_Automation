import requests, re

url = "https://j2gblog.tistory.com/89"
r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
print(f"Status: {r.status_code}")

if r.status_code == 200:
    # Check if SpaceX post
    if "스페이스X" in r.text or "SPCX" in r.text:
        print("✅ This is the SpaceX post!")
        # Extract OG image
        m = re.search(r'property="og:image"\s+content="([^"]+)"', r.text)
        if not m:
            m = re.search(r'content="([^"]+)"\s+property="og:image"', r.text)
        if m:
            og_url = m.group(1)
            print(f"OG Image URL: {og_url}")
        else:
            print("OG Image: NOT FOUND (may still be processing)")
    else:
        print("This is NOT the SpaceX post")
elif r.status_code == 404:
    print("Post not found (404)")
