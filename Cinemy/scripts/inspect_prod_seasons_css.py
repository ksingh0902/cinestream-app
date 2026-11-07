with open(r'C:\Users\Singh\Downloads\new-me\server\static\index.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
classes = ['season-tab-btn', 'ep-chip', 'seasons-nav', 'episodes-grid', 'btn-watch-back', 'watch-nav', 'server-switcher']
for cls in classes:
    pos = text.find('.' + cls)
    if pos != -1:
        print(f"--- .{cls} ---")
        print(text[pos:pos+300])

