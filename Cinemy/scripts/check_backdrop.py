import sqlite3
c = sqlite3.connect(r'C:\Users\Singh\Downloads\new-me\yomovies.db')
cur = c.cursor()
cols = [col[1] for col in cur.execute('PRAGMA table_info(movies)').fetchall()]
print('Columns in movies table:', cols)
sample = cur.execute('SELECT id, title, poster, backdrop FROM movies WHERE backdrop IS NOT NULL AND backdrop != "" LIMIT 5').fetchall()
print('Movies with backdrop:', len(sample))
for row in sample:
    print(row)

count_all = cur.execute('SELECT count(*) FROM movies').fetchone()[0]
count_bd = cur.execute('SELECT count(*) FROM movies WHERE backdrop IS NOT NULL AND backdrop != ""').fetchone()[0]
print(f"Total movies: {count_all}, with backdrop: {count_bd}")

