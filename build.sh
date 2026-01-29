#!/bin/bash
set -e  # Exit on error
echo "Building standalone executable..."
echo

# Use the full path to Python to avoid WindowsApps stub issues in Git Bash
PYTHON_CMD="/c/Users/user/AppData/Local/Programs/Python/Python314/python.exe"

# Verify Python exists
if [ ! -f "$PYTHON_CMD" ]; then
    echo "ERROR: Python executable not found at $PYTHON_CMD"
    echo "Trying 'python' command instead..."
    PYTHON_CMD="python"
fi

# Create build directories
mkdir -p dist build

# Check if spec file exists
if [ ! -f "MySQLDataParser.spec" ]; then
    echo "ERROR: MySQLDataParser.spec file not found!"
    exit 1
fi

# Build executable
echo "Running PyInstaller..."
$PYTHON_CMD -m PyInstaller MySQLDataParser.spec

echo
echo "Build complete! Executable is in the 'dist' folder."
echo "File: dist/MySQLDataParser.exe"
echo
