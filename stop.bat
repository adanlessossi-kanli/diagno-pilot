@echo off
REM stop.bat — Stop Diagno-Pilot locally

echo Stopping Diagno-Pilot...
docker compose down

echo All services stopped.
