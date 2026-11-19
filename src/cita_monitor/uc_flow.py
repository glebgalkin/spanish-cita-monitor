"""Selenium-compatible alternative browser backend for the appointment flow.

Uses undetected-chromedriver's WebDriver interface without custom fingerprint
spoofing, challenge solving, or retries after access rejection.
"""

import logging
import random
import time
from datetime import datetime
from pathlib import Path

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from cita_monitor.config import DocumentType, Settings
from cita_monitor.outcome import Outcome, RunResult

LOGGER = logging.getLogger(__name__)
ENTRY_URL = "https://icp.administracionelectronica.gob.es/icpco/index"
DOCUMENT_RADIOS = {
    DocumentType.NIE: "#rdbTipoDocNie",
    DocumentType.DNI: "#rdbTipoDocDni",
    DocumentType.PASAPORTE: "#rdbTipoDocPas",
}


def classify_page(text: str, html: str) -> Outcome | None:
    if "The requested URL was rejected" in text:
        return Outcome.BLOCKED
    if not text.strip() and "/TSPD/" in html:
        return Outcome.BLOCKED
    if "Se ha producido un error en el sistema" in text:
        return Outcome.PORTAL_ERROR
    return None


def classify_result(text: str) -> Outcome:
    """Fail closed until an explicit positive appointment signal is verified."""
    if "no hay citas disponibles" in text.lower():
        return Outcome.NO_APPOINTMENTS
    return Outcome.FLOW_CHANGED


class StopRun(Exception):
    def __init__(self, result: RunResult):
        super().__init__(result.detail)
        self.result = result


class SeleniumFlow:
    def __init__(self, driver, settings: Settings):
        self.driver = driver
        self.settings = settings
        self.step = "start"

    def pause(self):
        time.sleep(random.uniform(self.settings.step_delay_min, self.settings.step_delay_max))

    def check(self):
        outcome = classify_page(self.driver.find_element(By.TAG_NAME, "body").text,
                                self.driver.page_source)
        if outcome is not None:
            raise StopRun(RunResult(outcome, f"{outcome} at {self.driver.current_url}", self.step))

    def find(self, selector, description):
        try:
            return WebDriverWait(self.driver, 15).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            self.check()
            raise StopRun(RunResult(Outcome.FLOW_CHANGED,
                                    f"{description} missing at {self.driver.current_url}",
                                    self.step)) from None

    def wait_change(self, previous_url, previous_html):
        try:
            WebDriverWait(self.driver, 30).until(
                lambda d: d.current_url != previous_url or d.page_source != previous_html
            )
        except TimeoutException:
            self.check()
            raise
        self.check()

    def click(self, selector, description):
        element = self.find(selector, description)
        url, html = self.driver.current_url, self.driver.page_source
        element.click()
        self.wait_change(url, html)

    def run(self):
        self.step = "province"
        self.driver.get(ENTRY_URL)
        self.check()
        Select(self.find("select#form", "Province dropdown")).select_by_visible_text(
            self.settings.province
        )
        self.pause()
        self.click("#btnAceptar", "Province accept button")

        self.step = "office"
        self.pause()
        office = self.find("select#sede", "Office dropdown")
        url, html = self.driver.current_url, self.driver.page_source
        Select(office).select_by_visible_text(self.settings.office)
        self.wait_change(url, html)

        self.step = "procedure"
        self.pause()
        procedure = None
        for element in self.driver.find_elements(By.CSS_SELECTOR, "select"):
            if any(self.settings.procedure == option.text.strip()
                   for option in Select(element).options):
                procedure = element
                break
        if procedure is None:
            self.check()
            raise StopRun(RunResult(Outcome.FLOW_CHANGED, "Procedure dropdown missing",
                                    self.step))
        Select(procedure).select_by_visible_text(self.settings.procedure)
        self.pause()
        self.click("#btnAceptar", "Procedure accept button")

        self.step = "sin_clave"
        self.pause()
        self.click("#btnEntrar", "Presentación sin Cl@ve button")

        self.step = "applicant"
        self.find(DOCUMENT_RADIOS[self.settings.document_type], "Document type").click()
        self.find("#txtIdCitado", "Document number").send_keys(self.settings.document_number)
        self.find("#txtDesCitado", "Full name").send_keys(self.settings.full_name)
        self.pause()
        self.click("#btnEnviar", "Applicant accept button")

        self.step = "solicitar"
        self.pause()
        self.click("#btnEnviar", "Solicitar Cita button")

        self.step = "result"
        text = self.driver.find_element(By.TAG_NAME, "body").text
        outcome = classify_result(text)
        return RunResult(outcome, " ".join(text.split())[:300], self.step)


def save_debug(driver, settings, result):
    try:
        directory = Path(settings.debug_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = directory / f"{datetime.now():%Y%m%d-%H%M%S}-uc-{result.outcome}-{result.step}"
        driver.save_screenshot(f"{stem}.png")
        Path(f"{stem}.html").write_text(driver.page_source, encoding="utf-8")
        LOGGER.info("Saved snapshot to %s.{png,html}", stem)
    except Exception:
        LOGGER.warning("Could not save debug snapshot", exc_info=True)


def run_check(settings: Settings) -> RunResult:
    options = uc.ChromeOptions()
    if settings.headless:
        options.add_argument("--headless=new")
    driver = None
    try:
        driver = uc.Chrome(options=options)
        driver.set_page_load_timeout(30)
        flow = SeleniumFlow(driver, settings)
        try:
            result = flow.run()
        except StopRun as stop:
            result = stop.result
        except TimeoutException as exc:
            result = RunResult(Outcome.UNAVAILABLE, str(exc)[:300], flow.step)
        except WebDriverException as exc:
            result = RunResult(Outcome.UNAVAILABLE, str(exc)[:300], flow.step)
        if result.outcome is not Outcome.NO_APPOINTMENTS:
            save_debug(driver, settings, result)
        return result
    except (OSError, WebDriverException) as exc:
        return RunResult(Outcome.UNAVAILABLE, f"Browser startup failed: {exc}", "start")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                LOGGER.warning("Browser shutdown failed", exc_info=True)
