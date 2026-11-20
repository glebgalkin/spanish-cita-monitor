#!/usr/bin/env bash
# Set up (or update) the cita monitor on a fresh Ubuntu server, from your Mac.
#
#   ./deploy/setup.sh USER@SERVER_IP MINUTE [--no-test] [--force]
#
# Steps (see docs/DEPLOY.md): check the portal is reachable from the server, install
# packages/uv/Chromium, clone or update the repo, copy .env and telegram_chats.json,
# run one test check, install the hourly cron job. Safe to re-run for updates.
#
#   MINUTE     minute of each hour the check runs (0-59), e.g. 30 on one server and
#              50 on another so they take turns
#   --no-test  skip the test check (it is one real request to the portal)
#   --force    continue even if the portal looks unreachable from the server
set -euo pipefail

REPO_URL="https://github.com/glebgalkin/spanish-cita-monitor.git"
APP_DIR="/root/spanish-cita-monitor"
PORTAL_URL="https://icp.administracionelectronica.gob.es/icpco/index"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

TARGET="" MINUTE="" RUN_TEST=1 FORCE=0
for arg in "$@"; do
  case "$arg" in
    --no-test) RUN_TEST=0 ;;
    --force) FORCE=1 ;;
    -h|--help) usage ;;
    -*) echo "Unknown option: $arg" >&2; usage ;;
    *@*) TARGET="$arg" ;;
    *) MINUTE="$arg" ;;
  esac
done
[[ -n "$TARGET" ]] || usage
if ! [[ "$MINUTE" =~ ^[0-9]{1,2}$ ]] || (( 10#$MINUTE > 59 )); then
  echo "MINUTE must be a number from 0 to 59, got: '${MINUTE}'" >&2; usage
fi
MINUTE=$((10#$MINUTE))
CRON_LINE="$MINUTE * * * * cd $APP_DIR && xvfb-run -a /root/.local/bin/uv run cita-monitor >> /root/cita-monitor.log 2>&1"

cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo "No .env in $(pwd); copy .env.example and fill it in first." >&2; exit 1; }
[[ -f telegram_chats.json ]] || echo "Warning: no telegram_chats.json; the server won't send Telegram reports." >&2

SSH=(ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$TARGET")
step() { printf '\n==> %s\n' "$*"; }

step "Connecting to $TARGET"
"${SSH[@]}" 'echo "Connected: $(hostname), $(. /etc/os-release && echo "$PRETTY_NAME")"'

step "Checking the portal is reachable from the server"
# 200, or 000 with exit 60 (incomplete cert chain, see DEPLOY.md) = reachable.
# 000 with exit 28 (timeout) = the portal is dropping this IP.
"${SSH[@]}" "PORTAL_URL='$PORTAL_URL' FORCE=$FORCE bash -s" <<'REMOTE'
country=$(curl -s -m 10 https://ipinfo.io/country || true)
echo "Server country: ${country:-unknown}"
[ "$country" = "ES" ] || echo "Warning: server is not in Spain; the portal drops non-Spanish IPs."
code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$PORTAL_URL"); rc=$?
if [ "$rc" -eq 0 ] || [ "$rc" -eq 60 ]; then
  echo "Portal reachable (HTTP $code, curl exit $rc)."
else
  echo "Portal NOT reachable from this server (curl exit $rc)."
  [ "$FORCE" = 1 ] || { echo "Stopping. Re-run with --force to continue anyway."; exit 1; }
fi
REMOTE

step "Installing packages, uv and the app (a few minutes on a fresh server)"
"${SSH[@]}" "sudo -H env REPO_URL='$REPO_URL' APP_DIR='$APP_DIR' bash -s" <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl xvfb libatomic1 >/dev/null
echo "System packages installed."

if [ ! -x /root/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
UV=/root/.local/bin/uv
echo "uv: $($UV --version)"

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only -q
  echo "Repo updated: $(git -C "$APP_DIR" log --oneline -1)"
else
  git clone -q "$REPO_URL" "$APP_DIR"
  echo "Repo cloned: $(git -C "$APP_DIR" log --oneline -1)"
fi

cd "$APP_DIR"
$UV sync --frozen -q
$UV run playwright install --with-deps chromium >/dev/null
echo "Python dependencies and Chromium installed."
REMOTE

step "Copying secrets"
# CITA_START_DELAY_* is a local-only override (instant manual runs); the server keeps
# the default 1–5 minute random wait.
tmp_env=$(mktemp)
trap 'rm -f "$tmp_env"' EXIT
grep -v '^CITA_START_DELAY_' .env > "$tmp_env" || true
files=("$tmp_env")
[[ -f telegram_chats.json ]] && files+=(telegram_chats.json)
scp -q -o StrictHostKeyChecking=accept-new "${files[@]}" "$TARGET:/tmp/"
"${SSH[@]}" "sudo bash -s" <<REMOTE
set -euo pipefail
install -m 600 "/tmp/$(basename "$tmp_env")" "$APP_DIR/.env"
rm -f "/tmp/$(basename "$tmp_env")"
if [ -f /tmp/telegram_chats.json ]; then
  install -m 600 /tmp/telegram_chats.json "$APP_DIR/telegram_chats.json"
  rm -f /tmp/telegram_chats.json
fi
echo "Secrets installed (mode 600)."
REMOTE

if [[ $RUN_TEST == 1 ]]; then
  step "Running one test check (about a minute)"
  "${SSH[@]}" "sudo -H bash -c 'cd $APP_DIR && CITA_START_DELAY_MAX=0 xvfb-run -a /root/.local/bin/uv run cita-monitor 2>&1 | grep -E \"OUTCOME=|Telegram\" | cut -c1-200'" || true
fi

step "Installing the cron job (hourly at minute $MINUTE; replaces root's crontab)"
"${SSH[@]}" "echo '$CRON_LINE' | sudo crontab - && sudo crontab -l"

step "Done"
echo "Logs:  ssh $TARGET 'sudo tail -f /root/cita-monitor.log'"
echo "Stop:  ssh $TARGET 'sudo crontab -r'"
