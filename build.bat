@echo off
echo Building standalone executable...
echo.

REM Install PyInstaller if not already installed
python -m pip install pyinstaller --quiet

REM Create build directory
if not exist "dist" mkdir dist
if not exist "build" mkdir build

REM Build executable
echo Running PyInstaller...
python -m PyInstaller --name="MySQLDataParser" ^
    --onefile ^
    --console ^
    --add-data "config.json;." ^
    --hidden-import=mysql.connector ^
    --hidden-import=schedule ^
    --hidden-import=requests ^
    --hidden-import=dotenv ^
    --hidden-import=ftplib ^
    --hidden-import=ssl ^
    --hidden-import=mysql.connector.pooling ^
    --hidden-import=mysql.connector.cursor ^
    --collect-all mysql.connector ^
    main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Build complete! Executable is in the 'dist' folder.
    echo File: dist\MySQLDataParser.exe
) else (
    echo.
    echo Build failed! Check the error messages above.
)

echo.
pause
