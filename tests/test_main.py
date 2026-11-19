import pytest

from cita_monitor.config import DocumentType, Settings
from cita_monitor.flow import ENTRY_URL, classify_blocking_page, classify_result_page
from cita_monitor.outcome import EXIT_CODES, Outcome


def test_entry_url_is_https_index_page() -> None:
    assert ENTRY_URL.startswith("https://")
    assert ENTRY_URL.endswith("/icpco/index")


@pytest.mark.parametrize(
    ("body", "html", "expected"),
    [
        ("The requested URL was rejected. Please consult...", "", Outcome.BLOCKED),
        ("", '<script src="/TSPD/?type=18"></script>', Outcome.BLOCKED),
        ("Error Se ha producido un error en el sistema, por favor", "", Outcome.PORTAL_ERROR),
        ("CITA PREVIA EXTRANJERÍA Selecciona Oficina:", "<select id='sede'>", None),
    ],
)
def test_classify_blocking_page(body: str, html: str, expected: Outcome | None) -> None:
    assert classify_blocking_page(body, html) == expected


def test_classify_result_page_no_appointments() -> None:
    body = "En este momento no hay citas disponibles. Inténtelo más tarde."
    assert classify_result_page(body) is Outcome.NO_APPOINTMENTS


def test_every_outcome_has_a_distinct_exit_code() -> None:
    assert set(EXIT_CODES) == set(Outcome)
    assert len(set(EXIT_CODES.values())) == len(Outcome)
    assert Outcome.NO_APPOINTMENTS.exit_code == 0


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITA_DOCUMENT_TYPE", "PASAPORTE")
    monkeypatch.setenv("CITA_DOCUMENT_NUMBER", "X0000000T")
    monkeypatch.setenv("CITA_FULL_NAME", "TEST PERSON")
    settings = Settings(_env_file=None)
    assert settings.document_type is DocumentType.PASAPORTE
    assert settings.province == "Alicante"
    assert settings.procedure == "POLICIA-CARTA DE INVITACIÓN"


def test_start_delay_defaults_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CITA_START_DELAY_MIN", raising=False)
    monkeypatch.delenv("CITA_START_DELAY_MAX", raising=False)
    settings = Settings(_env_file=None, document_number="X", full_name="Y")
    assert settings.start_delay_min == 0
    assert settings.start_delay_max == 0
