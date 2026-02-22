@echo off
setlocal enabledelayedexpansion
REM Change to the directory where this script lives (project root)
cd /d "%~dp0"

REM Check if executable exists
if not exist "dist\MySQLDataParser.exe" (
    echo ERROR: MySQLDataParser.exe not found in dist folder!
    echo Please run build.bat first to build the executable.
    pause
    exit /b 1
)

echo Running MySQL Data Parser...
echo.
cd dist
MySQLDataParser.exe
set EXIT_CODE=%ERRORLEVEL%
cd ..

echo.
if %EXIT_CODE% EQU 0 (
    echo Program completed successfully.
) else (
    echo Program exited with error code: %EXIT_CODE%
)
echo.
pause
exit /b %EXIT_CODE%
