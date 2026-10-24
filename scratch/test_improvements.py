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
    
    # 1. Verify default sort is 'year'
    sort_val = page.eval_on_selector('#sort', 'el => el.value')
    print('Default sort value:', sort_val)
    assert sort_val == 'year', f"Expected 'year', got '{sort_val}'"
    
    # 2. Test navigate to page 3, then click 'MyMovies' title to go Home
    print('Testing Home navigation...')
    page.click('button:has-text("Next ›")')
    time.sleep(1)
    page.click('button:has-text("Next ›")')
    time.sleep(1)
    pager_text = page.eval_on_selector('#pager', 'el => el.textContent')
    print('After clicking Next twice:', pager_text.strip().replace('\n', ' '))
    
    # Click 'MyMovies'
    page.click('h1:has-text("MyMovies")')
    time.sleep(1)
    pager_text_home = page.eval_on_selector('#pager', 'el => el.textContent')
    print('After clicking MyMovies header:', pager_text_home.strip().replace('\n', ' '))
    assert 'Page 1' in pager_text_home, f"Expected Page 1 after clicking MyMovies, got: {pager_text_home}"
    
    # 3. Open movie player (Gold id=4 has verified subs and stream)
    print('Opening movie player...')
    # Open player by calling openPlayer(4)
    page.evaluate('openPlayer(4)')
    page.wait_for_selector('#overlay.on', timeout=8000)
    time.sleep(3)
    
    # Verify Subtitle Track attached
    sub_src = page.eval_on_selector('track#v-sub', 'el => el.src')
    print('Subtitle track attached src:', sub_src)
    assert '/api/subtitles/4' in sub_src, f"Unexpected sub src: {sub_src}"
    cc_btn_text = page.eval_on_selector('#btn-cc', 'el => el.textContent')
    print('CC Button initial state:', cc_btn_text)
    
    # Test toggle CC button
    page.click('#btn-cc')
    time.sleep(0.5)
    cc_btn_off = page.eval_on_selector('#btn-cc', 'el => el.textContent')
    print('CC Button after click:', cc_btn_off)
    assert 'OFF' in cc_btn_off
    page.click('#btn-cc')
    time.sleep(0.5)
    cc_btn_on = page.eval_on_selector('#btn-cc', 'el => el.textContent')
    print('CC Button after 2nd click:', cc_btn_on)
    assert 'ON' in cc_btn_on
    
    # 4. Test Arrow Right skipping with accumulation (+10s, +20s, +30s)
    print('Testing ArrowRight skipping...')
    t0 = page.evaluate('video.currentTime')
    print('Initial currentTime:', t0)
    
    # Click ArrowRight once
    page.keyboard.press('ArrowRight')
    time.sleep(0.1)
    hud1 = page.eval_on_selector('#player-hud', 'el => el.textContent')
    print('HUD after 1st click:', hud1)
    assert '+10s' in hud1, f"Expected +10s in HUD, got {hud1}"
    
    # Click ArrowRight second time rapidly
    page.keyboard.press('ArrowRight')
    time.sleep(0.1)
    hud2 = page.eval_on_selector('#player-hud', 'el => el.textContent')
    print('HUD after 2nd click:', hud2)
    assert '+20s' in hud2, f"Expected +20s in HUD, got {hud2}"
    
    # Click ArrowRight third time rapidly
    page.keyboard.press('ArrowRight')
    time.sleep(0.1)
    hud3 = page.eval_on_selector('#player-hud', 'el => el.textContent')
    print('HUD after 3rd click:', hud3)
    assert '+30s' in hud3, f"Expected +30s in HUD, got {hud3}"
    
    # Wait for accumulator to reset (800ms)
    time.sleep(1.0)
    
    # Test ArrowLeft backward skipping (-10s, -20s)
    print('Testing ArrowLeft skipping...')
    page.keyboard.press('ArrowLeft')
    time.sleep(0.1)
    hud_b1 = page.eval_on_selector('#player-hud', 'el => el.textContent')
    print('HUD after 1st left arrow:', hud_b1)
    assert '-10s' in hud_b1, f"Expected -10s in HUD, got {hud_b1}"
    
    page.keyboard.press('ArrowLeft')
    time.sleep(0.1)
    hud_b2 = page.eval_on_selector('#player-hud', 'el => el.textContent')
    print('HUD after 2nd left arrow:', hud_b2)
    assert '-20s' in hud_b2, f"Expected -20s in HUD, got {hud_b2}"
    
    print('ALL THREE REQUIREMENTS VERIFIED SUCCESSFULLY!')
    browser.close()
