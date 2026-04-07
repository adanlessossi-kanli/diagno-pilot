@echo off
REM start.bat — Start Diagno-Pilot locally

echo Starting Diagno-Pilot...

docker compose up --build -d
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: docker compose up failed ^(exit code %ERRORLEVEL%^).
    echo.
    echo Checking for failed services...
    FOR /F "tokens=*" %%S IN ('docker compose ps --status exited --format "{{.Service}}" 2^>nul') DO (
        echo   - %%S
    )
    echo.
    echo Run 'docker compose logs ^<service^>' for details.
    exit /b 1
)

echo.
echo Services:
echo   Frontend   ^-^> http://localhost:3000
echo   Backend    ^-^> http://localhost:8000
echo   Model LLM  ^-^> http://localhost:8080
echo   MongoDB    ^-^> mongodb://localhost:27017
echo   LocalStack ^-^> http://localhost:4566
echo.
echo Run 'docker compose logs -f' to follow logs.
