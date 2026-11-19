# Spanish Cita Monitor

A small Python project for inspecting Spain's immigration appointment portal.

## Setup

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync
uv run playwright install chromium
uv run cita-monitor
```

The command launches a **visible** Chromium browser, visits the appointment portal,
looks for the **PROVINCIAS DISPONIBLES** dropdown, and logs its options.
It does **not** select a province, submit forms, book appointments, or send Telegram messages.

If the portal shows a challenge or changes its markup, the command may fail with
a descriptive error. No attempt is made to bypass access controls.

## Development

```bash
uv run pytest
uv run ruff check .
```

Python 3.12 is the default. Dependencies include Playwright, HTTPX,
pydantic-settings, and python-telegram-bot (reserved for later work).

## Project layout

```text
src/cita_monitor/   Application code
tests/              Tests
pyproject.toml       Package and dependency configuration
```
