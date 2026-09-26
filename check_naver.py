import re, glob, os

def parts(p):
    n = open(p, encoding='utf-8').read()
    b = n.split('## 작성 메모')[0]
    tags = re.findall(r'#[가-힣A-Za-z0-9]+', b)
    b2 = re.sub(r'^제목:.*$', '', b, flags=re.M)
    b2 = re.sub(r'^#[가-힣A-Za-z0-9]+.*$', '', b2, flags=re.M)
    c = re.sub(r'\[(이미지|경험 한 줄|내부 링크)[^\]]*\]', '', b2)
    c = re.sub(r'^-{3,}$', '', c, flags=re.M)
    return n, b2, c, tags

def sents(x):
    x = re.sub(r'[#*>|\-]', '', x)
    return {s.strip() for s in re.split(r'[.!?]\s|\n', x) if len(s.strip()) >= 12}

tis = ''
for f in glob.glob('_workspace/02_blog_post_*.md'):
    tis += open(f, encoding='utf-8').read()
T = sents(tis)

allok = True
for p in sorted(glob.glob('content/naver/*.md')):
    n, b, c, tags = parts(p)
    m = re.search(r'^제목: (.+)$', n, flags=re.M)
    if not m:
        continue
    title = m.group(1)
    ln = len(c.strip())
    h = len(re.findall(r'^## ', b, flags=re.M))
    img = len(re.findall(r'\[이미지', b))
    exp = len(re.findall(r'\[경험 한 줄', b))
    link = len(re.findall(r'\[내부 링크', b))
    dup = sents(c) & T
    ok = (800 <= ln <= 1600 and 3 <= h <= 5 and img >= 2 and exp >= 1
          and link >= 1 and 8 <= len(tags) <= 12 and not dup)
    allok &= ok
    print(('OK   ' if ok else 'CHECK'), os.path.basename(p))
    print(f'       {ln}자 / 소제목 {h} / 이미지 {img} / 경험 {exp} / 내부링크 {link}'
          f' / 태그 {len(tags)} / 티스토리 중복 {len(dup)}')
    print(f'       제목: {title}')
    for d in list(dup)[:3]:
        print('         중복:', d[:55])
print('\n전체 통과' if allok else '\n확인 필요')
