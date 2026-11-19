# Spanish Cita Monitor

Checks Spain's immigration appointment portal for invitation-letter appointment availability.
Default: Alicante → CNP Comisaría Provincial → POLICIA-CARTA DE INVITACIÓN.

## Setup

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
# Fill in the applicant document number and name.
```

## Browser backends

The existing Playwright backend remains the default:

```bash
uv run cita-monitor
```

To experiment with the Selenium-compatible `undetected-chromedriver` backend:

```bash
uv run cita-monitor --browser uc
```

The experimental backend requires a locally installed Google Chrome. It uses the
standard WebDriver API to navigate the same workflow. No CAPTCHA solving,
fingerprint configuration, or access-control bypass logic is implemented.
If the portal rejects the session, it reports `BLOCKED` and stops.

The run does **not** book an appointment or send Telegram notifications.
Personal details belong in the gitignored `.env` file.

## Outcomes

| Outcome | Exit | Meaning |
|---|---|---|
| `NO_APPOINTMENTS` | 0 | Explicit no-availability text |
| `APPOINTMENTS_FOUND` | 10 | Positive signal (not yet validated in the UC backend) |
| `BLOCKED` | 20 | Portal access rejection |
| `PORTAL_ERROR` | 21 | Government portal error |
| `UNAVAILABLE` | 22 | Timeout or browser failure |
| `FLOW_CHANGED` | 30 | Missing selector or unrecognized result |

The UC backend intentionally returns `FLOW_CHANGED` for an unrecognized result,
not `APPOINTMENTS_FOUND`. Screenshots and HTML of unexpected pages are saved to
the gitignored `debug/` folder. Those files may contain applicant data: do not
share them publicly.

## Development

```bash
uv run pytest
uv run ruff check .
```

The experimental backend has not been verified against the live portal. Keep
checks infrequent and stop when access is rejected.
