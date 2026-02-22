#!/bin/bash
set -e  # Exit on error
# Change to script directory (project root)
cd "$(dirname "$0")"

# Check if executable exists
if [ ! -f "dist/MySQLDataParser" ]; then
    echo "ERROR: MySQLDataParser executable not found in dist folder!"
    echo "Please run build.sh first to build the executable."
    exit 1
fi

echo "Running MySQL Data Parser..."
echo ""
cd dist
./MySQLDataParser "$@"
EXIT_CODE=$?
cd ..

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "Program completed successfully."
else
    echo "Program exited with error code: $EXIT_CODE"
fi
echo ""
read -p "Press Enter to exit..."
