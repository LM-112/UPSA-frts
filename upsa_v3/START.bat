@echo off
title UPSA FRT Attendance System
color 1F
echo ===========================================================
echo   UPSA Face Recognition Attendance System v1.0
echo   Group 66 - University of Professional Studies, Accra
echo   Hikvision DS-K1T323MBFWX-E1 MinMoe Terminal
echo ===========================================================
echo.

cd /d "%~dp0"

echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python from python.org
    pause
    exit /b
)

echo [2/4] Installing required packages...
python -m pip install flask openpyxl requests python-dotenv --quiet --user

echo [3/4] Starting UPSA FRT System...
echo.
echo  Open your browser and go to:
echo.
echo       http://127.0.0.1:5000
echo.
echo  Login accounts:
echo    Super Admin : super@upsa.edu.gh      / Super@2026
echo    Admin       : admin@upsa.edu.gh      / Admin@2026
echo    Lecturer    : kowusu@upsa.edu.gh     / Lecturer@2026
echo    Student     : 10300137@students.upsa.edu.gh / Student@2026
echo.
echo  Press CTRL+C to stop the server.
echo ===========================================================

python run.py

pause
