with open(r'C:\Users\Singh\Downloads\new-me\server\static\index.html', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()
print('\n'.join(lines[4950:5100]))

