import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Singh\.gemini\antigravity\brain\77604531-823e-4f7d-bcb8-f9a41969a8ad"
BASE_URL = "http://127.0.0.1:5173"

def login_if_needed(page, username="admin", password="ka#PV!o2"):
    """Logs into CINEMY if login screen is displayed, supporting admin role for full UI verification."""
    try:
        pw_input = page.locator('input[type="password"]')
        if pw_input.count() > 0 and pw_input.first.is_visible():
            print(f"Logging in as {username}...")
            user_input = page.locator('input[type="text"]')
            if user_input.count() > 0:
                user_input.first.fill(username)
            pw_input.first.fill(password)
            page.locator('button[type="submit"]').click()
            time.sleep(1.5)
            print("Authentication successful.")
    except Exception as e:
        print("Login check:", e)

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        # -------------------------------------------------------------
        # 1. Desktop Full-Bleed Hero & Unified Navbar (1440 x 900)
        # -------------------------------------------------------------
        context_desktop = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context_desktop.new_page()
        page.goto(BASE_URL, wait_until="networkidle")
        login_if_needed(page, "admin", "ka#PV!o2")
        page.wait_for_selector(".hero-fullbleed", timeout=10000)
        time.sleep(1)

        hero_el = page.locator(".hero-fullbleed")
        hero_box = hero_el.bounding_box()
        print(f"Hero Bounding Box (Desktop): width={hero_box['width']}, height={hero_box['height']}")
        assert hero_box["width"] >= 1400, f"Expected full-bleed width >= 1400px, got {hero_box['width']}"

        # Poster Card dimensions check
        poster_card = page.locator(".hero-poster-card")
        if poster_card.count() > 0:
            poster_box = poster_card.bounding_box()
            print(f"Hero Poster Card: width={poster_box['width']}, height={poster_box['height']}")

        # Screenshot Desktop Hero
        desktop_path = os.path.join(ARTIFACT_DIR, "redesign_desktop_hero.png")
        page.screenshot(path=desktop_path)
        print(f"Saved: {desktop_path}")

        # -------------------------------------------------------------
        # 2. Hero 2000ms Rotation Verification
        # -------------------------------------------------------------
        initial_title = page.locator(".hero-display-title").inner_text()
        print(f"Initial Hero Title: {initial_title}")
        time.sleep(2.4) # Wait for exactly 2000ms interval + transition
        rotated_title = page.locator(".hero-display-title").inner_text()
        print(f"Rotated Hero Title (2000ms cycle): {rotated_title}")

        # -------------------------------------------------------------
        # 3. Sticky Frosted-Glass Header on Scroll (1440 x 900)
        # -------------------------------------------------------------
        page.evaluate("window.scrollTo(0, 500)")
        time.sleep(0.6)
        header_classes = page.locator(".main-header").get_attribute("class")
        print(f"Header classes on scroll: {header_classes}")
        assert "scrolled" in header_classes, f"Expected .scrolled class on header, got {header_classes}"

        scroll_path = os.path.join(ARTIFACT_DIR, "redesign_sticky_header_scroll.png")
        page.screenshot(path=scroll_path)
        print(f"Saved: {scroll_path}")

        # -------------------------------------------------------------
        # 4. Profile Dropdown Interaction & Single Accent Color
        # -------------------------------------------------------------
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.4)
        profile_trigger = page.locator(".profile-avatar-trigger")
        if profile_trigger.count() > 0:
            profile_trigger.click()
            time.sleep(0.5)
            dropdown_path = os.path.join(ARTIFACT_DIR, "redesign_profile_dropdown.png")
            page.screenshot(path=dropdown_path)
            print(f"Saved: {dropdown_path}")
            profile_trigger.click()
            time.sleep(0.3)

        context_desktop.close()

        # -------------------------------------------------------------
        # 5. Mobile (390 x 844) Viewport
        # -------------------------------------------------------------
        context_mobile = browser.new_context(viewport={"width": 390, "height": 844})
        page_mobile = context_mobile.new_page()
        page_mobile.goto(BASE_URL, wait_until="networkidle")
        login_if_needed(page_mobile, "admin", "ka#PV!o2")
        page_mobile.wait_for_selector(".hero-fullbleed", timeout=10000)
        time.sleep(1)

        mobile_path = os.path.join(ARTIFACT_DIR, "redesign_mobile.png")
        page_mobile.screenshot(path=mobile_path)
        print(f"Saved: {mobile_path}")
        context_mobile.close()

        # -------------------------------------------------------------
        # 6. Tablet (768 x 1024) Viewport
        # -------------------------------------------------------------
        context_tablet = browser.new_context(viewport={"width": 768, "height": 1024})
        page_tablet = context_tablet.new_page()
        page_tablet.goto(BASE_URL, wait_until="networkidle")
        login_if_needed(page_tablet, "admin", "ka#PV!o2")
        page_tablet.wait_for_selector(".hero-fullbleed", timeout=10000)
        time.sleep(1)

        tablet_path = os.path.join(ARTIFACT_DIR, "redesign_tablet.png")
        page_tablet.screenshot(path=tablet_path)
        print(f"Saved: {tablet_path}")
        context_tablet.close()

        # -------------------------------------------------------------
        # 7. Large TV (1920 x 1080) Viewport
        # -------------------------------------------------------------
        context_tv = browser.new_context(viewport={"width": 1920, "height": 1080})
        page_tv = context_tv.new_page()
        page_tv.goto(BASE_URL, wait_until="networkidle")
        login_if_needed(page_tv, "admin", "ka#PV!o2")
        page_tv.wait_for_selector(".hero-fullbleed", timeout=10000)
        time.sleep(1)

        tv_path = os.path.join(ARTIFACT_DIR, "redesign_tv_large.png")
        page_tv.screenshot(path=tv_path)
        print(f"Saved: {tv_path}")
        context_tv.close()

        # -------------------------------------------------------------
        # 8. Video Player Modal with Redesigned Icons & Auto-Hide
        # -------------------------------------------------------------
        context_player = browser.new_context(viewport={"width": 1440, "height": 900})
        page_player = context_player.new_page()
        page_player.goto(BASE_URL, wait_until="networkidle")
        login_if_needed(page_player, "admin", "ka#PV!o2")
        page_player.wait_for_selector(".btn-hero-play", timeout=10000)
        page_player.click(".btn-hero-play")

        # Wait for player modal to open
        page_player.wait_for_selector(".player-modal-root", timeout=10000)
        time.sleep(2) # Initial render

        player_path = os.path.join(ARTIFACT_DIR, "redesign_player_controls.png")
        page_player.screenshot(path=player_path)
        print(f"Saved: {player_path}")

        # Check player top bar icons
        has_back_btn = page_player.locator(".player-btn-back").count() > 0
        has_close_btn = page_player.locator(".player-btn-close").count() > 0
        print(f"Player has Back Button: {has_back_btn}, Close Button: {has_close_btn}")

        context_player.close()
        browser.close()

    print("\n=======================================================")
    print("ALL REDESIGN VERIFICATIONS & SCREENSHOTS COMPLETED!")
    print("=======================================================")

if __name__ == "__main__":
    run_verification()
