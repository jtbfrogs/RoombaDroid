@echo off
REM Run tests for DROID system

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║              DROID SYSTEM - Test Suite                     ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Activate venv
if exist "droid_env" (
    call droid_env\Scripts\activate.bat
) else (
    echo Virtual environment not found. Run run.bat first.
    pause
    exit /b 1
)

REM Run tests
python test_system.py

pause
