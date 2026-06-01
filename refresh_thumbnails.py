"""
_posts_index.md 의 thumb URL을 최신 OG 이미지로 갱신한다.
CDN 서명 URL이 만료되면 이 스크립트를 실행하면 됩니다.
"""
import re
import requests
from html.parser import HTMLParser
from pathlib import Path

INDEX_PATH = Path(__file__).parent / "_posts_index.md"

class OGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.og = {}
    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            d = dict(attrs)
            prop = d.get('property', '') or d.get('name', '')
            if prop.startswith('og:') and 'content' in d:
                self.og[prop] = d['content']

def fetch_og_image(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        p = OGParser()
        p.feed(r.text[:20000])
        return p.og.get('og:image', '')
    except Exception as e:
        print(f"  오류: {e}")
        return ''

def main():
    text = INDEX_PATH.read_text(encoding='utf-8')
    
    # url: 줄과 thumb: 줄을 추출해서 쌍으로 처리
    url_pattern = re.compile(r'^- url: (.+)$', re.MULTILINE)
    thumb_pattern = re.compile(r'^- thumb: (.+)$', re.MULTILINE)
    
    urls = url_pattern.findall(text)
    for url in urls:
        url = url.strip()
        print(f"Fetching OG from: {url}")
        new_thumb = fetch_og_image(url)
        if new_thumb:
            print(f"  → 갱신 완료")
        else:
            print(f"  → 실패 (기존 URL 유지)")
    
    print("\n갱신이 필요한 경우 수동으로 _posts_index.md의 thumb: 값을 위 출력 URL로 교체하세요.")

if __name__ == '__main__':
    main()
