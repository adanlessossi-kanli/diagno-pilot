@echo off
REM stop.bat — Stop Diagno-Pilot locally

echo Stopping Diagno-Pilot...

docker compose down
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: docker compose down failed ^(exit code %ERRORLEVEL%^).
    echo.
    echo Checking for services still running...
    FOR /F "tokens=*" %%S IN ('docker compose ps --status running --format "{{.Service}}" 2^>nul') DO (
        echo   - %%S
    )
    echo.
    echo Run 'docker compose logs ^<service^>' for details.
    exit /b 1
)

echo All services stopped.
