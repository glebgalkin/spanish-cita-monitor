"""Send each run's outcome to Telegram."""

import json
import logging
import socket
import time
from datetime import datetime
from pathlib import Path

import httpx

from cita_monitor.config import Settings
from cita_monitor.outcome import Outcome, RunResult

LOGGER = logging.getLogger(__name__)

PORTAL_URL = "https://icp.administracionelectronica.gob.es/icpco/index"
TELEGRAM_API = "https://api.telegram.org"
MAX_DETAIL = 300
# Seconds to wait before each retry of a failed Telegram call (3 attempts in total).
RETRY_WAITS = (3.0, 10.0)
MAX_RETRY_WAIT = 30.0

ICONS = {
    Outcome.APPOINTMENTS_FOUND: "🟢",
    Outcome.NO_APPOINTMENTS: "⚪",
    Outcome.BLOCKED: "⛔",
    Outcome.PORTAL_ERROR: "🟠",
    Outcome.UNAVAILABLE: "🟠",
    Outcome.FLOW_CHANGED: "⚠️",
}

# Outcomes that need a human: notify with sound. Everything else arrives silently.
LOUD = {Outcome.APPOINTMENTS_FOUND, Outcome.FLOW_CHANGED}


def format_report(result: RunResult, settings: Settings, now: datetime | None = None,
                  host: str | None = None) -> str:
    """Plain-text report. Never includes the applicant's document number or name."""
    now = now or datetime.now()
    host = host or socket.gethostname()
    lines = [f"{ICONS[result.outcome]} {result.outcome}"]
    if result.outcome is Outcome.APPOINTMENTS_FOUND:
        lines.append(f"Book now: {PORTAL_URL}")
    elif result.outcome is Outcome.FLOW_CHANGED:
        lines.append("Unrecognized page — check the debug snapshot.")
    lines += [
        "",
        f"{settings.province} / {settings.procedure}",
        f"Step: {result.step or '-'}",
        f"Host: {host}",
        f"Time: {now:%Y-%m-%d %H:%M:%S}",
    ]
    detail = " ".join(result.detail.split())
    if detail and result.outcome is not Outcome.NO_APPOINTMENTS:
        if len(detail) > MAX_DETAIL:
            detail = detail[:MAX_DETAIL] + "…"
        lines += ["", detail]
    return "\n".join(lines)


def load_chats(path: str | Path) -> dict[str, dict]:
    """Registered chats as {chat_id: {"username": ...}}; empty if the file is missing."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_chats(path: str | Path, chats: dict[str, dict]) -> None:
    Path(path).write_text(json.dumps(chats, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def telegram_call(token: str, method: str, payload: dict) -> dict | None:
    """Call a Bot API method. Never raises; returns the `result` or None on failure.

    Network errors, rate limits (429) and Telegram server errors (5xx) are retried;
    other rejections (e.g. "chat not found") are not, since retrying can't fix them.
    """
    for attempt, wait in enumerate((*RETRY_WAITS, None), start=1):
        try:
            response = httpx.post(f"{TELEGRAM_API}/bot{token}/{method}", json=payload,
                                  timeout=15)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # The exception text can contain the request URL, which includes the token.
            problem = type(exc).__name__
        else:
            if data.get("ok"):
                return data["result"]
            problem = data.get("description")
            if response.status_code != 429 and response.status_code < 500:
                LOGGER.warning("Telegram %s rejected: %s", method, problem)
                return None
            retry_after = (data.get("parameters") or {}).get("retry_after")
            if wait is not None and retry_after:
                wait = min(float(retry_after), MAX_RETRY_WAIT)
        if wait is None:
            LOGGER.warning("Telegram %s failed after %d attempts: %s", method, attempt, problem)
            return None
        LOGGER.info("Telegram %s attempt %d failed (%s); retrying in %.0f s",
                    method, attempt, problem, wait)
        time.sleep(wait)
    return None


def send_report(result: RunResult, settings: Settings) -> int:
    """Post the report to every registered chat. Never raises; returns how many got it."""
    chats = load_chats(settings.telegram_chats_file)
    if settings.telegram_bot_token is None or not chats:
        LOGGER.info("Telegram not configured or no registered chats; skipping report")
        return 0
    token = settings.telegram_bot_token.get_secret_value()
    text = format_report(result, settings)
    sent = 0
    for chat_id in chats:
        if telegram_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": result.outcome not in LOUD,
            "disable_web_page_preview": True,
        }) is not None:
            sent += 1
    LOGGER.info("Telegram report sent to %d/%d chats", sent, len(chats))
    return sent
