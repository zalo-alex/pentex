#!/bin/sh
set -e

# instance/ and logs/ are bind-mounted from the host by docker-compose, which
# creates them as root on first run — overriding the chown done at build time.
# Fix ownership here (as root, before dropping privileges) on every start.
mkdir -p /app/instance /app/logs
chown -R appuser:appuser /app/instance /app/logs

exec gosu appuser "$@"
