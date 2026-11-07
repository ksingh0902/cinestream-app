with open(r'C:\Users\Singh\Downloads\new-me\server\static\index.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos = text.find('.player-container {')
if pos != -1:
    print("--- .player-container CSS ---")
    print(text[pos:pos+1500])

pos_box = text.find('#overlay .box {')
if pos_box != -1:
    print("--- #overlay .box CSS ---")
    print(text[pos_box:pos_box+800])

