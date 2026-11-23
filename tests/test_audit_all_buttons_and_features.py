import pytest
pytestmark = pytest.mark.e2e
"""Comprehensive UI Feature & Button Audit Test.

Iterates through every interactive button, modal, drawer, tab, and slider control
in the application to verify that:
1. Every feature is accessible and functioning.
2. No button was removed or left disconnected.
3. Modals and drawers open and close seamlessly.
4. Zero JavaScript console errors occur during any interaction.
"""

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
import pytest
import time

def test_audit_all_ui_buttons_and_features():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        
        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector(".day-group-card", timeout=15000)
        
        # --- 1. Top Bar Controls ---
        # A. Theme Toggle
        page.click("#btn-theme-toggle")
        time.sleep(0.1)
        page.click("#btn-theme-toggle")
        time.sleep(0.1)
        
        # B. Right Studio Toggle
        page.click("#btn-toggle-studio")
        time.sleep(0.1)
        page.click("#btn-toggle-studio")
        time.sleep(0.1)
        
        # C. Cram Sheet Modal
        page.click("#btn-open-cram-sheet")
        page.wait_for_selector("#modal-cram-sheet:not(.hidden)", timeout=5000)
        page.click("#btn-close-cram-sheet")
        page.wait_for_selector("#modal-cram-sheet", state="hidden", timeout=5000)
        
        # D. Mock Exam Modal
        page.click("#btn-mock-exam")
        page.wait_for_selector("#mock-exam-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-mock-exam")
        page.wait_for_selector("#mock-exam-modal", state="hidden", timeout=5000)
        
        # E. Settings Modal & Inside Shortcuts
        page.click("#btn-settings")
        page.wait_for_selector("#settings-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-settings")
        page.wait_for_selector("#settings-modal", state="hidden", timeout=5000)
        
        # F. Creator View (New Goal)
        page.click("#btn-new-course")
        page.wait_for_selector("#creator-view:not(.hidden)", timeout=5000)
        page.click("#btn-cancel-creator")
        page.wait_for_selector("#workspace-view:not(.hidden)", timeout=5000)
        
        # --- 2. Left Syllabus Rail & Modals ---
        # A. Collapse / Expand Sidebar
        page.click("#btn-collapse-schedule")
        page.wait_for_selector("#pane-schedule.rail-collapsed", timeout=5000)
        page.click("#btn-expand-rail-top")
        page.wait_for_selector("#pane-schedule:not(.rail-collapsed)", timeout=5000)
        
        # B. Collapse Days
        page.click("#btn-toggle-collapse-all")
        time.sleep(0.1)
        page.click("#btn-toggle-collapse-all")
        time.sleep(0.1)
        
        # C. Pacing Strategy Pills
        page.click("#pill-strategy-fixed")
        time.sleep(0.1)
        page.click("#pill-strategy-paced")
        time.sleep(0.1)
        
        # D. Revision Buffer Pills
        page.click("#pill-buffer-zero")
        time.sleep(0.1)
        page.click("#pill-buffer-two")
        time.sleep(0.1)
        
        # E. Filter Buttons
        page.click("#btn-filter-concepts")
        time.sleep(0.1)
        page.click("#btn-filter-examples")
        time.sleep(0.1)
        page.click("#btn-filter-pyq")
        time.sleep(0.1)
        page.click("#btn-filter-all")
        time.sleep(0.1)
        
        # F. Edit Course Modal
        page.click("#btn-edit-course")
        page.wait_for_selector("#edit-course-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-edit-course")
        page.wait_for_selector("#edit-course-modal", state="hidden", timeout=5000)
        
        # G. Curriculum Drawer
        page.click("#btn-toggle-curriculum")
        page.wait_for_selector("#curriculum-drawer:not(.hidden)", timeout=5000)
        page.click("#btn-close-curriculum")
        page.wait_for_selector("#curriculum-drawer", state="hidden", timeout=5000)
        
        # H. Diagnostic Pre-Test Modal
        page.click("#btn-diagnostic-test")
        page.wait_for_selector("#diagnostic-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-diagnostic")
        page.wait_for_selector("#diagnostic-modal", state="hidden", timeout=5000)
        
        # I. Add Source Modal
        page.click("#btn-open-add-source")
        page.wait_for_selector("#add-source-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-add-source")
        page.wait_for_selector("#add-source-modal", state="hidden", timeout=5000)
        
        # --- 3. Center Study Canvas & Player Splitter ---
        # A. Quick Snap Buttons
        page.click("#snap-compact-video")
        time.sleep(0.1)
        page.click("#snap-balanced-video")
        time.sleep(0.1)
        page.click("#btn-collapse-player")
        time.sleep(0.1)
        page.click("#btn-collapse-player")
        time.sleep(0.1)
        
        # B. Lesson Action Buttons
        page.click("#btn-toggle-auto-advance")
        time.sleep(0.1)
        page.click("#btn-toggle-auto-advance")
        time.sleep(0.1)
        
        # Edit Active Lesson Modal
        page.click("#btn-edit-active-lesson")
        page.wait_for_selector("#edit-lesson-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-edit-lesson")
        page.wait_for_selector("#edit-lesson-modal", state="hidden", timeout=5000)
        
        # --- 4. Right Studio Panel Tabs ---
        # A. Quiz Tab
        page.click("#tab-quiz-mastery")
        page.wait_for_selector("#pane-quiz-mastery:not(.hidden)", timeout=5000)
        
        # B. Flashcards Tab & Add Card Modal
        page.click("#tab-flashcards-fsrs")
        page.wait_for_selector("#pane-flashcards-fsrs:not(.hidden)", timeout=5000)
        page.click("#btn-add-card-manual")
        page.wait_for_selector("#add-card-modal:not(.hidden)", timeout=5000)
        page.click("#btn-close-add-card")
        page.wait_for_selector("#add-card-modal", state="hidden", timeout=5000)
        
        # C. Q&A Tab
        page.click("#tab-qa-notebook")
        page.wait_for_selector("#pane-qa-notebook:not(.hidden)", timeout=5000)
        
        # D. Code Tab
        page.click("#tab-pyodide-scratchpad")
        page.wait_for_selector("#pane-pyodide-scratchpad:not(.hidden)", timeout=5000)
        
        # E. PYQ Tab
        page.click("#tab-pyq-questions")
        page.wait_for_selector("#pane-pyq-questions:not(.hidden)", timeout=5000)
        
        # F. Return to Notes Tab
        page.click("#tab-personal-notes")
        page.wait_for_selector("#pane-personal-notes:not(.hidden)", timeout=5000)
        
        print("ALL UI BUTTONS AND FEATURES AUDITED SUCCESSFULLY!")
        print("Console errors captured:", console_errors)
        assert len(console_errors) == 0, f"Found console errors: {console_errors}"
        browser.close()

if __name__ == "__main__":
    test_audit_all_ui_buttons_and_features()
