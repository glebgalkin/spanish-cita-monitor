"""Runtime settings, read from environment variables or a local `.env` file."""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class DocumentType(StrEnum):
    NIE = "NIE"
    DNI = "DNI"
    PASAPORTE = "PASAPORTE"


class Settings(BaseSettings):
    """All values can be overridden with `CITA_<NAME>` environment variables."""

    model_config = SettingsConfigDict(env_prefix="CITA_", env_file=".env", extra="ignore")

    # Applicant details (required, keep them in `.env` — never commit them).
    document_type: DocumentType = DocumentType.NIE
    document_number: str
    full_name: str

    # Which appointment to look for.
    province: str = "Alicante"
    office: str = "CNP Comisaría Provincial, C/ Isabel la Católica, 25, Alicante"
    procedure: str = "POLICIA-CARTA DE INVITACIÓN"

    # Browser behaviour.
    headless: bool = False
    # Pause between steps, in seconds. Firing requests back-to-back gets the
    # session rejected by the portal's bot protection.
    step_delay_min: float = 4.0
    step_delay_max: float = 8.0
    # Where screenshots/HTML of unexpected pages are saved for debugging.
    debug_dir: str = "debug"
