#!/usr/bin/env bash
#
# setup-tunnel.sh — stand up (or update) the flubpub reverse SSH tunnel.
#
# Runs on the HOME machine (WSL). Idempotent: re-running reconciles both ends to
# the configured values. Does two things:
#   1. LOCAL  — installs autossh, renders + installs the systemd unit, starts it.
#   2. REMOTE — drops a GatewayPorts sshd snippet on the VPS and reloads sshd,
#               so the forwarded port can bind 0.0.0.0.
#
# Reachability afterwards:  ssh -p $TUNNEL_PORT $LOCAL_USER@$REMOTE_HOST
#
# Config via env (defaults match the dwm install):
#   TUNNEL_PORT     port on the VPS that forwards home         (default 47022)
#   REMOTE_HOST     VPS hostname                               (default danielwymark.com)
#   REMOTE_USER     ssh user on the VPS                        (default root)
#   LOCAL_USER      home login the tunnel exposes / runs as    (default $USER)
#   LOCAL_SSH_PORT  home sshd port                             (default 22)
#
# Teardown: pass  --down  to stop+disable the local unit and remove the VPS
# snippet (leaves autossh installed).
set -euo pipefail

TUNNEL_PORT="${TUNNEL_PORT:-47022}"
REMOTE_HOST="${REMOTE_HOST:-danielwymark.com}"
REMOTE_USER="${REMOTE_USER:-root}"
LOCAL_USER="${LOCAL_USER:-$USER}"
LOCAL_SSH_PORT="${LOCAL_SSH_PORT:-22}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="flubpub-tunnel.service"
UNIT_DEST="/etc/systemd/system/${UNIT_NAME}"
REMOTE_SNIPPET="/etc/ssh/sshd_config.d/40-flubpub-tunnel.conf"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

teardown() {
  say "Tearing down local unit"
  sudo systemctl disable --now "$UNIT_NAME" 2>/dev/null || true
  sudo rm -f "$UNIT_DEST"
  sudo systemctl daemon-reload
  say "Removing VPS sshd snippet"
  ssh "${REMOTE_USER}@${REMOTE_HOST}" \
    "rm -f '$REMOTE_SNIPPET' && sshd -t && systemctl reload ssh" || true
  say "Down. (autossh left installed; VPS firewall untouched.)"
}

if [[ "${1:-}" == "--down" ]]; then teardown; exit 0; fi

# --- 1. LOCAL: autossh -------------------------------------------------------
if ! command -v autossh >/dev/null 2>&1; then
  say "Installing autossh"
  sudo apt-get update -qq
  sudo apt-get install -y autossh
else
  say "autossh already installed"
fi

# --- 2. REMOTE: GatewayPorts snippet + reload sshd ---------------------------
say "Configuring VPS sshd (GatewayPorts clientspecified)"
scp -q "$HERE/sshd-tunnel.conf" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_SNIPPET}"
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash -euo pipefail <<EOF
chmod 644 '$REMOTE_SNIPPET'
sshd -t
systemctl reload ssh
# Open the port if ufw is active (no-op when inactive; DO cloud firewall, if
# any, must be opened out of band in the DO console).
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  ufw allow ${TUNNEL_PORT}/tcp
fi
echo "VPS sshd reloaded; GatewayPorts=\$(sshd -T | awk '/^gatewayports/{print \$2}')"
EOF

# --- 3. LOCAL: render + install systemd unit ---------------------------------
say "Installing systemd unit -> $UNIT_DEST"
tmp="$(mktemp)"
sed -e "s|__TUNNEL_PORT__|${TUNNEL_PORT}|g" \
    -e "s|__REMOTE_HOST__|${REMOTE_HOST}|g" \
    -e "s|__REMOTE_USER__|${REMOTE_USER}|g" \
    -e "s|__LOCAL_USER__|${LOCAL_USER}|g" \
    -e "s|__LOCAL_SSH_PORT__|${LOCAL_SSH_PORT}|g" \
    "$HERE/flubpub-tunnel.service.template" > "$tmp"
sudo install -m 644 "$tmp" "$UNIT_DEST"
rm -f "$tmp"

sudo systemctl daemon-reload
sudo systemctl enable --now "$UNIT_NAME"
sudo systemctl restart "$UNIT_NAME"   # pick up config changes on re-run

sleep 2
say "Local unit status:"
systemctl --no-pager --lines=0 status "$UNIT_NAME" || true
echo
say "Done. Reach home with:  ssh -p ${TUNNEL_PORT} ${LOCAL_USER}@${REMOTE_HOST}"
