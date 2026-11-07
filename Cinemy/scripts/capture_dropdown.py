import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Singh\.gemini\antigravity\brain\77604531-823e-4f7d-bcb8-f9a41969a8ad"
BASE_URL = "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(BASE_URL, wait_until="networkidle")
    
    # Login as admin
    pw = page.locator('input[type="password"]')
    if pw.count() > 0 and pw.first.is_visible():
        page.locator('input[type="text"]').first.fill("admin")
        pw.first.fill("ka#PV!o2")
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

    # Click avatar
    page.wait_for_selector(".header-avatar-btn", timeout=10000)
    page.click(".header-avatar-btn")
    time.sleep(0.5)

    dropdown_path = os.path.join(ARTIFACT_DIR, "redesign_profile_dropdown.png")
    page.screenshot(path=dropdown_path)
    print(f"Saved: {dropdown_path}")
    browser.close()
