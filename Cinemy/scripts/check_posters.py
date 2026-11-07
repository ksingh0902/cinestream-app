import sqlite3
c = sqlite3.connect(r'C:\Users\Singh\Downloads\new-me\yomovies.db')
cur = c.cursor()
rows = cur.execute('SELECT id, title, poster, poster_url, tmdb_id FROM movies LIMIT 15').fetchall()
for r in rows:
    print(r)

