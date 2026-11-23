import asyncio
import threading
import time
from pathlib import Path
from playwright.async_api import async_playwright
import uvicorn
from backend.main import app
from backend.config import APP_HOST

SCREENSHOTS_DIR = Path("preview_screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def capture_all():
    port = 8003
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to boot
    import urllib.request
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    url = f"http://127.0.0.1:{port}"
    print(f"Server booted on {url}. Launching Playwright...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 920})
        page = await context.new_page()

        await page.goto(url)
        await page.wait_for_selector(".allocation-card", timeout=10000)
        await page.locator(".allocation-card").first.click()
        await page.wait_for_timeout(1000)

        # 1. Dark Mode Workspace
        shot1 = SCREENSHOTS_DIR / "10_vibrant_dark_workspace.png"
        await page.screenshot(path=str(shot1), full_page=False)
        print(f"Captured: {shot1}")

        # 2. Light Mode Workspace
        await page.click("#btn-theme-toggle")
        await page.wait_for_timeout(600)
        shot2 = SCREENSHOTS_DIR / "11_vibrant_light_workspace.png"
        await page.screenshot(path=str(shot2), full_page=False)
        print(f"Captured: {shot2}")

        # Switch back to dark for modal previews
        await page.click("#btn-theme-toggle")
        await page.wait_for_timeout(400)

        # 3. Edit Course Modal
        await page.click("#btn-edit-course")
        await page.wait_for_selector("#edit-course-modal:not(.hidden)", timeout=5000)
        await page.wait_for_timeout(500)
        shot3 = SCREENSHOTS_DIR / "12_edit_course_modal.png"
        await page.screenshot(path=str(shot3), full_page=False)
        print(f"Captured: {shot3}")
        await page.click("#btn-close-edit-course")
        await page.wait_for_timeout(300)

        # 4. Edit Lesson Modal
        await page.click("#btn-edit-active-title")
        await page.wait_for_selector("#edit-lesson-modal:not(.hidden)", timeout=5000)
        await page.wait_for_timeout(500)
        shot4 = SCREENSHOTS_DIR / "13_edit_lesson_modal.png"
        await page.screenshot(path=str(shot4), full_page=False)
        print(f"Captured: {shot4}")
        await page.click("#btn-close-edit-lesson")
        await page.wait_for_timeout(300)

        # 5. Personal Notes Tab
        await page.click("#tab-personal-notes")
        await page.wait_for_timeout(500)
        shot5 = SCREENSHOTS_DIR / "14_personal_notes_toolbar.png"
        await page.screenshot(path=str(shot5), full_page=False)
        print(f"Captured: {shot5}")

        # 6. Curriculum Drawer
        await page.click("#btn-toggle-curriculum")
        await page.wait_for_selector("#curriculum-drawer:not(.hidden)", timeout=5000)
        await page.wait_for_timeout(500)
        shot6 = SCREENSHOTS_DIR / "15_curriculum_drawer_filter.png"
        await page.screenshot(path=str(shot6), full_page=False)
        print(f"Captured: {shot6}")

        await browser.close()
        server.should_exit = True
        print("All preview screenshots captured successfully!")

if __name__ == "__main__":
    asyncio.run(capture_all())
