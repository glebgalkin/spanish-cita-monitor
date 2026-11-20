# Deploying to a server

Verified on 2026-11-19 with a Google Cloud VM in Madrid (`europe-southwest1`, Ubuntu).

## Automatic setup

Create an Ubuntu VM in Spain, make sure you can `ssh USER@SERVER_IP` (step 2), then from
the project folder on the Mac:

```bash
./deploy/setup.sh USER@SERVER_IP MINUTE
```

`MINUTE` (0–59) is the minute of each hour the check runs. Give each server a different
one so they take turns, e.g. `30` for the first and `50` for the second.

It runs steps 1 and 3–6 below over SSH: checks the portal is reachable (stops if not),
installs everything, copies `.env` (without local `CITA_START_DELAY_*` overrides) and
`telegram_chats.json`, runs one test check, and installs the hourly cron job. Re-run it
to update a server. Options: `--no-test` skips the test check, `--force` continues even if
the portal looks unreachable. The SSH user needs passwordless `sudo` (the default on
Google Cloud) or must be `root`.

The manual steps below are what the script does.

## 1. Pick a server in Spain

The portal drops connections from outside Spain. A Linode in Germany timed out on the
first page; a Google Cloud VM in Madrid works. Other options with Spanish regions: Vultr
(Madrid), IONOS (Spain), Clouding.io (Barcelona). Use 2 GB of RAM or more for Chromium.

Before setting anything up, check the server can reach the portal:

```bash
curl -s https://ipinfo.io/country    # should print ES
curl -sS -o /dev/null -m 20 -w '%{http_code} %{time_total}s\n' \
  https://icp.administracionelectronica.gob.es/icpco/index
```

| Result | Meaning |
|---|---|
| `200` | Reachable. Go ahead. |
| `000` after ~20 s | The portal is dropping this IP. Use a different server. |
| `000` instantly, `SSL certificate problem` | Reachable. The portal sends an incomplete certificate chain that Linux `curl` rejects; Chromium handles it. See below. |

On Linux, `curl` will most likely print:

```text
curl: (60) SSL certificate problem: unable to get local issuer certificate
More details here: https://curl.se/docs/sslcerts.html
```

The portal leaves out the RapidSSL intermediate certificate. Fetch it (its URL is in the
portal's own certificate) and test again with it added; you should get `200`:

```bash
curl -s http://cacerts.rapidssl.com/RapidSSLTLSRSACAG1.crt | openssl x509 -inform der -out /tmp/rapidssl.pem
curl -sS -o /dev/null -m 20 -w '%{http_code}\n' \
  --cacert <(cat /etc/ssl/certs/ca-certificates.crt /tmp/rapidssl.pem) \
  https://icp.administracionelectronica.gob.es/icpco/index
```

This is safe over plain `http`: `curl` still checks that the intermediate is signed by
DigiCert, which the system already trusts. The bot itself needs no change.

## 2. Connect with SSH (Google Cloud)

1. Copy your public key on the Mac: `pbcopy < ~/.ssh/id_ed25519.pub`
2. In the console: instance → **Edit** → **SSH Keys** → **Add item** → paste → **Save**.
3. Connect with the username shown next to the key, then become root. Google derives it
   from the key's comment (your email before the `@`; it may keep the dot, e.g.
   `first.last`).

```bash
ssh USERNAME@SERVER_IP
sudo -i
```

No SSH key yet? The **SSH** button in the console opens a browser terminal instead.

Alternatively, add the key from a shell already on the server (e.g. the browser terminal).
On the Mac, print the key with `cat ~/.ssh/id_ed25519.pub`, then on the server, as your
normal user (not root):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo 'ssh-ed25519 AAAA...paste-your-key... you@example.com' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

For other providers with password login, `ssh-copy-id USERNAME@SERVER_IP` from the Mac
does the same.

## 3. Install

As root:

```bash
apt update && apt install -y git xvfb libatomic1
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env
git clone https://github.com/glebgalkin/spanish-cita-monitor.git && cd spanish-cita-monitor
uv sync --frozen && uv run playwright install --with-deps chromium
```

- `xvfb` gives Chromium a virtual screen, since the bot runs a normal (non-headless) browser.
- `libatomic1` is needed by Playwright's driver on minimal Ubuntu images.
- `playwright install --with-deps chromium` downloads Chromium and its system libraries.

## 4. Copy the secrets

`.env` (applicant data, bot token) and `telegram_chats.json` are not in git. From the
project folder on the Mac:

```bash
scp .env telegram_chats.json USERNAME@SERVER_IP:~
```

(In the browser terminal, use the **Upload file** button instead.) If your local `.env`
contains `CITA_START_DELAY_MAX=0`, remove that line on the server copy, or scheduled runs
won't wait before starting.

Then on the server, as root:

```bash
mv /home/USERNAME/.env /home/USERNAME/telegram_chats.json /root/spanish-cita-monitor/
chmod 600 /root/spanish-cita-monitor/.env /root/spanish-cita-monitor/telegram_chats.json
```

## 5. Run a check

```bash
cd ~/spanish-cita-monitor && CITA_START_DELAY_MAX=0 xvfb-run uv run cita-monitor
```

`CITA_START_DELAY_MAX=0` skips the default 1–5 minute wait for this manual run. Expect `OUTCOME=NO_APPOINTMENTS` (or another outcome) and `Telegram report sent to 1/1 chats`.

## 6. Schedule (cron, hourly)

As root. This **replaces** root's whole crontab with one job:

```bash
echo '50 * * * * cd /root/spanish-cita-monitor && xvfb-run -a /root/.local/bin/uv run cita-monitor >> /root/cita-monitor.log 2>&1' | crontab -
```

Every 15 minutes got the Madrid VM's IP blocked by the portal within a few hours, so
check at most hourly from a datacenter IP.

- Cron starts a run at minute 50 of every hour; the script then waits a random 1–5 minutes
  (default `CITA_START_DELAY_MIN/MAX`) before checking. Output goes to `/root/cita-monitor.log`.
- `uv` needs its full path because cron doesn't load `~/.local/bin` into `PATH`.
- Debug snapshots (they contain applicant data) accumulate in `debug/`; clear them now
  and then with `rm /root/spanish-cita-monitor/debug/*`.

Check with `crontab -l` and `tail -f /root/cita-monitor.log` (Ctrl+C stops watching, not
the job). By the next :50 you should see `Waiting N s before starting`, then a Telegram
report. Stop the schedule with `crontab -r` (removes all of root's cron jobs).

## Updating

As root:

```bash
cd ~/spanish-cita-monitor && git pull && uv sync --frozen
```

Cron picks up the new code on its next run; nothing needs restarting. Re-run `uv run playwright install --with-deps chromium` only if the Playwright version changed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `uv: command not found` right after installing | `source ~/.local/bin/env`, or log in again |
| `libatomic.so.1: cannot open shared object file` | `apt install -y libatomic1` |
| `git: command not found` | `apt install -y git` |
| Shell shows `>` after pasting a multi-line command | Indented paste broke it; Ctrl+C and use the one-line version |
| `Telegram ... failed after 3 attempts` | Network issue reaching Telegram; the check itself still ran (see `OUTCOME=`) |
| `OUTCOME=UNAVAILABLE ... Page.goto: Timeout` | The server can't reach the portal; check step 1 |
| `OUTCOME=BLOCKED` at step `province` | Firewall rejected the IP. Don't retry in a loop; wait a few hours |
