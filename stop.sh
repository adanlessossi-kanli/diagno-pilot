#!/usr/bin/env bash
# stop.sh — Stop Diagno-Pilot locally

set -euo pipefail

echo "Stopping Diagno-Pilot..."

COMPOSE_OUTPUT=$(docker compose down 2>&1)
COMPOSE_EXIT=$?

if [ $COMPOSE_EXIT -ne 0 ]; then
  echo ""
  echo "ERROR: docker compose down failed (exit code $COMPOSE_EXIT)."
  echo ""
  echo "$COMPOSE_OUTPUT"
  exit 1
fi

echo "All services stopped."
