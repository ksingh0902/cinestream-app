with open(r'C:\Users\Singh\Downloads\new-me\server\static\index.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos = text.find('id="overlay"')
print("overlay pos:", pos)
if pos != -1:
    print(text[pos-40:pos+2000])

print("\n--- STYLES FOR OVERLAY ---")
style_pos = text.find('#overlay {')
if style_pos != -1:
    print(text[style_pos:style_pos+1500])
