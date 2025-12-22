from playwright.sync_api import sync_playwright

def verify_yuusei_editor():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a mobile viewport to test responsiveness
        page = browser.new_page(viewport={"width": 375, "height": 667})

        # Load the index.html file directly from the file system
        import os
        cwd = os.getcwd()
        page.goto(f"file://{cwd}/index.html")

        # Verify title
        assert page.title() == "Trình Chỉnh Sửa Bộ Lọc Yuusei"

        # 1. Verify Ace Editor Loaded
        # Ace creates a div with class "ace_editor"
        page.wait_for_selector(".ace_editor")
        assert page.locator(".ace_editor").is_visible()

        # 2. Interact with Editor via JS
        # Set value
        page.evaluate("ace.edit('editor').setValue('! Test Content');")
        # Get value
        content = page.evaluate("ace.edit('editor').getValue();")
        assert content == "! Test Content"

        # 3. Verify Navbar Buttons
        assert page.locator("#btn-reload").is_visible()
        assert page.locator("#btn-save").is_visible()

        # 4. Settings Modal
        page.click("button[title='Cài đặt']")
        assert page.locator("h2:text('Cài Đặt')").is_visible()

        # Take screenshot
        page.screenshot(path="verification/editor_ace_mobile.png")

        browser.close()

if __name__ == "__main__":
    verify_yuusei_editor()
