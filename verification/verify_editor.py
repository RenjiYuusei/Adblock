from playwright.sync_api import sync_playwright

def verify_yuusei_editor():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the index.html file directly from the file system
        import os
        cwd = os.getcwd()
        page.goto(f"file://{cwd}/index.html")

        # Verify title
        assert page.title() == "Yuusei Filter Editor"

        # Verify navbar components
        # Use more specific selectors or get_by_role to avoid strictness violations
        assert page.locator("h1:text('Yuusei Editor')").is_visible()

        # "Save" appears in multiple places (button text, modal text), so we use role=button
        # But here the button text is "Save" (with an icon).
        # Let's target the specific save button in the navbar.
        # The button has "Save" text.
        assert page.get_by_role("button", name="Save").first.is_visible()

        assert page.locator(".fa-cog").is_visible()

        # Verify text editor exists
        assert page.locator("#editor").is_visible()

        # Verify settings modal logic
        # Click settings button
        page.click(".fa-cog")
        # Check if modal is visible
        assert page.locator("text=GitHub Personal Access Token").is_visible()

        # Take screenshot of the settings modal
        page.screenshot(path="verification/editor_settings.png")

        # Close modal by clicking "Cancel" button
        page.get_by_role("button", name="Cancel").click()

        # Take screenshot of main editor
        page.screenshot(path="verification/editor_main.png")

        browser.close()

if __name__ == "__main__":
    verify_yuusei_editor()
