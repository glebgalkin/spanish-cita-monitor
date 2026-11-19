"""Command-line entry point: run one availability check and report the outcome."""

import logging

from pydantic import ValidationError

from cita_monitor.config import Settings
from cita_monitor.flow import run_check
from cita_monitor.outcome import Outcome

LOGGER = logging.getLogger("cita_monitor")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        settings = Settings()
    except ValidationError as exc:
        LOGGER.error("Invalid configuration (see .env.example):\n%s", exc)
        raise SystemExit(2) from None

    LOGGER.info("Checking %s / %s / %s", settings.province, settings.office, settings.procedure)
    result = run_check(settings)
    level = logging.WARNING if result.outcome is Outcome.APPOINTMENTS_FOUND else logging.INFO
    LOGGER.log(level, "OUTCOME=%s step=%s detail=%s", result.outcome, result.step, result.detail)
    raise SystemExit(result.outcome.exit_code)


if __name__ == "__main__":
    main()
