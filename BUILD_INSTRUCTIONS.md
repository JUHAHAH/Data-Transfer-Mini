# Building Standalone Executable

This guide explains how to build a portable standalone executable that doesn't require Python to be installed.

## Prerequisites

- Python 3.7 or higher installed
- All runtime dependencies installed (`pip install -r requirements.txt`)

## Quick Build

### Windows
```bash
pip install pyinstaller
build.bat
```

### Linux/Mac
```bash
pip install pyinstaller
chmod +x build.sh
./build.sh
```

## Manual Build

If you prefer to build manually:

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller --name="MySQLDataParser" \
    --onefile \
    --console \
    --add-data "config.json;." \
    --hidden-import=mysql.connector \
    --hidden-import=schedule \
    --hidden-import=requests \
    --collect-all mysql.connector \
    main.py
```

Or use the spec file:
```bash
pyinstaller MySQLDataParser.spec
```

## Build Options

### Windowed Mode (No Console)

To hide the console window on Windows, edit `build.bat` and change:
- `--console` to `--windowed`
- Or edit `MySQLDataParser.spec` and set `console=False`

### Include Additional Files

To include additional files (like example configs), add to `--add-data`:
```bash
--add-data "config.json;config_example.json;."
```

### Reduce Executable Size

The executable includes all Python dependencies and can be large (50-100MB). To reduce size:

1. Use `--exclude-module` to exclude unused modules
2. Use UPX compression (already enabled in spec file)
3. Consider using `--onedir` instead of `--onefile` (creates a folder instead of single file)

## Distribution

When distributing the executable:

1. **Include `config.json`** - The executable expects `config.json` in the same directory
2. **Create a package** with:
   - `MySQLDataParser.exe` (or `MySQLDataParser` on Linux/Mac)
   - `config.json` (or `config_example.json` for users to customize)
   - `README.md` (instructions)
   - `FORMATTING_GUIDE.md` (optional documentation)

3. **Optional files:**
   - `.env` file template (if using environment variables)
   - Example output directory structure

## Troubleshooting

### "Module not found" errors

Add missing modules to `--hidden-import`:
```bash
--hidden-import=missing_module_name
```

### Large executable size

- Use `--onedir` mode instead of `--onefile`
- Exclude unused modules with `--exclude-module`
- The first run may be slower as files are extracted

### MySQL connector issues

The spec file includes `--collect-all mysql.connector` to ensure all MySQL connector files are included. If you still have issues, try:
```bash
--collect-all mysql.connector.pooling
--collect-all mysql.connector.cursor
```

### Config file not found

Make sure `config.json` is included with `--add-data`. The executable will look for it in the same directory as the executable.

## Advanced: Custom Spec File

Edit `MySQLDataParser.spec` for advanced configuration:

- Change `console=True` to `console=False` for windowed mode
- Add more data files in the `datas` list
- Adjust UPX compression settings
- Modify icon (add `icon='icon.ico'` to EXE section)
