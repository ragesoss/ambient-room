#!/bin/sh
# Install or update the Ugly Duckling String Band on the control unit. Runs there, from the deployed tree
# (tools/deploy-ud puts it at ~/ugly-duckling). Safe to run again. It restarts only its own service.
set -eu
app=$(cd "$(dirname "$0")/.." && pwd)

sudo apt-get install -y -q --no-install-recommends alsa-utils libfluidsynth3 python3-numpy python3-venv >/dev/null

[ -d "$app/.venv" ] || /usr/bin/python3 -m venv --system-site-packages "$app/.venv"
"$app/.venv/bin/pip" install -q -r "$app/requirements-ud.txt" || \
    "$app/.venv/bin/pip" install -q -r "$app/requirements-band.txt"   # without vosk: no voice, the rest works

# The config is installed once; later edits here are kept.
if [ ! -f /etc/ugly-duckling.toml ]; then
    sudo install -m 644 "$app/config/ud-pi.toml" /etc/ugly-duckling.toml
    echo "installed /etc/ugly-duckling.toml"
fi
# Settings added since: put into a config installed before them (2026-10-17: the room mic, captured always).
if ! grep -q '^room *=' /etc/ugly-duckling.toml; then
    sudo sed -i 's|^loopback = \[10, 11\]$|&\n# The room mic (input 4), captured whichever input the band follows: the room delay, and the recording.\nroom = [3]|' \
        /etc/ugly-duckling.toml
    grep -q '^room *=' /etc/ugly-duckling.toml && echo "added room = [3] to /etc/ugly-duckling.toml"
fi

unit=$(mktemp)
trap 'rm -f "$unit"' EXIT
sed -e "s|@USER@|$(id -un)|g" -e "s|@APP@|$app|g" "$app/setup/ugly-duckling.service" >"$unit"
sudo install -m 644 "$unit" /etc/systemd/system/ugly-duckling.service
sudo systemctl daemon-reload
sudo systemctl enable -q ugly-duckling
sudo systemctl restart ugly-duckling

port=$(PYTHONPATH="$app" "$app/.venv/bin/python" -c 'from ugly_duckling.config import load_config; print(load_config().web_port)')
state="NOT answering on port $port (journalctl -u ugly-duckling)"
for i in $(seq 1 30); do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/api/status', timeout=2)" 2>/dev/null; then
        state="answering on port $port"
        break
    fi
    sleep 1
done
echo "ugly-duckling: $app, service $state"
