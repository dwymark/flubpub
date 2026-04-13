#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER=${REMOTE_USER:-flubpub}
REMOTE_HOST=${REMOTE_HOST:?REMOTE_HOST must be set}
REMOTE_DIR=${REMOTE_DIR:-/opt/flubpub}

# Build the Python package
echo "Building package..."
uv build

# Sync build artifacts and config to remote
echo "Syncing files to remote..."
rsync -av dist/*.whl site/ deploy/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# Run remote setup
echo "Running remote setup..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash <<EOF
set -euo pipefail

# Create service user if not already present
id flubpub &>/dev/null || useradd --system flubpub

# Ensure data directory exists
mkdir -p ${REMOTE_DIR}/data

# Set up virtualenv and install the wheel
python3 -m venv ${REMOTE_DIR}/.venv
${REMOTE_DIR}/.venv/bin/pip install --quiet ${REMOTE_DIR}/dist/*.whl

# Build the 11ty static site
cd ${REMOTE_DIR}/site
npm ci
npm run build

# Install and enable the systemd service
cp ${REMOTE_DIR}/deploy/flubpub.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now flubpub
EOF

echo "Deployed successfully."
