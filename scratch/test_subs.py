import requests
import re
import urllib.parse

def get_english_subtitle(title, year):
    clean_title = re.sub(r'\(\d{4}\).*', '', title).strip()
    query = f"{clean_title} {year or ''}".strip()
    encoded = urllib.parse.quote(query)
    c_url = f"https://v3-cinemeta.strem.io/catalog/movie/top/search={encoded}.json"
    try:
        r = requests.get(c_url, timeout=6)
        metas = r.json().get('metas', [])
        if not metas:
            return None
        imdb_id = metas[0].get('id')
        print(f"Matched '{title}' -> {imdb_id} ({metas[0].get('name')})")
        
        s_url = f"https://opensubtitles-v3.strem.io/subtitles/movie/{imdb_id}.json"
        s_r = requests.get(s_url, timeout=6)
        subs = s_r.json().get('subtitles', [])
        eng = [s for s in subs if s.get('lang') in ['eng', 'en']]
        if not eng:
            return None
        print(f"Found {len(eng)} English subs, fetching {eng[0]['url'][:60]}...")
        sub_text = requests.get(eng[0]['url'], timeout=6).text
        vtt = 'WEBVTT\n\n' + re.sub(r'(\d\d:\d\d:\d\d),(\d\d\d)', r'\1.\2', sub_text)
        return vtt
    except Exception as e:
        print(f"Error getting sub for {title}: {e}")
        return None

for t, y in [('Gold', 2018), ('Once Upon a Time in Mumbaai', 2010), ('Lost', 2022)]:
    vtt = get_english_subtitle(t, y)
    print(f"{t}: VTT length = {len(vtt) if vtt else 0} bytes")
