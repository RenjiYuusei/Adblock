from playwright.sync_api import sync_playwright

def verify_yuusei_editor():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load the index.html file directly from the file system
        import os
        cwd = os.getcwd()
        page.goto(f"file://{cwd}/index.html")

        # Verify title (Updated to Vietnamese)
        assert page.title() == "Trình Chỉnh Sửa Bộ Lọc Yuusei"

        # Verify navbar components
        assert page.locator("h1:text('Yuusei Editor')").is_visible()

        # Button text changed to "Lưu Thay Đổi"
        # Since it might have icon, use loose match or role
        assert page.get_by_role("button", name="Lưu Thay Đổi").first.is_visible()

        # Verify text editor exists
        assert page.locator("#editor").is_visible()

        # Verify settings modal logic
        # Click settings button (icon cog)
        page.click(".fa-cog")

        # Check if modal is visible (Text: Cài Đặt)
        # Note: The modal might have a transition, so we might need to wait or check visibility carefully
        # But playwright auto-waits.
        assert page.locator("h2:text('Cài Đặt')").is_visible()

        # Take screenshot of the settings modal
        page.screenshot(path="verification/editor_settings.png")

        # Close modal by clicking "Hủy" button
        page.get_by_role("button", name="Hủy").click()

        # Take screenshot of main editor
        page.screenshot(path="verification/editor_main.png")

        browser.close()

if __name__ == "__main__":
    verify_yuusei_editor()
