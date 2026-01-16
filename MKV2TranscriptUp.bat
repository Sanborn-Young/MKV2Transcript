@echo off
REM MKV2Transcript Startup Script
echo ================================================
echo    MKV2Transcript - Starting Service
echo ================================================
echo.

REM Change to the script directory
cd /d "%~dp0"

echo [1/3] Checking Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is not running!
    echo Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)

echo [2/3] Starting MKV2Transcript container...
docker-compose up -d

if errorlevel 1 (
    echo.
    echo ERROR: Failed to start container!
    echo Check the error messages above.
    echo.
    pause
    exit /b 1
)

echo [3/3] Waiting for service to be ready...
timeout /t 5 /nobreak >nul

echo.
echo ================================================
echo    MKV2Transcript is now running!
echo ================================================
echo.
echo Opening web interface in your browser...
echo Access URL: http://localhost:7860
echo.
echo To stop the service, run: MKV2TranscriptDown.bat
echo.

REM Open browser
start http://localhost:7860

echo.
echo Press any key to close this window...
pause >nul
