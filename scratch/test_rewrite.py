import httpx, re
from urllib.parse import quote, urljoin

def rewrite(text, base):
    def absu(x): return urljoin(base, x)
    if '#EXT-X-STREAM-INF' in text or '#EXT-X-MEDIA:' in text:
        out = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith('#'):
                out.append('/proxy/hls?u=' + quote(absu(s), safe=''))
            elif s.startswith('#EXT-X-MEDIA:') and 'URI=' in s:
                out.append(re.sub(r'URI="([^"]+)"',
                                  lambda m: f'URI="/proxy/hls?u={quote(absu(m.group(1)), safe="")}"', s))
            else:
                out.append(line)
    else:
        out = []
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith('#'):
                out.append('/proxy/seg?u=' + quote(absu(s), safe=''))
            elif s.startswith('#EXT-X-KEY') and 'URI=' in s:
                out.append(re.sub(r'URI="([^"]+)"',
                                  lambda m: f'URI="/proxy/seg?u={quote(absu(m.group(1)), safe="")}"', s))
            else:
                out.append(line)
    return '\n'.join(out)

client = httpx.Client(timeout=30)
master_text = client.get('https://park.ydc1wes.me/hls2/02/00011/hne9gajxbah0_,l,h,.urlset/master.m3u8?t=2PYK_KgeJ-w5IqnY328v8N-5GzuKrI-A2IGsFYQ6DXo&s=1792803876&e=21600&f=56335&i=0.0&sp=0').text
child_text = client.get('https://park.ydc1wes.me/hls2/02/00011/hne9gajxbah0_l/index-v1-a1.m3u8?t=2PYK_KgeJ-w5IqnY328v8N-5GzuKrI-A2IGsFYQ6DXo&s=1792803876&e=21600&f=56335&i=0.0&sp=0').text

rw_master = rewrite(master_text, 'https://park.ydc1wes.me/')
rw_child = rewrite(child_text, 'https://park.ydc1wes.me/hls2/02/00011/hne9gajxbah0_l/')

print('Master non-comments all /proxy/hls?', all(l.startswith('/proxy/hls') for l in rw_master.splitlines() if l and not l.startswith('#')))
print('Child non-comments all /proxy/seg?', all(l.startswith('/proxy/seg') for l in rw_child.splitlines() if l and not l.startswith('#')))
key_lines = [l for l in rw_child.splitlines() if '#EXT-X-KEY' in l]
print('Child KEY rewritten to /proxy/seg?', '/proxy/seg?u=' in key_lines[0] if key_lines else False)
