import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("preview_screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def run_live_verification():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("Navigating to http://127.0.0.1:8000 ...")
        await page.goto("http://127.0.0.1:8000", wait_until="networkidle")

        # Wait for courses to populate
        await page.wait_for_selector("#course-selector option:not([value=''])", state="attached", timeout=10000)
        options = await page.locator("#course-selector option").all_text_contents()
        print(f"Courses loaded in dropdown: {options}")

        # 1. Capture Workspace for Course 1 (TOC or DBMS)
        await page.wait_for_selector(".allocation-card", timeout=10000)
        await page.locator(".allocation-card").first.click()
        await page.wait_for_timeout(1500)
        
        shot1 = SCREENSHOTS_DIR / "01_workspace_course1.png"
        await page.screenshot(path=str(shot1), full_page=False)
        print(f"Captured: {shot1}")

        # 2. Switch to the other course in dropdown
        other_option_val = await page.evaluate("""() => {
            const sel = document.getElementById('course-selector');
            for (let i = 0; i < sel.options.length; i++) {
                if (sel.options[i].value !== sel.value) return sel.options[i].value;
            }
            return sel.value;
        }""")
        
        await page.select_option("#course-selector", value=other_option_val)
        await page.wait_for_timeout(2000)
        await page.wait_for_selector(".allocation-card", timeout=10000)
        await page.locator(".allocation-card").first.click()
        await page.wait_for_timeout(1500)

        shot2 = SCREENSHOTS_DIR / "02_workspace_course2.png"
        await page.screenshot(path=str(shot2), full_page=False)
        print(f"Captured: {shot2}")

        # 3. Test Creator / Onboarding View UI
        await page.click("#btn-new-course")
        await page.wait_for_selector("#creator-view:not(.hidden)", timeout=5000)
        await page.wait_for_timeout(1000)

        shot3 = SCREENSHOTS_DIR / "03_redesigned_onboarding_creator.png"
        await page.screenshot(path=str(shot3), full_page=False)
        print(f"Captured: {shot3}")

        # 4. Test clicking the DBMS preset card in the onboarding view
        await page.click("#card-preset-dbms")
        await page.wait_for_timeout(1500)

        shot4 = SCREENSHOTS_DIR / "04_preset_selected_workspace.png"
        await page.screenshot(path=str(shot4), full_page=False)
        print(f"Captured: {shot4}")

        await browser.close()
        print("\nAll live previews captured successfully!")

if __name__ == "__main__":
    asyncio.run(run_live_verification())
