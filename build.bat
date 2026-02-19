@echo off
setlocal enabledelayedexpansion
REM Change to the directory where this script lives (project root)
cd /d "%~dp0"
echo Building standalone executable...
echo Current directory: %CD%
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not found in PATH!
    echo Please make sure Python is installed and added to your system PATH.
    pause
    exit /b 1
)

REM Install PyInstaller if not already installed
echo Installing/updating PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller!
    pause
    exit /b 1
)

REM Create build directory
if not exist "dist" mkdir dist
if not exist "build" mkdir build

REM Check if spec file exists
if not exist "MySQLDataParser.spec" (
    echo ERROR: MySQLDataParser.spec file not found!
    pause
    exit /b 1
)

REM Build executable
echo Running PyInstaller...
python -m PyInstaller MySQLDataParser.spec
set BUILD_ERROR=%ERRORLEVEL%

if %BUILD_ERROR% EQU 0 (
    echo.
    echo Build complete! Executable is in the 'dist' folder.
    echo File: dist\MySQLDataParser.exe
    echo.
) else (
    echo.
    echo Build failed with error code: %BUILD_ERROR%
    echo Check the error messages above.
    echo.
)

pause
exit /b %BUILD_ERROR%