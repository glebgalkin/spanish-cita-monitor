import httpx
import pytest

from cita_monitor import notify
from cita_monitor.config import Settings
from cita_monitor.notify import load_chats
from cita_monitor.register import collect_starts, register


def start(update_id: int, chat_id: int, username: str, text: str = "/start",
          chat_type: str = "private") -> dict:
    return {"update_id": update_id, "message": {
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": chat_id, "username": username}, "text": text}}


def test_collect_starts_keeps_private_start_messages_once() -> None:
    updates = [start(1, 10, "alice"), start(2, 10, "alice"), start(3, 11, "bob", text="hi"),
               start(4, -5, "carol", chat_type="group"), {"update_id": 5}]
    assert collect_starts(updates) == [{"chat_id": "10", "username": "alice"}]


def test_register_only_allowlisted_users(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    chats_file = tmp_path / "chats.json"
    settings = Settings(_env_file=None, document_number="X", full_name="Y",
                        telegram_bot_token="123:abc", telegram_chats_file=str(chats_file),
                        telegram_allowed_usernames="@Alice")
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url.rsplit("/", 1)[-1], json))
        if url.endswith("getUpdates") and "offset" not in json:
            return httpx.Response(200, json={"ok": True, "result": [
                start(7, 10, "alice"), start(8, 11, "mallory")]})
        return httpx.Response(200, json={"ok": True, "result": []})

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    assert register(settings) == 0
    assert load_chats(chats_file) == {"10": {"username": "alice"}}
    assert ("sendMessage", "10") in [(m, p.get("chat_id")) for m, p in calls]
    assert calls[-1] == ("getUpdates", {"offset": 9, "limit": 1})
