@echo off
REM MKV2Transcript Shutdown Script
echo ================================================
echo    MKV2Transcript - Stopping Service
echo ================================================
echo.

REM Change to the script directory
cd /d "%~dp0"

echo [1/2] Checking Docker status...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Docker Desktop is not running!
    echo The container may already be stopped.
    echo.
    pause
    exit /b 0
)

echo [2/2] Stopping MKV2Transcript container...
docker-compose down

if errorlevel 1 (
    echo.
    echo ERROR: Failed to stop container!
    echo Check the error messages above.
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================
echo    MKV2Transcript has been stopped
echo ================================================
echo.
echo To start again, run: MKV2TranscriptUp.bat
echo.
echo Press any key to close this window...
pause >nul
