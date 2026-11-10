#!/bin/sh
# Write files as the owner of the mounted ./EXPORTS folder (so they are not root-owned on Linux hosts).
set -e
U=$(stat -c %u /exports 2>/dev/null || echo 0)
G=$(stat -c %g /exports 2>/dev/null || echo 0)
if [ "$(id -u)" = "0" ] && [ "$U" != "0" ]; then
  exec setpriv --reuid="$U" --regid="$G" --clear-groups "$@"
fi
exec "$@"
