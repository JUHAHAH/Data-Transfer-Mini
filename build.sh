#!/bin/bash
echo "Building standalone executable..."
echo

# Install PyInstaller if not already installed
python -m pip install pyinstaller --quiet

# Create build directories
mkdir -p dist build

# Build executable
python -m PyInstaller --name="MySQLDataParser" \
    --onefile \
    --console \
    --add-data "config.json:." \
    --hidden-import=mysql.connector \
    --hidden-import=schedule \
    --hidden-import=requests \
    --hidden-import=dotenv \
    --hidden-import=ftplib \
    --hidden-import=ssl \
    --hidden-import=mysql.connector.pooling \
    --hidden-import=mysql.connector.cursor \
    --collect-all mysql.connector \
    main.py

echo
echo "Build complete! Executable is in the 'dist' folder."
echo
