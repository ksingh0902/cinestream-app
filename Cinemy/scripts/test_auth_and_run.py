import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page()
    page.goto(BASE_URL)
    page.wait_for_selector('input[type="password"]', timeout=5000)
    print("Login form appeared!")

    # Check username input
    user_inputs = page.locator('input[type="text"]')
    if user_inputs.count() > 0:
        user_inputs.first.fill("viewer")
    page.locator('input[type="password"]').fill("loveyoujaan")
    page.click('button[type="submit"]')

    time.sleep(2)
    print("Logged in! URL:", page.url)
    hero_count = page.locator('.hero-fullbleed').count()
    print("Hero count:", hero_count)
    if hero_count > 0:
        print("Hero title:", page.locator('.hero-display-title').inner_text())
    browser.close()

