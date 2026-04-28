@echo off
REM Start the DROID system v3.0

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║              DROID SYSTEM v3.0 - Starting                  ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

REM Check if venv exists
if not exist "dro" (
    echo Creating virtual environment...
    python -m venv dro
)

REM Activate venv
call C:\Users\jtbdr\Desktop\droid\dro\Scripts\activate.bat

REM Install requirements if needed
pip install -q -r requirements.txt 2>nul

REM Run main program
python main.py

pause
