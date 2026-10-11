#!/bin/sh
# Install or update the ambient synth on the Pi (piano-recorder's control
# unit). Runs there, from the deployed tree (tools/deploy puts it at
# ~/ambient-room). Safe to run again.
set -eu
app=$(cd "$(dirname "$0")/.." && pwd)

sudo apt-get install -y -q --no-install-recommends alsa-utils csound python3-csound python3-numpy python3-venv >/dev/null

[ -d "$app/.venv" ] || python3 -m venv --system-site-packages "$app/.venv"
"$app/.venv/bin/pip" install -q -r "$app/requirements.txt"

# The config is installed once; later edits on the Pi are kept.
if [ ! -f /etc/ambient-room.toml ]; then
    sudo install -m 644 "$app/config/pi.toml" /etc/ambient-room.toml
    echo "installed /etc/ambient-room.toml"
fi

# The unit names the user and the tree: fill them in for this install.
unit=$(mktemp)
trap 'rm -f "$unit"' EXIT
sed -e "s|@USER@|$(id -un)|g" -e "s|@APP@|$app|g" "$app/setup/ambient-room.service" >"$unit"
sudo install -m 644 "$unit" /etc/systemd/system/ambient-room.service
sudo systemctl daemon-reload
sudo systemctl enable -q ambient-room
sudo systemctl restart ambient-room

port=$(PYTHONPATH="$app" "$app/.venv/bin/python" -c 'from ambient.config import load_config; print(load_config().web_port)')
state="NOT answering on port $port (journalctl -u ambient-room)"
for i in $(seq 1 20); do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/api/status', timeout=2)" 2>/dev/null; then
        state="answering on port $port"
        break
    fi
    sleep 1
done
echo "ambient-room: $app, service $state"
