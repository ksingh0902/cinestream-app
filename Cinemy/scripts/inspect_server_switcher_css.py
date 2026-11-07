with open(r'C:\Users\Singh\Downloads\new-me\server\static\index.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos = text.find('#server-switcher')
if pos != -1:
    print(text[pos:pos+500])

