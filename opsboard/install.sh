#!/usr/bin/env bash
# opsboard installer. Idempotent. Usage: sudo bash install.sh   (Ubuntu 22.04 / 24.04)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST=/opt/opsboard
ETC=/etc/opsboard
PORT="${PORT:-8080}"

echo "[1/6] packages"
if ! command -v python3 >/dev/null || ! python3 -c 'import venv' 2>/dev/null; then
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
fi
python3 -c 'import ensurepip' 2>/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv >/dev/null; }

echo "[2/6] user"
id board >/dev/null 2>&1 || useradd --system --home-dir "$DEST" --shell /usr/sbin/nologin board

echo "[3/6] copy to $DEST"
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  for f in relay web requirements.txt config.example.yaml README.md install.sh opsboard.service; do
    rm -rf "$DEST/$f"; cp -r "$SRC/$f" "$DEST/$f"
  done
fi
find "$DEST" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

echo "[4/6] venv + pip"
[ -x "$DEST/venv/bin/python" ] || python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --quiet --upgrade pip
"$DEST/venv/bin/pip" install --quiet -r "$DEST/requirements.txt"
chown -R board:board "$DEST"

echo "[5/6] config in $ETC"
mkdir -p "$ETC"
[ -f "$ETC/config.yaml" ] || cp "$DEST/config.example.yaml" "$ETC/config.yaml"
if [ ! -f "$ETC/env" ] || ! grep -q '^BOARD_TOKEN=' "$ETC/env"; then
  TOKEN="$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 32)"
  { echo "# environment for opsboard relay; referenced from config.yaml as \${VAR}"; echo "BOARD_TOKEN=$TOKEN"; \
    echo "#BI_USER="; echo "#BI_PASS="; echo "#SHELLY_AUTH_KEY="; echo "#CF_ACCESS_CLIENT_ID="; echo "#CF_ACCESS_CLIENT_SECRET="; } >> "$ETC/env"
fi
chown -R root:board "$ETC"; chmod 750 "$ETC"; chmod 640 "$ETC/env" "$ETC/config.yaml"
grep -q '^port:' "$ETC/config.yaml" || echo "port: $PORT" >> "$ETC/config.yaml"

echo "[6/6] systemd"
cp "$DEST/opsboard.service" /etc/systemd/system/opsboard.service
systemctl daemon-reload
systemctl enable opsboard.service >/dev/null 2>&1
systemctl restart opsboard.service
sleep 1
systemctl --no-pager --lines=0 status opsboard.service | head -3 || true

TOKEN="$(grep '^BOARD_TOKEN=' "$ETC/env" | cut -d= -f2-)"
PORT_CFG="$(grep -E '^port:' "$ETC/config.yaml" | awk '{print $2}' | head -1)"; PORT_CFG="${PORT_CFG:-$PORT}"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "========================================================"
echo " opsboard installed."
echo "  Board URL (open once on the iPad, token is then stored):"
echo "    http://${IP:-<this-host>}:${PORT_CFG}/?token=${TOKEN}"
echo "  Token:   $TOKEN      (in $ETC/env)"
echo "  Config:  $ETC/config.yaml   then: sudo systemctl restart opsboard"
echo "  Logs:    journalctl -u opsboard -f"
echo "  Demo:    sudo -u board $DEST/venv/bin/python -m relay --demo --config $ETC/config.yaml"
echo "========================================================"
