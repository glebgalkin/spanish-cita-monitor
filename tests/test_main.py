from cita_monitor.main import URL


def test_portal_url_uses_https() -> None:
    assert URL.startswith("https://")
