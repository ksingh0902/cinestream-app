import requests

r = requests.get('http://127.0.0.1:8000/api/movies?page=1&per_page=10').json()
print('Total clean titles:', r['total'])
print('\nTop 10 Default (Newly added by time):')
for it in r['items']:
    print(f"{it['id']}: {it['title']} ({it['year']}) [{it['quality']}] - series={it['is_series']}")

# Test search for adult series
s = requests.get('http://127.0.0.1:8000/api/search?q=Bad%20Boyy').json()
print('\nSearch for "Bad Boyy" (should be empty):', s['items'])

# Test search for Gold (should NOT have Gold Digger BulbulPlay)
s2 = requests.get('http://127.0.0.1:8000/api/search?q=Gold').json()
print('\nSearch for "Gold":', [it['title'] for it in s2['items'][:5]])

# Test Movies only filter
m = requests.get('http://127.0.0.1:8000/api/movies?series=0&page=1&per_page=5').json()
print('\nMovies only (series=0):', [(it['title'], it['is_series']) for it in m['items']])
