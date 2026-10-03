from browser.state import (
    PageState,
    LinkState,
    ButtonState,
    InputState,
)
from browser.identity import stable_element_ids


class PageReader:
    def __init__(self, page):
        self.page = page

    def get_title(self):
        return self.page.title()

    def get_text(self):
        return self.page.locator("body").inner_text()

    def get_headings(self):
        return self.page.locator(
            "h1, h2, h3, h4, h5, h6"
        ).all_inner_texts()

    def get_regions(self):
        regions = []
        for selector, name in [
            ("nav, [role='navigation']", "navigation"),
            ("main, [role='main']", "main"),
            ("form, [role='form']", "form"),
            ("footer, [role='contentinfo']", "footer"),
            ("dialog, [role='dialog']", "dialog"),
        ]:
            if self.page.locator(selector).count() > 0:
                regions.append(name)
        return regions

    def _escape_css(self, value):
        return (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
        )

    def _build_selector(self, element):
        """
        Build the most stable selector available.
        """

        element_id = element.get_attribute("id")

        if element_id:
            return f'#{self._escape_css(element_id)}'

        name = element.get_attribute("name")

        if name:
            tag = element.evaluate(
                "(el) => el.tagName"
            ).lower()

            return (
                f'{tag}[name="{self._escape_css(name)}"]'
            )

        aria_label = element.get_attribute(
            "aria-label"
        )

        if aria_label:
            tag = element.evaluate(
                "(el) => el.tagName"
            ).lower()

            return (
                f'{tag}[aria-label="'
                f'{self._escape_css(aria_label)}"]'
            )

        placeholder = element.get_attribute(
            "placeholder"
        )

        if placeholder:
            tag = element.evaluate(
                "(el) => el.tagName"
            ).lower()

            return (
                f'{tag}[placeholder="'
                f'{self._escape_css(placeholder)}"]'
            )

        href = element.get_attribute("href")

        if href:
            tag = element.evaluate(
                "(el) => el.tagName"
            ).lower()

            return (
                f'{tag}[href="{self._escape_css(href)}"]'
            )

        return element.evaluate(
            """
            (el) => {
                const path = [];
                let current = el;

                while (
                    current &&
                    current.nodeType === Node.ELEMENT_NODE
                ) {
                    let selector =
                        current.tagName.toLowerCase();

                    if (current.id) {
                        selector += "#" + current.id;
                        path.unshift(selector);
                        break;
                    }

                    let sibling = current;
                    let index = 1;

                    while (
                        sibling.previousElementSibling
                    ) {
                        sibling =
                            sibling.previousElementSibling;

                        if (
                            sibling.tagName ===
                            current.tagName
                        ) {
                            index++;
                        }
                    }

                    if (index > 1) {
                        selector +=
                            `:nth-of-type(${index})`;
                    }

                    path.unshift(selector);

                    current = current.parentElement;
                }

                return path.join(" > ");
            }
            """
        )

    def _is_visible(self, element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def _is_enabled(self, element):
        try:
            return element.is_enabled()
        except Exception:
            return False

    def get_links(self):
        links = self.page.locator("a")
        results = []

        elements = [links.nth(i) for i in range(links.count())]
        for element, stable_id in zip(elements, stable_element_ids("link", elements)):

            results.append(
                LinkState(
                    id=stable_id,
                    text=element.inner_text().strip(),
                    href=element.get_attribute("href"),
                    selector=self._build_selector(
                        element
                    ),
                    visible=self._is_visible(
                        element
                    ),
                    enabled=self._is_enabled(
                        element
                    ),
                )
            )

        return results

    def get_buttons(self):
        buttons = self.page.locator(
            "button, "
            "input[type='button'], "
            "input[type='submit'], "
            "input[type='reset']"
        )

        results = []

        elements = [buttons.nth(i) for i in range(buttons.count())]
        for element, stable_id in zip(elements, stable_element_ids("button", elements)):

            text = (
                element.inner_text().strip()
                or element.get_attribute("value")
                or ""
            )

            results.append(
                ButtonState(
                    id=stable_id,
                    text=text,
                    aria_label=element.get_attribute(
                        "aria-label"
                    ),
                    selector=self._build_selector(
                        element
                    ),
                    visible=self._is_visible(
                        element
                    ),
                    enabled=self._is_enabled(
                        element
                    ),
                )
            )

        return results

    def _get_label(self, element):
        element_id = element.get_attribute("id")

        if element_id:
            label = self.page.locator(
                f'label[for="{self._escape_css(element_id)}"]'
            )

            if label.count() > 0:
                text = (
                    label.first
                    .inner_text()
                    .strip()
                )

                if text:
                    return text

        aria_label = element.get_attribute("aria-label")
        if aria_label:
            return aria_label.strip()

        labelledby = element.get_attribute("aria-labelledby")
        if labelledby:
            labels = []
            for reference in labelledby.split():
                node = self.page.locator(
                    f'#{self._escape_css(reference)}'
                )
                if node.count() > 0:
                    text = node.first.inner_text().strip()
                    if text:
                        labels.append(text)
            if labels:
                return " ".join(labels)

        parent_label = element.locator(
            "xpath=ancestor::label"
        )

        if parent_label.count() > 0:
            text = (
                parent_label.first
                .inner_text()
                .strip()
            )

            if text:
                return text

        placeholder = element.get_attribute("placeholder")
        if placeholder:
            return placeholder.strip()

        name = element.get_attribute("name")
        if name:
            return name.strip()

        return None

    def get_inputs(self):
        inputs = self.page.locator(
            "input, textarea, select"
        )

        results = []

        elements = [inputs.nth(i) for i in range(inputs.count())]
        for element, stable_id in zip(elements, stable_element_ids("input", elements)):

            tag = element.evaluate(
                "(el) => el.tagName"
            )

            input_type = (
                element.get_attribute("type")
                or ""
            )

            value = None

            try:
                value = element.input_value()
            except Exception:
                pass

            checked = None
            if input_type.lower() in {"checkbox", "radio"}:
                try:
                    checked = element.is_checked()
                except Exception:
                    pass

            options = []
            selected = None
            if tag.upper() == "SELECT":
                try:
                    options = [
                        text.strip()
                        for text in element.locator("option").all_inner_texts()
                        if text.strip()
                    ]
                    selected = value
                except Exception:
                    pass

            form = element.locator("xpath=ancestor::form")
            form_id = None
            if form.count() > 0:
                form_id = form.first.get_attribute("id")

            results.append(
                InputState(
                    id=stable_id,
                    tag=tag,
                    type=input_type,
                    name=element.get_attribute(
                        "name"
                    ),
                    placeholder=element.get_attribute(
                        "placeholder"
                    ),
                    aria_label=element.get_attribute(
                        "aria-label"
                    ),
                    label=self._get_label(
                        element
                    ),
                    value=value,
                    selector=self._build_selector(
                        element
                    ),
                    visible=self._is_visible(
                        element
                    ),
                    enabled=self._is_enabled(
                        element
                    ),
                    role=(element.get_attribute("role") or (
                        "combobox" if tag.upper() == "SELECT" else
                        "checkbox" if input_type.lower() == "checkbox" else
                        "radio" if input_type.lower() == "radio" else
                        "textbox"
                    )),
                    aria_labelledby=element.get_attribute("aria-labelledby"),
                    checked=checked,
                    selected=selected,
                    options=options,
                    form_id=form_id,
                )
            )

        return results

    def read_page(self):
        return PageState(
            url=self.page.url,
            title=self.get_title(),
            headings=self.get_headings(),
            links=self.get_links(),
            buttons=self.get_buttons(),
            inputs=self.get_inputs(),
            text=self.get_text(),
            regions=self.get_regions(),
        )
