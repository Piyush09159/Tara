import time

from agent.action import BrowserAction
from browser.identity import stable_element_ids


class BrowserActions:

    def __init__(self, page):
        self.page = page

    # =========================================================
    # ELEMENT LOOKUP
    # =========================================================

    def _find_by_id(
        self,
        element_id: str,
    ):
        if "_" not in element_id:
            raise ValueError(
                f"Invalid Tara element ID: {element_id}"
            )

        element_type, _ = element_id.split(
            "_",
            1,
        )

        if element_type == "input":

            locator = self.page.locator(
                "input, textarea, select"
            )

        elif element_type == "link":

            locator = self.page.locator(
                "a"
            )

        elif element_type == "button":

            locator = self.page.locator(
                "button, "
                "input[type='button'], "
                "input[type='submit'], "
                "input[type='reset']"
            )

        else:

            raise ValueError(
                f"Unsupported element type: "
                f"{element_type}"
            )

        elements = [locator.nth(index) for index in range(locator.count())]

        for element, current_id in zip(
            elements,
            stable_element_ids(element_type, elements),
        ):

            if current_id == element_id:
                return element

        raise LookupError(
            f"Could not resolve Tara element: "
            f"{element_id}"
        )


    # =========================================================
    # WAIT FOR SETTLE
    # =========================================================

    def wait_for_settle(
        self,
        timeout=10.0,
        stable_for=0.5,
    ):

        start = time.monotonic()

        last_url = self.page.url

        try:

            last_text = (
                self.page
                .locator("body")
                .inner_text(
                    timeout=3000
                )
            )

        except Exception:

            last_text = ""

        stable_since = time.monotonic()

        while (
            time.monotonic() - start
            < timeout
        ):

            time.sleep(0.1)

            current_url = self.page.url

            try:

                current_text = (
                    self.page
                    .locator("body")
                    .inner_text(
                        timeout=1000
                    )
                )

            except Exception:

                current_text = ""

            if (
                current_url == last_url
                and current_text == last_text
            ):

                if (
                    time.monotonic()
                    - stable_since
                    >= stable_for
                ):

                    return {
                        "settled": True,
                        "url": current_url,
                        "elapsed": round(
                            time.monotonic()
                            - start,
                            3,
                        ),
                    }

            else:

                last_url = current_url
                last_text = current_text

                stable_since = (
                    time.monotonic()
                )

        return {
            "settled": False,
            "url": self.page.url,
            "elapsed": round(
                time.monotonic()
                - start,
                3,
            ),
        }

    # =========================================================
    # CLICK
    # =========================================================

    def click(
        self,
        element_id: str,
    ):

        try:

            element = self._find_by_id(
                element_id
            )

        except LookupError as error:

            return {
                "success": False,
                "action": "click",
                "error_type": "ELEMENT_NOT_FOUND",
                "error": str(error),
                "element_id": element_id,
            }

        try:

            if not element.is_visible():

                return {
                    "success": False,
                    "action": "click",
                    "error_type": (
                        "ELEMENT_NOT_VISIBLE"
                    ),
                    "error": (
                        "Element is not visible."
                    ),
                    "element_id": element_id,
                }

        except Exception:

            pass

        try:

            if not element.is_enabled():

                return {
                    "success": False,
                    "action": "click",
                    "error_type": (
                        "ELEMENT_DISABLED"
                    ),
                    "error": (
                        "Element is disabled."
                    ),
                    "element_id": element_id,
                }

        except Exception:

            pass

        old_url = self.page.url

        try:

            element.click()

        except Exception as error:

            return {
                "success": False,
                "action": "click",
                "error_type": "CLICK_ERROR",
                "error": str(error),
                "element_id": element_id,
            }

        settle_result = (
            self.wait_for_settle()
        )

        return {
            "success": True,
            "action": "click",
            "element_id": element_id,
            "old_url": old_url,
            "new_url": self.page.url,
            "navigated": (
                old_url != self.page.url
            ),
            "settle": settle_result,
        }

    # =========================================================
    # TYPE
    # =========================================================

    def type(
        self,
        element_id: str,
        text: str,
    ):

        try:

            element = self._find_by_id(
                element_id
            )

        except LookupError as error:

            return {
                "success": False,
                "action": "type",
                "error_type": "ELEMENT_NOT_FOUND",
                "error": str(error),
                "element_id": element_id,
                "text": text,
            }

        try:

            if not element.is_visible():

                return {
                    "success": False,
                    "action": "type",
                    "error_type": (
                        "ELEMENT_NOT_VISIBLE"
                    ),
                    "error": (
                        "Element is not visible."
                    ),
                    "element_id": element_id,
                    "text": text,
                }

        except Exception:

            pass

        try:

            if not element.is_enabled():

                return {
                    "success": False,
                    "action": "type",
                    "error_type": (
                        "ELEMENT_DISABLED"
                    ),
                    "error": (
                        "Element is disabled."
                    ),
                    "element_id": element_id,
                    "text": text,
                }

        except Exception:

            pass

        try:

            element.fill(text)

        except Exception as error:

            return {
                "success": False,
                "action": "type",
                "error_type": "TYPE_ERROR",
                "error": str(error),
                "element_id": element_id,
                "text": text,
            }

        return {
            "success": True,
            "action": "type",
            "element_id": element_id,
            "text": text,
        }

    # =========================================================
    # FORM CONTROLS
    # =========================================================

    def _form_control(self, action, element_id):
        """Resolve a current, interactable form target before mutation."""
        try:
            element = self._find_by_id(element_id)
        except LookupError as error:
            return None, {
                "success": False, "action": action,
                "error_type": "ELEMENT_NOT_FOUND", "error": str(error),
                "element_id": element_id,
            }
        try:
            if not element.is_visible():
                return None, {"success": False, "action": action,
                              "error_type": "ELEMENT_NOT_VISIBLE",
                              "error": "Element is not visible.",
                              "element_id": element_id}
            if not element.is_enabled():
                return None, {"success": False, "action": action,
                              "error_type": "ELEMENT_DISABLED",
                              "error": "Element is disabled.",
                              "element_id": element_id}
        except Exception:
            pass
        return element, None

    def select(self, element_id: str, option: str):
        element, failure = self._form_control("select", element_id)
        if failure:
            return failure
        try:
            element.select_option(label=option)
        except Exception:
            try:
                element.select_option(value=option)
            except Exception as error:
                return {"success": False, "action": "select",
                        "error_type": "SELECT_ERROR", "error": str(error),
                        "element_id": element_id, "option": option}
        return {"success": True, "action": "select", "element_id": element_id,
                "option": option}

    def check(self, element_id: str):
        element, failure = self._form_control("check", element_id)
        if failure:
            return failure
        try:
            element.check()
        except Exception as error:
            return {"success": False, "action": "check",
                    "error_type": "CHECK_ERROR", "error": str(error),
                    "element_id": element_id}
        return {"success": True, "action": "check", "element_id": element_id}

    def uncheck(self, element_id: str):
        element, failure = self._form_control("uncheck", element_id)
        if failure:
            return failure
        try:
            element.uncheck()
        except Exception as error:
            return {"success": False, "action": "uncheck",
                    "error_type": "UNCHECK_ERROR", "error": str(error),
                    "element_id": element_id}
        return {"success": True, "action": "uncheck", "element_id": element_id}

    # =========================================================
    # PRESS
    # =========================================================

    def press(
        self,
        key: str,
    ):

        try:

            self.page.keyboard.press(
                key
            )

        except Exception as error:

            return {
                "success": False,
                "action": "press",
                "error_type": "KEY_PRESS_ERROR",
                "error": str(error),
                "key": key,
            }

        settle_result = (
            self.wait_for_settle(
                timeout=5.0
            )
        )

        return {
            "success": True,
            "action": "press",
            "key": key,
            "settle": settle_result,
        }

    # =========================================================
    # NAVIGATE
    # =========================================================

    def navigate(
        self,
        url: str,
    ):

        old_url = self.page.url

        try:

            self.page.goto(
                url,
                wait_until="domcontentloaded",
            )

        except Exception as error:

            return {
                "success": False,
                "action": "navigate",
                "error_type": (
                    "NAVIGATION_ERROR"
                ),
                "error": str(error),
                "url": url,
            }

        settle_result = (
            self.wait_for_settle()
        )

        return {
            "success": True,
            "action": "navigate",
            "old_url": old_url,
            "new_url": self.page.url,
            "navigated": (
                old_url != self.page.url
            ),
            "settle": settle_result,
        }

    # =========================================================
    # BACK
    # =========================================================

    def go_back(self):

        old_url = self.page.url

        try:

            self.page.go_back(
                wait_until="domcontentloaded"
            )

        except Exception as error:

            return {
                "success": False,
                "action": "back",
                "error_type": (
                    "NAVIGATION_ERROR"
                ),
                "error": str(error),
            }

        settle_result = (
            self.wait_for_settle()
        )

        return {
            "success": True,
            "action": "back",
            "old_url": old_url,
            "new_url": self.page.url,
            "settle": settle_result,
        }

    # =========================================================
    # FORWARD
    # =========================================================

    def go_forward(self):

        old_url = self.page.url

        try:

            self.page.go_forward(
                wait_until="domcontentloaded"
            )

        except Exception as error:

            return {
                "success": False,
                "action": "forward",
                "error_type": (
                    "NAVIGATION_ERROR"
                ),
                "error": str(error),
            }

        settle_result = (
            self.wait_for_settle()
        )

        return {
            "success": True,
            "action": "forward",
            "old_url": old_url,
            "new_url": self.page.url,
            "settle": settle_result,
        }

    # =========================================================
    # WAIT
    # =========================================================

    def wait(
        self,
        seconds: float,
    ):

        try:

            time.sleep(seconds)

        except Exception as error:

            return {
                "success": False,
                "action": "wait",
                "error_type": "WAIT_ERROR",
                "error": str(error),
                "seconds": seconds,
            }

        return {
            "success": True,
            "action": "wait",
            "seconds": seconds,
        }

    # =========================================================
    # UNIFIED EXECUTION
    # =========================================================

    def execute(
        self,
        raw_action,
    ):

        if isinstance(
            raw_action,
            BrowserAction,
        ):

            action = raw_action

        else:

            action = (
                BrowserAction.model_validate(
                    raw_action
                )
            )

        action.validate_requirements()

        if action.action == "click":

            return self.click(
                action.element_id
            )

        if action.action == "type":

            return self.type(
                action.element_id,
                action.text,
            )

        if action.action == "select":
            return self.select(action.element_id, action.option)

        if action.action == "check":
            return self.check(action.element_id)

        if action.action == "uncheck":
            return self.uncheck(action.element_id)

        if action.action == "press":

            return self.press(
                action.key
            )

        if action.action == "navigate":

            return self.navigate(
                action.url
            )

        if action.action == "back":

            return self.go_back()

        if action.action == "forward":

            return self.go_forward()

        if action.action == "wait":

            return self.wait(
                action.seconds
            )

        raise ValueError(
            f"Unsupported action: "
            f"{action.action}"
        )
