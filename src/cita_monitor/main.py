"""Open the appointment portal and inspect its province selector."""

import logging

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGGER = logging.getLogger(__name__)
URL = "https://icp.administracionelectronica.gob.es/icpco/acInfo"


def inspect_provinces() -> list[str]:
    """Return visible options from the province selector, if available."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page(locale="es-ES")
            LOGGER.info("Opening %s", URL)
            page.goto(URL, wait_until="domcontentloaded", timeout=30_000)

            # Prefer the accessible label; fall back to nearby form controls.
            selector = page.get_by_label("PROVINCIAS DISPONIBLES", exact=False)
            if selector.count() == 0:
                selector = page.locator("select").first

            try:
                selector.wait_for(state="visible", timeout=15_000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(
                    "Province selector was not found. Inspect the open page: "
                    "the portal may have changed or displayed an access challenge."
                ) from exc

            if selector.evaluate("(el) => el.tagName.toLowerCase()") != "select":
                raise RuntimeError("Found a labeled element, but it is not a select dropdown.")

            options = [value.strip() for value in selector.locator("option").all_text_contents()]
            LOGGER.info("Province dropdown found (%d options)", len(options))
            for option in options:
                LOGGER.info("  %s", option)
            page.wait_for_timeout(5_000)
            return options
        finally:
            browser.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        inspect_provinces()
    except Exception:
        LOGGER.exception("Could not inspect province options")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
