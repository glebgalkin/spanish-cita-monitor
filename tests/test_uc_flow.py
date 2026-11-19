from cita_monitor.outcome import Outcome
from cita_monitor.uc_flow import classify_page, classify_result


def test_blocked_page():
    assert classify_page("The requested URL was rejected", "") is Outcome.BLOCKED


def test_portal_error():
    assert classify_page("Se ha producido un error en el sistema", "") is Outcome.PORTAL_ERROR


def test_no_appointments():
    assert classify_result("En este momento no hay citas disponibles") is Outcome.NO_APPOINTMENTS


def test_unknown_page_is_not_positive():
    assert classify_result("Solicitar Cita") is Outcome.FLOW_CHANGED
