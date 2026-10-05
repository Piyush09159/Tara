from playwright.sync_api import sync_playwright


class Browser:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.pages = []
        self.runtime_telemetry = {
            "popup_detected": 0, "page_switches": 0,
            "dialogs_dismissed": 0,
        }

    def start(self):
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.headless
        )

        self.page = self.browser.new_page()
        self.pages = [self.page]
        self._attach_page(self.page)

    def _attach_page(self, page):
        """Register lightweight lifecycle handling for a Playwright page."""
        page.on("dialog", lambda dialog: self._dismiss_dialog(dialog))

    def _dismiss_dialog(self, dialog):
        # Native alerts silently block subsequent Playwright actions.  Dismiss
        # them conservatively; confirm/alert intent is not inferred as a task.
        try:
            dialog.dismiss()
            self.runtime_telemetry["dialogs_dismissed"] += 1
        except Exception:
            pass

    def refresh_pages(self):
        if not self.browser:
            return self.page
        live_pages = list(self.browser.contexts[0].pages)
        for page in live_pages:
            if page not in self.pages:
                self.pages.append(page)
                self._attach_page(page)
                self.runtime_telemetry["popup_detected"] += 1
                self.page = page
                self.runtime_telemetry["page_switches"] += 1
        self.pages = [page for page in self.pages if not page.is_closed()]
        return self.page

    def set_active_page(self, page):
        if page is not self.page:
            self.page = page
            self.runtime_telemetry["page_switches"] += 1
        if page not in self.pages:
            self.pages.append(page)
            self._attach_page(page)

    def open(self, url: str):
        if self.page is None:
            raise RuntimeError("Browser has not been started.")

        self.page.goto(url, wait_until="domcontentloaded")

    def get_title(self) -> str:
        if self.page is None:
            raise RuntimeError("Browser has not been started.")

        return self.page.title()

    def get_text(self) -> str:
        if self.page is None:
            raise RuntimeError("Browser has not been started.")

        return self.page.locator("body").inner_text()

    def close(self):
        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()
