#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER=${REMOTE_USER:-flubpub}
REMOTE_HOST=${REMOTE_HOST:?REMOTE_HOST must be set}
REMOTE_DIR=${REMOTE_DIR:-/opt/flubpub}

# Build the Python package
echo "Building package..."
uv build

# Ensure remote directories exist
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}/{dist,site,deploy}"

# Sync to remote, preserving directory structure
echo "Syncing files to remote..."
rsync -av --exclude node_modules --exclude _site --exclude __pycache__ --exclude .venv \
    dist/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dist/"
rsync -av --exclude node_modules --exclude _site --exclude __pycache__ \
    site/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/site/"
rsync -av deploy/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/deploy/"

# Run remote setup
echo "Running remote setup..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash <<DEPLOY
set -euo pipefail

# Create service user if not already present
id flubpub &>/dev/null || useradd --system --no-create-home flubpub

mkdir -p ${REMOTE_DIR}/data ${REMOTE_DIR}/site/src/pages

# Set up virtualenv and install the wheel
python3 -m venv ${REMOTE_DIR}/.venv
${REMOTE_DIR}/.venv/bin/pip install --quiet --force-reinstall ${REMOTE_DIR}/dist/*.whl

# Build the 11ty static site on the server
cd ${REMOTE_DIR}/site
npm ci
npx @11ty/eleventy

# Fix ownership so the service user can write data and rebuild the site
chown -R flubpub:flubpub ${REMOTE_DIR}

# Install and enable the systemd service
cp ${REMOTE_DIR}/deploy/flubpub.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now flubpub
DEPLOY

echo "Deployed successfully."
