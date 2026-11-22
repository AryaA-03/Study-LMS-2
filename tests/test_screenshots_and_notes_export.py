"""Verification test for Screenshot-to-Notes and Notes PDF/MD Export features."""

from playwright.sync_api import sync_playwright
import pytest
import time

def test_screenshot_to_notes_and_notes_export():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector(".day-group-card", timeout=15000)
        page.wait_for_selector("#notes-content h1, #notes-content h2, #notes-content p", timeout=15000)

        # 1. Verify Grounded Notes Action Toolbar is visible
        page.wait_for_selector("#grounded-notes-toolbar", timeout=5000)
        assert page.is_visible("#btn-print-grounded-notes")
        assert page.is_visible("#btn-download-grounded-notes")
        assert page.is_visible("#btn-copy-to-personal-notes")

        # 2. Test "Copy to My Notes" button
        page.click("#btn-copy-to-personal-notes")
        # Should switch tab to Personal Notes
        page.wait_for_selector("#pane-personal-notes:not(.hidden)", timeout=5000)
        page.wait_for_function("() => document.getElementById('input-personal-notes').value.length > 0")
        personal_text = page.input_value("#input-personal-notes")
        assert len(personal_text) > 0, "Personal notes textarea should have content copied"

        # 3. Test "Snap to Notes" button from Action Strip
        page.click("#btn-snap-current-to-notes")
        page.wait_for_selector("#pane-personal-notes:not(.hidden)", timeout=5000)
        page.wait_for_function("() => document.getElementById('input-personal-notes').value.includes('### 📸 Frame')")
        updated_text = page.input_value("#input-personal-notes")
        assert "### 📸 Frame" in updated_text, "Personal notes should contain frame heading"
        assert "Note:" in updated_text, "Personal notes should contain Note prompt"

        # 4. Test "📸 Snap Frame" button from Personal Notes toolbar
        page.click("#btn-toolbar-snap-frame")
        time.sleep(0.3)
        updated_text2 = page.input_value("#input-personal-notes")
        assert updated_text2.count("### 📸 Frame") >= 2, "Second frame should be appended"

        # 5. Test Print Grounded Notes setup (verifies print container renders properly)
        print_container_html = page.evaluate("""() => {
            window.printGroundedNotes();
            const container = document.getElementById('grounded-notes-print-container');
            return container ? container.innerHTML : '';
        }""")
        assert "Grounded Lecture Notes" in print_container_html
        assert "print-notes-body" in print_container_html

        # 6. Test Download Grounded Notes Markdown
        # Check download event
        with page.expect_download() as download_info:
            page.click("#btn-download-grounded-notes")
        download = download_info.value
        assert download.suggested_filename.endswith(".md")

        print("SCREENSHOTS TO NOTES & NOTES EXPORT VERIFIED SUCCESSFULLY!")
        print("Console errors:", console_errors)
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"
        browser.close()

if __name__ == "__main__":
    test_screenshot_to_notes_and_notes_export()
