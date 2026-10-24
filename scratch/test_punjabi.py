import sqlite3

con = sqlite3.connect("yomovies.db")
c = con.cursor()

g_cnt = c.execute('SELECT count(*) FROM movies WHERE genres LIKE \'%"Punjabi"%\'').fetchone()[0]
q_cnt = c.execute("SELECT count(*) FROM movies WHERE quality = 'Punjabi'").fetchone()[0]
t_cnt = c.execute("SELECT count(*) FROM movies WHERE title LIKE '%Punjabi%'").fetchone()[0]
comb_cnt = c.execute('SELECT count(*) FROM movies WHERE genres LIKE \'%"Punjabi"%\' OR quality = \'Punjabi\' OR title LIKE \'%Punjabi%\'').fetchone()[0]

print(f"Genres: {g_cnt}, Quality: {q_cnt}, Title: {t_cnt}, Combined: {comb_cnt}")

rows = c.execute('SELECT id, title, year, quality, genres FROM movies WHERE genres LIKE \'%"Punjabi"%\' OR quality = \'Punjabi\' OR title LIKE \'%Punjabi%\' ORDER BY CAST(year AS INT) DESC LIMIT 5').fetchall()
for r in rows:
    print(r)
