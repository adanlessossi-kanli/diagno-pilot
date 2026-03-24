@echo off
REM start.bat — Start Diagno-Pilot locally

echo Starting Diagno-Pilot...
docker compose up --build -d

echo.
echo Services:
echo   Frontend   ^-^> http://localhost:3000
echo   Backend    ^-^> http://localhost:8000
echo   MongoDB    ^-^> mongodb://localhost:27017
echo   LocalStack ^-^> http://localhost:4566
echo.
echo Run 'docker compose logs -f' to follow logs.
