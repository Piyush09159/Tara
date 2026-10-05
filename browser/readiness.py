"""Bounded, structured page-readiness probing for synchronous Playwright."""
import hashlib
import time


class PageReadiness:
    POLL_SECONDS = 0.10
    STABLE_FOR_SECONDS = 0.30
    DEFAULT_TIMEOUT_SECONDS = 4.0

    def __init__(self, page, on_page_change=None):
        self.page = page
        self.on_page_change = on_page_change
        self.telemetry = {"readiness_attempts": 0, "readiness_timeouts": 0,
                          "fingerprint_changes": 0}

    def _sample(self):
        try:
            ready = self.page.evaluate("document.readyState")
            title = self.page.title()
            text = self.page.locator("body").inner_text(timeout=500)[:4000]
            count = self.page.locator("a, button, input, textarea, select").count()
        except Exception:
            ready, title, text, count = "loading", "", "", -1
        signature = "|".join([self.page.url, title, text, str(count), ready])
        return {"url": self.page.url, "title": title, "ready_state": ready,
                "interactive_count": count,
                "fingerprint": hashlib.sha1(signature.encode("utf-8")).hexdigest()}

    def wait(self, timeout=DEFAULT_TIMEOUT_SECONDS, stable_for=STABLE_FOR_SECONDS):
        start = time.monotonic(); last = self._sample(); stable_since = start
        attempts = 1
        while time.monotonic() - start < timeout:
            time.sleep(self.POLL_SECONDS)
            if self.on_page_change:
                changed = self.on_page_change()
                if changed is not None:
                    self.page = changed
            current = self._sample(); attempts += 1
            if current["fingerprint"] != last["fingerprint"]:
                self.telemetry["fingerprint_changes"] += 1
                last, stable_since = current, time.monotonic()
                continue
            if current["ready_state"] in {"interactive", "complete"} and time.monotonic() - stable_since >= stable_for:
                self.telemetry["readiness_attempts"] += attempts
                return {"settled": True, "elapsed": round(time.monotonic()-start, 3),
                        "attempts": attempts, **current}
        self.telemetry["readiness_attempts"] += attempts
        self.telemetry["readiness_timeouts"] += 1
        return {"settled": False, "elapsed": round(time.monotonic()-start, 3),
                "attempts": attempts, **last}
