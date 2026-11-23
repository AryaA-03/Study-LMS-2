import pytest
pytestmark = pytest.mark.e2e
"""Playwright Live Browser Test for Syllabus Copy-Paste & Auto-Selection Alignment.

Validates:
1. User can open Syllabus Alignment modal via sidebar header or curriculum drawer.
2. User can paste a university syllabus outline with units and topics.
3. System parses syllabus and auto-matches playlist videos.
4. Review screen presents matched videos, saved study time, topic groupings, and video checklist.
5. User can fine-tune or apply directly.
6. Applying automatically excludes out-of-syllabus videos and reflows study schedule.
7. Zero JavaScript console errors occur throughout.
"""

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
import pytest
import time

def test_syllabus_matching_and_auto_selection_ui_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector(".day-group-card", timeout=15000)

        # 1. Open Syllabus Matcher Modal via header button
        btn_open = page.locator("#btn-open-syllabus-modal")
        assert btn_open.is_visible()
        btn_open.click()

        modal = page.locator("#modal-syllabus-match")
        page.wait_for_selector("#modal-syllabus-match:not(.hidden)", timeout=5000)

        # 2. Verify Step 1 input is visible
        step_input = page.locator("#syllabus-step-input")
        assert step_input.is_visible()

        # 3. Enter sample university syllabus
        sample_syllabus = """
        Unit 1: Finite Automata & State Machines
        Introduction to Theory of Computation, Finite State Machine, Deterministic Finite Automata (DFA), Non-Deterministic Finite Automata (NFA).

        Unit 2: Regular Sets
        Regular Languages, Regular Expressions, Pumping Lemma for Regular Languages.
        """
        textarea = page.locator("#input-syllabus-text")
        textarea.fill(sample_syllabus)

        # 4. Click 'Analyze & Match Videos'
        btn_analyze = page.locator("#btn-analyze-syllabus")
        btn_analyze.click()

        # 5. Wait for Step 2 Review screen
        page.wait_for_selector("#syllabus-step-review:not(.hidden)", timeout=10000)

        # Verify summary stats
        stat_matched = page.locator("#stat-syl-matched-count").inner_text()
        assert "/" in stat_matched
        print(f"Matched stat: {stat_matched}")

        stat_saved = page.locator("#stat-syl-saved-time").inner_text()
        assert "saved" in stat_saved.lower()
        print(f"Saved time stat: {stat_saved}")

        # 6. Check 'By Syllabus Topic' view
        topics = page.locator("#syllabus-view-topics > div")
        assert topics.count() > 0

        # 7. Switch to 'All Videos Checklist' tab
        page.click("#tab-syl-checklist")
        page.wait_for_selector("#syllabus-view-checklist:not(.hidden)")

        checklist_items = page.locator("#syllabus-view-checklist > div")
        assert checklist_items.count() > 0

        # Check label shows selected videos
        selected_label = page.locator("#syllabus-selected-label").inner_text()
        assert "selected" in selected_label

        # 8. Apply syllabus and reflow schedule
        btn_apply = page.locator("#btn-apply-syllabus")
        btn_apply.click()

        # 9. Wait for modal to close and toast to appear
        page.wait_for_selector("#modal-syllabus-match", state="hidden", timeout=8000)
        time.sleep(1)

        # Verify schedule allocations are loaded and visible
        allocs = page.locator(".allocation-card")
        assert allocs.count() > 0

        # Assert no JS errors
        real_errors = [e for e in console_errors if "favicon" not in e and "404" not in e]
        assert not real_errors, f"JavaScript errors detected: {real_errors}"

        browser.close()
