@echo off
REM stop.bat — Stop Diagno-Pilot locally

echo Stopping Diagno-Pilot...

docker compose down
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: docker compose down failed ^(exit code %ERRORLEVEL%^).
    exit /b 1
)

echo All services stopped.
