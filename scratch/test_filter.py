import sqlite3

con = sqlite3.connect("yomovies.db")
c = con.cursor()

exclude_clauses = [
    "quality = '18+'",
    "quality LIKE '%18+%'",
    "genres LIKE '%\"Erotic Movies\"%'",
    "title LIKE '%(Ullu%'",
    "title LIKE '%(PrimeShots%'",
    "title LIKE '%(Hunters Original%'",
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
    "title LIKE '%(Atrangii Original%'",
]

where_exclude = " AND NOT (" + " OR ".join(exclude_clauses) + ")"

total = c.execute("SELECT count(*) FROM movies").fetchone()[0]
clean_total = c.execute(f"SELECT count(*) FROM movies WHERE title IS NOT NULL AND title != '' {where_exclude}").fetchone()[0]
print(f"Total: {total}, Clean: {clean_total}, Excluded: {total - clean_total}")

# Verify none of the excluded titles show up in top 20
print("\nTop 20 newly added / latest release clean movies:")
query = f"""SELECT id, title, year, quality, genres 
            FROM movies 
            WHERE title IS NOT NULL AND title != '' {where_exclude}
            ORDER BY CAST(year AS INT) DESC, id ASC 
            LIMIT 20"""
rows = c.execute(query).fetchall()
for r in rows:
    print(r)
