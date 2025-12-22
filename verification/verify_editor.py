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

        # Verify title (Updated to Vietnamese)
        assert page.title() == "Trình Chỉnh Sửa Bộ Lọc Yuusei"

        # 1. Verify Mobile Navbar
        # Title should be visible (compact version)
        # Using a broader selector and checking if ANY is visible, since CSS media queries hide/show different ones
        # The mobile view should show <div class="sm:hidden"><h1 ...>Yuusei</h1></div>
        assert page.locator(".sm\\:hidden h1:text('Yuusei')").is_visible()

        # Search toggle button should be visible
        page.click("button[title='Tìm kiếm']")
        assert page.locator("#search-bar").is_visible()

        # Test search input typing
        page.fill("#search-input", "test")

        # Close search
        page.locator("#search-bar button:has(.fa-times)").click()

        # 2. Verify Text Editor
        assert page.locator("#editor").is_visible()

        # 3. Verify Settings Modal
        page.click("button[title='Cài đặt']")
        assert page.locator("h2:text('Cài Đặt')").is_visible()

        # Take screenshot of mobile view
        page.screenshot(path="verification/editor_mobile.png")

        # Close modal
        page.click("button:text('Đóng')")

        browser.close()

if __name__ == "__main__":
    verify_yuusei_editor()
