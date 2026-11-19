"""Walk the appointment portal up to the availability check."""

import logging
import random
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from cita_monitor.config import DocumentType, Settings
from cita_monitor.outcome import Outcome, RunResult

LOGGER = logging.getLogger(__name__)

ENTRY_URL = "https://icp.administracionelectronica.gob.es/icpco/index"

REJECTED_TEXT = "The requested URL was rejected"
PORTAL_ERROR_TEXT = "Se ha producido un error en el sistema"
NO_APPOINTMENTS_TEXT = "no hay citas disponibles"

DOCUMENT_RADIOS = {
    DocumentType.NIE: "#rdbTipoDocNie",
    DocumentType.DNI: "#rdbTipoDocDni",
    DocumentType.PASAPORTE: "#rdbTipoDocPas",
}


class StopRun(Exception):
    """Ends the run early with a known outcome."""

    def __init__(self, result: RunResult) -> None:
        super().__init__(result.detail)
        self.result = result


def classify_blocking_page(body_text: str, html: str) -> Outcome | None:
    """Return an outcome if the page is a rejection/challenge/error page."""
    if REJECTED_TEXT in body_text:
        return Outcome.BLOCKED
    if not body_text.strip() and "/TSPD/" in html:
        return Outcome.BLOCKED
    if PORTAL_ERROR_TEXT in body_text:
        return Outcome.PORTAL_ERROR
    return None


def classify_result_page(body_text: str) -> Outcome:
    """Decide availability from the page shown after 'Solicitar Cita'."""
    if NO_APPOINTMENTS_TEXT in body_text.lower():
        return Outcome.NO_APPOINTMENTS
    return Outcome.APPOINTMENTS_FOUND


class PortalFlow:
    def __init__(self, page: Page, settings: Settings) -> None:
        self.page = page
        self.settings = settings
        self.step = "start"

    # --- helpers -----------------------------------------------------------

    def pause(self) -> None:
        delay = random.uniform(self.settings.step_delay_min, self.settings.step_delay_max)
        self.page.wait_for_timeout(delay * 1000)

    def check_page(self) -> None:
        """Stop the run if the current page is a block or error page."""
        self.page.wait_for_load_state("load")
        body = self.page.locator("body").inner_text(timeout=5_000)
        outcome = classify_blocking_page(body, self.page.content())
        if outcome is not None:
            raise StopRun(RunResult(outcome, f"{outcome} page at {self.page.url}", self.step))

    def expect(self, locator: Locator, what: str) -> Locator:
        """Wait for an element, or stop with FLOW_CHANGED (after re-checking for blocks)."""
        try:
            locator.first.wait_for(state="visible", timeout=15_000)
        except PlaywrightTimeoutError:
            self.check_page()
            raise StopRun(
                RunResult(Outcome.FLOW_CHANGED, f"{what} not found at {self.page.url}", self.step)
            ) from None
        return locator.first

    def click_and_wait(self, locator: Locator) -> None:
        with self.page.expect_navigation(wait_until="load", timeout=30_000):
            locator.click()
        self.check_page()

    # --- steps -------------------------------------------------------------

    def choose_province(self) -> None:
        self.step = "province"
        self.page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=30_000)
        select = self.expect(self.page.locator("select#form"), "Province dropdown")
        self.pause()
        select.select_option(label=self.settings.province)
        self.pause()
        self.click_and_wait(self.page.locator("#btnAceptar"))

    def choose_office_and_procedure(self) -> None:
        self.step = "office"
        office = self.expect(self.page.locator("select#sede"), "Office dropdown")
        self.pause()
        # Changing the office submits the form (to /selectSede) and reloads the page.
        with self.page.expect_navigation(wait_until="load", timeout=30_000):
            office.select_option(label=self.settings.office)
        self.check_page()

        self.step = "procedure"
        # After the reload the procedure list is re-rendered (its id changes),
        # so find whichever dropdown offers our procedure.
        procedure = self.page.locator("select").filter(
            has=self.page.locator("option", has_text=self.settings.procedure)
        )
        procedure = self.expect(procedure, f"Procedure '{self.settings.procedure}'")
        self.pause()
        procedure.select_option(label=self.settings.procedure)
        self.pause()
        self.click_and_wait(self.page.locator("#btnAceptar"))

    def enter_without_clave(self) -> None:
        self.step = "sin_clave"
        button = self.page.locator("#btnEntrar").or_(
            self.page.get_by_text("Presentación sin Cl@ve", exact=True)
        )
        button = self.expect(button, "'Presentación sin Cl@ve' button")
        self.pause()
        self.click_and_wait(button)

    def fill_applicant(self) -> None:
        self.step = "applicant"
        radio = self.expect(
            self.page.locator(DOCUMENT_RADIOS[self.settings.document_type]), "Document type"
        )
        radio.check()
        self.expect(self.page.locator("#txtIdCitado"), "Document number field").fill(
            self.settings.document_number
        )
        self.expect(self.page.locator("#txtDesCitado"), "Name field").fill(self.settings.full_name)
        self.pause()
        self.click_and_wait(self.page.locator("#btnEnviar"))

    def request_appointment(self) -> RunResult:
        self.step = "solicitar"
        button = self.expect(self.page.locator("#btnEnviar"), "'Solicitar Cita' button")
        self.pause()
        self.click_and_wait(button)

        self.step = "result"
        body = self.page.locator("body").inner_text()
        outcome = classify_result_page(body)
        return RunResult(outcome, " ".join(body.split())[:300], self.step)

    def run(self) -> RunResult:
        self.choose_province()
        self.choose_office_and_procedure()
        self.enter_without_clave()
        self.fill_applicant()
        return self.request_appointment()


def save_debug(page: Page, settings: Settings, result: RunResult) -> Path | None:
    """Save a screenshot and HTML of the last page for anything but a clean 'no'."""
    try:
        folder = Path(settings.debug_dir)
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / f"{datetime.now():%Y%m%d-%H%M%S}-{result.outcome}-{result.step}"
        page.screenshot(path=f"{stem}.png", full_page=True)
        Path(f"{stem}.html").write_text(page.content(), encoding="utf-8")
        return stem
    except Exception:
        LOGGER.warning("Could not save debug snapshot", exc_info=True)
        return None


def run_check(settings: Settings) -> RunResult:
    """Run the whole flow once and return its outcome. Never raises for portal issues."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        page = browser.new_page(locale="es-ES")
        flow = PortalFlow(page, settings)
        try:
            result = flow.run()
        except StopRun as stop:
            result = stop.result
        except PlaywrightTimeoutError as exc:
            result = RunResult(Outcome.UNAVAILABLE, f"Timed out: {exc.message}", flow.step)
        try:
            if result.outcome is not Outcome.NO_APPOINTMENTS and (
                stem := save_debug(page, settings, result)
            ):
                LOGGER.info("Saved snapshot to %s.{png,html}", stem)
        finally:
            browser.close()
        return result
