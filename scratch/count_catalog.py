import re

with open('js/data.js', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'"title":\s*"([^"]+)"', text)
print('Titles in js/data.js:', len(matches))
