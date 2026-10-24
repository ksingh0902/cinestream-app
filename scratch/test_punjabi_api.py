import requests

res = requests.get('http://127.0.0.1:8000/api/movies?genre=Punjabi&per_page=6').json()
print("Total Punjabi movies found:", res['total'])
print("First 6 Punjabi titles:")
for item in res['items']:
    print(f"- {item['title']} ({item['year']}) [{item['quality']}]")
