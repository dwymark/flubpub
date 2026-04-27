#!/usr/bin/env bash
# Deploy a flubpub install for a single site. The install is fully
# self-contained at /opt/flubpub-${SITE}/, served by systemd unit
# flubpub@${SITE} on port ${PORT}, fronted by nginx site flubpub-${SITE}.
#
# Required env vars:
#   SITE         short identifier (e.g. dwm, bj). Used in install path,
#                systemd instance, and nginx site filename.
#   REMOTE_HOST  target VPS hostname or IP.
#   SERVER_NAME  the public hostname nginx should match (e.g. example.com).
#   PORT         a free TCP port for the FastAPI server (e.g. 8001).
#
# Optional:
#   REMOTE_USER  defaults to root.
#
# Idempotent: re-running against an existing install rebuilds and restarts.
set -euo pipefail

SITE=${SITE:?SITE must be set (e.g. dwm, bj)}
REMOTE_HOST=${REMOTE_HOST:?REMOTE_HOST must be set}
SERVER_NAME=${SERVER_NAME:?SERVER_NAME must be set (the host nginx will match)}
PORT=${PORT:?PORT must be set (a free TCP port for this install)}
REMOTE_USER=${REMOTE_USER:-root}
REMOTE_DIR=${REMOTE_DIR:-/opt/flubpub-${SITE}}
# Override for testing; production never sets this.
ETC=${ETC:-/etc}

echo "Deploying site '${SITE}'"
echo "  remote:   ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
echo "  hostname: ${SERVER_NAME}"
echo "  port:     ${PORT}"

echo "Building package..."
uv build

ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}/{dist,site,deploy}"

echo "Syncing files to remote..."
rsync -av --exclude node_modules --exclude _site --exclude __pycache__ --exclude .venv \
    dist/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dist/"
rsync -av --exclude node_modules --exclude _site --exclude __pycache__ \
    site/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/site/"
rsync -av deploy/ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/deploy/"

echo "Running remote setup..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash <<DEPLOY
set -euo pipefail

# Install uv if not present
if ! command -v uv &>/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="\$HOME/.local/bin:\$PATH"
fi

mkdir -p "${REMOTE_DIR}/data" "${REMOTE_DIR}/site/src/pages"

# Per-instance environment file consumed by the templated systemd unit.
cat > "${REMOTE_DIR}/instance.env" <<EOF
FLUBPUB_DATA_DIR=${REMOTE_DIR}/data
FLUBPUB_SITE_DIR=${REMOTE_DIR}/site
FLUBPUB_PORT=${PORT}
EOF

# Set up venv and install the wheel
uv venv --clear "${REMOTE_DIR}/.venv"
uv pip install --quiet --force-reinstall \
    --python "${REMOTE_DIR}/.venv/bin/python" \
    "${REMOTE_DIR}"/dist/*.whl

# Build the 11ty static site
cd "${REMOTE_DIR}/site"
npm ci
npx @11ty/eleventy
cd -

# Install the templated systemd unit (one shared file across all instances)
# and enable this site's instance.
cp "${REMOTE_DIR}/deploy/flubpub@.service" ${ETC}/systemd/system/
systemctl daemon-reload
systemctl enable "flubpub@${SITE}"
systemctl restart "flubpub@${SITE}"

# Render this site's nginx config from the template and (re)enable it.
sed -e "s|__SERVER_NAME__|${SERVER_NAME}|g" \
    -e "s|__INSTALL_ROOT__|${REMOTE_DIR}|g" \
    -e "s|__PORT__|${PORT}|g" \
    "${REMOTE_DIR}/deploy/nginx-site.conf.template" \
    > "${ETC}/nginx/sites-available/flubpub-${SITE}"
ln -sf "${ETC}/nginx/sites-available/flubpub-${SITE}" \
       "${ETC}/nginx/sites-enabled/flubpub-${SITE}"
nginx -t
systemctl reload nginx
DEPLOY

echo "Deployed site '${SITE}' successfully."
