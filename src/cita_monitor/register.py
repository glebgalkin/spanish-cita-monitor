"""Register Telegram users who sent /start to the bot, so they receive run reports."""

import logging

from pydantic import ValidationError

from cita_monitor.config import Settings
from cita_monitor.notify import load_chats, save_chats, telegram_call

LOGGER = logging.getLogger("cita_monitor.register")


def collect_starts(updates: list[dict]) -> list[dict]:
    """Private-chat /start messages, as [{"chat_id", "username"}], first occurrence only."""
    seen: dict[str, dict] = {}
    for update in updates:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private":
            continue
        if not (message.get("text") or "").startswith("/start"):
            continue
        chat_id = str(chat["id"])
        seen.setdefault(chat_id, {"chat_id": chat_id,
                                  "username": (message.get("from") or {}).get("username") or ""})
    return list(seen.values())


def register(settings: Settings) -> int:
    token = settings.telegram_bot_token.get_secret_value()
    updates = telegram_call(token, "getUpdates", {"allowed_updates": ["message"]})
    if updates is None:
        return 1

    allowed = settings.allowed_usernames
    chats = load_chats(settings.telegram_chats_file)
    for start in collect_starts(updates):
        chat_id, username = start["chat_id"], start["username"]
        if chat_id in chats:
            LOGGER.info("Already registered: @%s (%s)", username, chat_id)
        elif username.lower() in allowed:
            chats[chat_id] = {"username": username}
            telegram_call(token, "sendMessage", {
                "chat_id": chat_id, "text": "✅ Registered — you'll get cita monitor reports here."})
            LOGGER.info("Registered @%s (%s)", username, chat_id)
        else:
            LOGGER.warning("Ignored @%s (%s): not in CITA_TELEGRAM_ALLOWED_USERNAMES",
                           username or "<no username>", chat_id)
    save_chats(settings.telegram_chats_file, chats)

    if updates:  # Acknowledge, so the same messages aren't processed again.
        telegram_call(token, "getUpdates", {"offset": updates[-1]["update_id"] + 1, "limit": 1})
    LOGGER.info("%d registered chat(s) in %s", len(chats), settings.telegram_chats_file)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        settings = Settings()
    except ValidationError as exc:
        LOGGER.error("Invalid configuration (see .env.example):\n%s", exc)
        raise SystemExit(2) from None
    if settings.telegram_bot_token is None:
        LOGGER.error("Set CITA_TELEGRAM_BOT_TOKEN in .env first")
        raise SystemExit(2)
    if not settings.allowed_usernames:
        LOGGER.error("Set CITA_TELEGRAM_ALLOWED_USERNAMES in .env first")
        raise SystemExit(2)
    raise SystemExit(register(settings))


if __name__ == "__main__":
    main()
