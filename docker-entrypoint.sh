#!/bin/sh
# Hosting platforms often mount the data volume owned by root. Fix ownership
# as root, then drop to the unprivileged app user before starting the server.
set -e

if [ "$(id -u)" = "0" ]; then
    data_dir="$(dirname "${DATABASE_PATH:-/data/app.db}")"
    mkdir -p "$data_dir"
    chown -R app:app "$data_dir"
    exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
