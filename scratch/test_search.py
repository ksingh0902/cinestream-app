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

    # 1. Check placeholder
    ph = page.eval_on_selector('#q', 'el => el.placeholder')
    print('Placeholder:', ph)
    assert '10,000+' in ph, f'Expected 10,000+ in placeholder, got {ph}'

    # 2. Type 'gold' into search bar
    print('Typing into search bar...')
    page.fill('#q', 'gold')
    page.wait_for_selector('#search-dropdown.open', timeout=5000)
    time.sleep(1)

    items = page.eval_on_selector_all(
        '.s-item',
        'els => els.map(e => e.querySelector(".s-title").textContent)'
    )
    print('Search dropdown items rendered:', items)
    assert len(items) > 0, 'No items rendered in search dropdown'
    assert any('Gold' in it for it in items), f'Gold not in items: {items}'

    footer_text = page.eval_on_selector('.s-footer', 'el => el.textContent')
    print('Search footer action:', footer_text.strip())
    assert 'matching titles' in footer_text

    # 3. Test keyboard navigation in search bar
    page.keyboard.press('ArrowDown')
    time.sleep(0.3)
    active_idx = page.eval_on_selector(
        '.s-item.active',
        'el => el.getAttribute("data-idx")'
    )
    print('Active item after ArrowDown:', active_idx)
    assert active_idx == '0', f'Expected active idx 0, got {active_idx}'

    # 4. Test clicking clear button
    print('Testing clear button...')
    page.click('#q-clear')
    time.sleep(0.5)
    q_val = page.eval_on_selector('#q', 'el => el.value')
    is_open = page.eval_on_selector(
        '#search-dropdown',
        'el => el.classList.contains("open")'
    )
    print('Value after clear:', repr(q_val), 'Dropdown is open:', is_open)
    assert q_val == ''
    assert not is_open

    # 5. Test search select opens movie
    print('Testing direct item click from search dropdown...')
    page.fill('#q', 'gold')
    page.wait_for_selector('#search-dropdown.open', timeout=5000)
    time.sleep(0.5)
    page.click('.s-item:first-child')
    page.wait_for_selector('#overlay.on', timeout=5000)
    p_title = page.eval_on_selector('#p-title', 'el => el.textContent')
    print('Overlay title after selecting search item:', p_title)
    assert 'Gold' in p_title

    print('SEARCH BAR RENDERING VERIFIED 100% SUCCESSFULLY!')
    browser.close()
