#!/bin/sh
# Render the nginx config, then hand off to supervisor.
#
# The Grid Hub address differs by platform and cannot be baked in:
#   App Service : sidecar containers share one network namespace and reach each
#                 other on 127.0.0.1 — a service name like "chrome" does not
#                 resolve, so nginx would fail to start with
#                 "host not found in upstream".
#   Compose/K8s : the service/DNS name is correct.
set -e

: "${GRID_UPSTREAM:=127.0.0.1:4444}"
export GRID_UPSTREAM

# Only GRID_UPSTREAM is substituted — nginx's own $host / $http_upgrade
# variables must survive verbatim.
envsubst '${GRID_UPSTREAM}' \
    < /etc/nginx/nginx.conf.template \
    > /etc/nginx/sites-available/default

echo "[entrypoint] nginx -> Grid Hub at ${GRID_UPSTREAM}"
echo "[entrypoint] app   -> SELENIUM_REMOTE_URL=${SELENIUM_REMOTE_URL:-<unset>}"

nginx -t

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
