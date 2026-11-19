"""Command-line entry point: run one availability check and report the outcome."""

import logging
import random
import time

from pydantic import ValidationError

from cita_monitor.config import Settings
from cita_monitor.flow import run_check
from cita_monitor.notify import send_report
from cita_monitor.outcome import Outcome

LOGGER = logging.getLogger("cita_monitor")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        settings = Settings()
    except ValidationError as exc:
        LOGGER.error("Invalid configuration (see .env.example):\n%s", exc)
        raise SystemExit(2) from None

    if settings.start_delay_max > 0:
        delay = random.uniform(settings.start_delay_min, settings.start_delay_max)
        LOGGER.info("Waiting %.0f s before starting", delay)
        time.sleep(delay)

    LOGGER.info("Checking %s / %s / %s", settings.province, settings.office, settings.procedure)
    result = run_check(settings)
    level = logging.WARNING if result.outcome is Outcome.APPOINTMENTS_FOUND else logging.INFO
    LOGGER.log(level, "OUTCOME=%s step=%s detail=%s", result.outcome, result.step, result.detail)
    send_report(result, settings)
    raise SystemExit(result.outcome.exit_code)


if __name__ == "__main__":
    main()
