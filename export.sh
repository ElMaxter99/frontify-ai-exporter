#!/usr/bin/env bash
# Frontify Exporter: one command, no UI. macOS / Linux (and Git Bash / WSL on Windows).
#   ./export.sh --url https://cliente.frontify.com --token <TOKEN> [--name CLIENTE_01] [--concurrency 4]
# Token: --token, or the FRONTIFY_TOKEN env var, or a .env file next to this script. URL: --url or FRONTIFY_URL.
# Builds the image, runs the export, writes to ./EXPORTS and removes the container when finished.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && { set -a; . ./.env; set +a; }
URL="${FRONTIFY_URL:-}"; TOKEN="${FRONTIFY_TOKEN:-}"; NAME=""; CONC=4
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="${2:?missing value for --url}"; shift 2;;
    --token) TOKEN="${2:?missing value for --token}"; shift 2;;
    --name) NAME="${2:?missing value for --name}"; shift 2;;
    --concurrency) CONC="${2:?missing value for --concurrency}"; shift 2;;
    -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "Unknown option: $1 (use --help)" >&2; exit 2;;
  esac
done
[ -n "$URL" ] || { echo "Missing Frontify URL (--url or FRONTIFY_URL)" >&2; exit 2; }
[ -n "$TOKEN" ] || { echo "Missing token (--token or FRONTIFY_TOKEN)" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "Docker is not installed: https://docs.docker.com/get-docker/" >&2; exit 3; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Start Docker Desktop/daemon and retry." >&2; exit 3; }

mkdir -p EXPORTS
ARGS=(python -m src export --url "$URL" --dest /exports --concurrency "$CONC")
[ -n "$NAME" ] && ARGS+=(--name "$NAME")

# The token goes through the environment (not the command line, so it is not visible in `ps`).
export FRONTIFY_TOKEN="$TOKEN"
set +e
docker compose run --rm --build -e FRONTIFY_TOKEN frontify-exporter "${ARGS[@]}"
RC=$?
set -e
docker compose down --remove-orphans >/dev/null 2>&1 || true
echo
echo "Results: $(pwd)/EXPORTS   (report: EXPORT_REPORT.json inside the client folder)"
[ $RC -eq 0 ] && echo "Finished without errors." || echo "Finished with errors or failures (exit $RC). See EXPORT_REPORT.json."
exit $RC
