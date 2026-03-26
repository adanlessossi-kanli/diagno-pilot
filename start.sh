#!/usr/bin/env bash
# start.sh — Start Diagno-Pilot locally

set -euo pipefail

# Load .env if present — set -a exports all variables automatically
if [ -f .env ]; then
  set -a
  # shellcheck source=.env
  source .env
  set +a
fi

echo "Starting Diagno-Pilot..."

# Capture output and exit code from docker compose
COMPOSE_OUTPUT=$(docker compose up --build -d 2>&1)
COMPOSE_EXIT=$?

if [ $COMPOSE_EXIT -ne 0 ]; then
  echo ""
  echo "ERROR: docker compose up failed (exit code $COMPOSE_EXIT)."
  echo ""
  echo "$COMPOSE_OUTPUT"
  echo ""
  # Identify which services are not running
  FAILED_SERVICES=$(docker compose ps --status exited --format "{{.Service}}" 2>/dev/null || true)
  if [ -n "$FAILED_SERVICES" ]; then
    echo "Failed service(s):"
    echo "$FAILED_SERVICES" | while read -r svc; do
      echo "  - $svc"
    done
    echo ""
    echo "Run 'docker compose logs <service>' for details."
  fi
  exit 1
fi

echo ""
echo "Services:"
echo "  Frontend   → http://localhost:3000"
echo "  Backend    → http://localhost:8000"
echo "  MongoDB    → mongodb://localhost:27017"
echo "  LocalStack → http://localhost:4566"
echo ""
echo "Run 'docker compose logs -f' to follow logs."
