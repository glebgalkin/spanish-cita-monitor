from datetime import datetime

import httpx
import pytest

from cita_monitor import notify
from cita_monitor.config import Settings
from cita_monitor.notify import format_report, save_chats, send_report
from cita_monitor.outcome import Outcome, RunResult

NOW = datetime(2026, 11, 19, 20, 59, 15)


@pytest.fixture
def settings(tmp_path) -> Settings:
    chats_file = tmp_path / "chats.json"
    save_chats(chats_file, {"42": {"username": "alice"}})
    return Settings(_env_file=None, document_number="X1234567T", full_name="SECRET NAME",
                    telegram_bot_token="123:abc", telegram_chats_file=str(chats_file),
                    telegram_allowed_usernames="alice")


def test_report_never_contains_applicant_data(settings: Settings) -> None:
    for outcome in Outcome:
        text = format_report(RunResult(outcome, "detail", "result"), settings, NOW, "box")
        assert "X1234567T" not in text
        assert "SECRET NAME" not in text


def test_found_report_links_to_portal(settings: Settings) -> None:
    text = format_report(RunResult(Outcome.APPOINTMENTS_FOUND, "x", "result"), settings, NOW, "a")
    assert text.startswith("🟢 APPOINTMENTS_FOUND")
    assert notify.PORTAL_URL in text


def test_long_detail_is_truncated(settings: Settings) -> None:
    text = format_report(RunResult(Outcome.FLOW_CHANGED, "y" * 1000, "result"), settings, NOW, "a")
    assert "y" * notify.MAX_DETAIL + "…" in text
    assert "y" * (notify.MAX_DETAIL + 1) not in text


def test_skips_when_no_chats_registered(settings: Settings, tmp_path) -> None:
    settings.telegram_chats_file = str(tmp_path / "missing.json")
    assert send_report(RunResult(Outcome.NO_APPOINTMENTS, "", "result"), settings) == 0


@pytest.mark.parametrize(("outcome", "silent"), [
    (Outcome.NO_APPOINTMENTS, True),
    (Outcome.BLOCKED, True),
    (Outcome.APPOINTMENTS_FOUND, False),
    (Outcome.FLOW_CHANGED, False),
])
def test_sends_with_expected_loudness(settings: Settings, monkeypatch: pytest.MonkeyPatch,
                                      outcome: Outcome, silent: bool) -> None:
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return httpx.Response(200, json={"ok": True, "result": {}})

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    assert send_report(RunResult(outcome, "d", "result"), settings) == 1
    url, body = calls[0]
    assert url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert body["chat_id"] == "42"
    assert body["disable_notification"] is silent


def test_network_error_does_not_raise_or_log_token(settings: Settings,
                                                   monkeypatch: pytest.MonkeyPatch,
                                                   caplog: pytest.LogCaptureFixture,
                                                   no_sleep: list[float]) -> None:
    def boom(url, json, timeout):
        raise httpx.ConnectError(f"failed to reach {url}")

    monkeypatch.setattr(notify.httpx, "post", boom)
    assert send_report(RunResult(Outcome.BLOCKED, "", "province"), settings) == 0
    assert "123:abc" not in caplog.text


def test_telegram_rejection_returns_false(settings: Settings,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notify.httpx, "post", lambda url, json, timeout: httpx.Response(
        400, json={"ok": False, "description": "Bad Request: chat not found"}))
    assert send_report(RunResult(Outcome.BLOCKED, "", "province"), settings) == 0


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr(notify.time, "sleep", waits.append)
    return waits


def test_retries_network_errors_then_succeeds(settings: Settings, monkeypatch: pytest.MonkeyPatch,
                                              no_sleep: list[float]) -> None:
    responses = iter([httpx.ConnectError("down"), httpx.ConnectError("down"),
                      httpx.Response(200, json={"ok": True, "result": {}})])

    def flaky_post(url, json, timeout):
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(notify.httpx, "post", flaky_post)
    assert send_report(RunResult(Outcome.APPOINTMENTS_FOUND, "", "result"), settings) == 1
    assert no_sleep == list(notify.RETRY_WAITS)


def test_gives_up_after_all_attempts(settings: Settings, monkeypatch: pytest.MonkeyPatch,
                                     no_sleep: list[float]) -> None:
    calls = []

    def down(url, json, timeout):
        calls.append(url)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(notify.httpx, "post", down)
    assert send_report(RunResult(Outcome.BLOCKED, "", "province"), settings) == 0
    assert len(calls) == len(notify.RETRY_WAITS) + 1


def test_does_not_retry_permanent_rejection(settings: Settings, monkeypatch: pytest.MonkeyPatch,
                                            no_sleep: list[float]) -> None:
    calls = []

    def rejected(url, json, timeout):
        calls.append(url)
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    monkeypatch.setattr(notify.httpx, "post", rejected)
    assert send_report(RunResult(Outcome.BLOCKED, "", "province"), settings) == 0
    assert len(calls) == 1
    assert no_sleep == []


def test_rate_limit_uses_retry_after(settings: Settings, monkeypatch: pytest.MonkeyPatch,
                                     no_sleep: list[float]) -> None:
    responses = iter([
        httpx.Response(429, json={"ok": False, "description": "Too Many Requests",
                                  "parameters": {"retry_after": 7}}),
        httpx.Response(200, json={"ok": True, "result": {}}),
    ])
    monkeypatch.setattr(notify.httpx, "post", lambda url, json, timeout: next(responses))
    assert send_report(RunResult(Outcome.BLOCKED, "", "province"), settings) == 1
    assert no_sleep == [7.0]
