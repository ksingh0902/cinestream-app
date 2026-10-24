import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        headless=False,
        args=['--window-position=-2400,-2400', '--window-size=1280,800']
    )
    page = browser.new_page()
    page.goto('http://localhost:8000', timeout=15000)
    page.wait_for_selector('.card', timeout=10000)
    cards = page.query_selector_all('.card')
    print(f'Rendered cards count: {len(cards)}')
    
    # Click the first card
    cards[1].click()
    page.wait_for_selector('#overlay.on', timeout=5000)
    print('Overlay opened!')
    
    # Check video playback
    t_start = time.time()
    played_past_30 = False
    for sec in range(60):
        time.sleep(1)
        cur_time = page.evaluate('document.getElementById("v").currentTime')
        paused = page.evaluate('document.getElementById("v").paused')
        status = page.evaluate('document.getElementById("p-status").textContent')
        ready_state = page.evaluate('document.getElementById("v").readyState')
        print(f'[{sec}s] Video currentTime: {cur_time:.2f}s | Paused: {paused} | ReadyState: {ready_state} | Status: {status}')
        if cur_time >= 30.0:
            played_past_30 = True
            print('SUCCESS: Video played past 30 seconds!')
            break
            
    browser.close()
    if not played_past_30:
        sys.exit(1)
