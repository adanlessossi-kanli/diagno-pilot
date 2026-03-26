#!/usr/bin/env bash
# stop.sh — Stop Diagno-Pilot locally

set -euo pipefail

echo "Stopping Diagno-Pilot..."

# Capture output and exit code from docker compose
COMPOSE_OUTPUT=$(docker compose down 2>&1)
COMPOSE_EXIT=$?

if [ $COMPOSE_EXIT -ne 0 ]; then
  echo ""
  echo "ERROR: docker compose down failed (exit code $COMPOSE_EXIT)."
  echo ""
  echo "$COMPOSE_OUTPUT"
  echo ""
  # Identify any containers still running
  RUNNING_SERVICES=$(docker compose ps --status running --format "{{.Service}}" 2>/dev/null || true)
  if [ -n "$RUNNING_SERVICES" ]; then
    echo "Service(s) still running:"
    echo "$RUNNING_SERVICES" | while read -r svc; do
      echo "  - $svc"
    done
    echo ""
    echo "Run 'docker compose logs <service>' for details."
  fi
  exit 1
fi

echo "All services stopped."
