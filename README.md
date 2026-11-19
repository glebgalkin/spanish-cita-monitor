# Spanish Cita Monitor

Checks Spain's immigration appointment portal (cita previa extranjería) for
free appointments and reports one clear outcome per run.

Default search: **Alicante → CNP Comisaría Provincial, C/ Isabel la Católica, 25 →
POLICIA-CARTA DE INVITACIÓN**, presented *sin Cl@ve*.

It only **checks** availability; it never books. Telegram notifications are
planned but not implemented yet.

## Setup

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync
uv run playwright install chromium
cp .env.example .env   # then fill in your document number and full name
uv run cita-monitor
```

`.env` holds personal data and is gitignored — never commit it.

## What a run does

1. Opens `https://icp.administracionelectronica.gob.es/icpco/index` and picks the province.
2. Picks the office (this reloads the page via `/icpco/selectSede`) and the procedure.
3. Clicks **Presentación sin Cl@ve**.
4. Fills document type, document number and *Nombre y apellidos*, then **Aceptar**.
5. Clicks **Solicitar Cita** and reads the result page.
6. Sends the outcome to every registered Telegram chat (see below).

It pauses a random 4–8 s between steps (`CITA_STEP_DELAY_MIN/MAX`).

## Telegram reports

1. Set `CITA_TELEGRAM_BOT_TOKEN` and `CITA_TELEGRAM_ALLOWED_USERNAMES` (comma-separated,
   without `@`) in `.env`.
2. Each recipient opens the bot in Telegram and sends `/start`.
3. Run `uv run cita-register`. Allowlisted users are saved to the gitignored
   `telegram_chats.json` and get a confirmation message; anyone else is logged and ignored.

Every run then reports to all registered chats. `APPOINTMENTS_FOUND` and `FLOW_CHANGED`
notify with sound; other outcomes arrive silently. Reports never include the applicant's
document number or name. Copy `telegram_chats.json` along with `.env` when deploying.

## Outcomes

Each run logs `OUTCOME=...` and exits with a matching code:

| Outcome | Exit | Meaning |
|---|---|---|
| `NO_APPOINTMENTS` | 0 | Reached the result page; "no hay citas disponibles" |
| `APPOINTMENTS_FOUND` | 10 | Reached the result page and it did not say "no hay citas" |
| `BLOCKED` | 20 | Bot-protection rejection ("The requested URL was rejected") or blank challenge page |
| `PORTAL_ERROR` | 21 | Portal's own "Se ha producido un error en el sistema" page |
| `UNAVAILABLE` | 22 | Timeout / site down |
| `FLOW_CHANGED` | 30 | An expected dropdown/button was missing — markup may have changed |

Anything other than `NO_APPOINTMENTS` saves a screenshot and HTML to `debug/`.

## Portal notes (verified 2026-11-19)

- `/icpco/acInfo` cannot be opened directly; it returns the generic error page.
- Province: `select#form` (label *PROVINCIAS DISPONIBLES*). Alicante → `/icpco/citar?p=3`.
- Office: `select#sede` (Comisaría Provincial = value `13`). Changing it submits
  the form; afterwards the procedure list is re-rendered as `tramiteGrupo[0]`
  (CARTA DE INVITACIÓN = value `4037`).
- *sin Cl@ve*: `#btnEntrar`.
- Applicant form (`/icpco/acEntrada`): `#rdbTipoDocNie|Dni|Pas`, `#txtIdCitado`,
  `#txtDesCitado`, submit `#btnEnviar`.
- **Not yet confirmed:** the *Solicitar Cita* page and the result page. The
  availability check currently treats any result page without "no hay citas
  disponibles" as `APPOINTMENTS_FOUND`.
- The info page states this procedure at this office is only for people
  *empadronados* in Alicante capital / the Comisaría Provincial area.

### Bot protection

The site is behind F5 bot protection (`/TSPD/` scripts). Automated runs are
frequently rejected at a random step, more so after many runs in a short time.
This project does **not** try to evade or bypass it — a rejection is reported as
`BLOCKED`. Keep the run frequency low (every 30–60 minutes or less).

## Development

```bash
uv run pytest
uv run ruff check .
```

## Project layout

```text
src/cita_monitor/
  config.py    Settings from env / .env (CITA_* variables)
  flow.py      Portal walk-through and page classification
  outcome.py   Outcome enum and exit codes
  main.py      CLI entry point (`cita-monitor`)
  notify.py    Telegram report formatting and sending
  register.py  Registers Telegram chats that sent /start (`cita-register`)
tests/         Unit tests
```
