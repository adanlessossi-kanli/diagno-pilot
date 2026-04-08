#!/usr/bin/env bash
# start.sh — Start Diagno-Pilot locally

set -euo pipefail

# Load .env if present
if [ -f .env ]; then
  set -a
  # shellcheck source=.env
  source .env
  set +a
fi

echo "Starting Diagno-Pilot..."

COMPOSE_OUTPUT=$(docker compose up --build -d 2>&1)
COMPOSE_EXIT=$?

if [ $COMPOSE_EXIT -ne 0 ]; then
  echo ""
  echo "ERROR: docker compose up failed (exit code $COMPOSE_EXIT)."
  echo ""
  echo "$COMPOSE_OUTPUT"
  echo ""
  FAILED_SERVICES=$(docker compose ps --status exited --format "{{.Service}}" 2>/dev/null || true)
  if [ -n "$FAILED_SERVICES" ]; then
    echo "Checking for failed services..."
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
echo "  Model LLM  → http://localhost:8080"
echo "  MongoDB    → mongodb://localhost:27017"
echo "  LocalStack → http://localhost:4566"
echo ""
echo "Run 'docker compose logs -f' to follow logs."
