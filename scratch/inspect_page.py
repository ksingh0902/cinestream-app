import requests
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

r = requests.get('https://yomoviesnow.com/16868-jailer.html', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'lxml')
p = soup.select_one('#player')
if p:
    print('Player HTML:', str(p)[:2000])

for s in soup.select('script'):
    if 'embed' in s.text or 'speedostream' in s.text or 'player' in s.text or 'm3u8' in s.text:
        print('Script match:', s.text[:500])
