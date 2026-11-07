import os

# 1. formatRating in formatters.ts
path = 'src/utils/formatters.ts'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace("if (clean) return `★ ${clean}`;", "if (clean) return clean;")
t = t.replace("return `★ ${rating.toFixed(1)}`;", "return rating.toFixed(1);")
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('formatters.ts updated')

# 2. SearchPage.tsx
path = 'src/features/search/SearchPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace('>✕</button>', '><X size={16} strokeWidth={1.5} /></button>')
t = t.replace('>\n            ✕\n          </button>', '>\n            <X size={16} strokeWidth={1.5} />\n          </button>')
t = t.replace('{query && (\n          <button\n            type="button"\n            className="search-clear-btn"\n            onClick={handleClear}\n            aria-label="Clear search input"\n          >\n            ✕\n          </button>\n        )}', '{query && (\n          <button\n            type="button"\n            className="search-clear-btn"\n            onClick={handleClear}\n            aria-label="Clear search input"\n          >\n            <X size={16} strokeWidth={1.5} />\n          </button>\n        )}')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('SearchPage.tsx updated')

# 3. SeriesDetailPage.tsx
path = 'src/features/series-details/SeriesDetailPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace('☰ Browse Episodes', '<Tv size={15} strokeWidth={1.5} /> <span>Browse Episodes</span>')
t = t.replace('<div className="episode-play-overlay">▶</div>', '<div className="episode-play-overlay"><Play size={16} strokeWidth={1.5} fill="currentColor" /></div>')
with open(path, 'w', encoding='utf-8') as f:
    f.write(t)
print('SeriesDetailPage.tsx updated')

