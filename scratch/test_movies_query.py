import sqlite3

con = sqlite3.connect("yomovies.db")
c = con.cursor()

exclude = [
    "quality = '18+'",
    "quality LIKE '%18+%'",
    "genres LIKE '%\"Erotic Movies\"%'",
    "title LIKE '%(Ullu%'",
    "title LIKE '%(PrimeShots%'",
    "title LIKE '%(Hunters%'",
    "title LIKE '%(WOOW%'",
    "title LIKE '%(HuntCinema%'",
    "title LIKE '%(Mastiplay%'",
    "title LIKE '%(BulbulPlay%'",
    "title LIKE '%(Besharams%'",
    "title LIKE '%(Kaddu%'",
    "title LIKE '%(DesiPrime%'",
    "title LIKE '%(Hotshots%'",
    "title LIKE '%(MoodX%'",
    "title LIKE '%(Voovi%'",
    "title LIKE '%(Chikooflix%'",
    "title LIKE '%(Bigshots%'",
    "title LIKE '%(Atrangii%'",
]
sql_ex = " AND NOT (" + " OR ".join(exclude) + ")"

q = f"""SELECT id, title, year, quality, is_series 
        FROM movies 
        WHERE is_series = 0 AND title IS NOT NULL AND title != '' {sql_ex} 
        ORDER BY CAST(year AS INT) DESC, id ASC 
        LIMIT 20"""

print("=== Clean Movies Only (is_series=0, Year DESC, newly added) ===")
for r in c.execute(q):
    print(r)
