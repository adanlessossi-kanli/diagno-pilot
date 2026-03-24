#!/usr/bin/env bash
# stop.sh — Stop Diagno-Pilot locally

echo "Stopping Diagno-Pilot..."
docker compose down

echo "All services stopped."
