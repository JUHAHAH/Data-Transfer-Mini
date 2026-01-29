# Distribution Guide

This guide explains how to create and distribute the standalone executable.

## Quick Build

### Windows
```bash
build.bat
```

### Linux/Mac
```bash
chmod +x build.sh
./build.sh
```

The executable will be in the `dist/` folder.

## Distribution Package Structure

When distributing the executable, create a package with:

```
MySQLDataParser/
├── MySQLDataParser.exe    (or MySQLDataParser on Linux/Mac)
├── config.json            (user must configure this)
├── config_example.json    (example/template)
├── README.md              (instructions)
└── FORMATTING_GUIDE.md    (optional documentation)
```

## Important Notes

1. **config.json is required** - Users must create/edit `config.json` in the same directory as the executable
2. **No Python required** - The executable is completely standalone
3. **First run** - May take a few seconds to extract files (PyInstaller onefile mode)
4. **Antivirus warnings** - Some antivirus software may flag PyInstaller executables. This is a false positive.

## File Sizes

- **Executable**: ~50-100 MB (includes Python and all dependencies)
- **Total package**: ~50-150 MB depending on included files

## Usage Instructions for End Users

1. Extract the package to a folder
2. Edit `config.json` with your database settings
3. Run `MySQLDataParser.exe` (Windows) or `./MySQLDataParser` (Linux/Mac)
4. The program will create:
   - `data_parser.log` - Log file
   - `state.json` - State tracking file
   - Output files/folders as configured

## Troubleshooting for End Users

### "Configuration file not found"
- Make sure `config.json` is in the same folder as the executable
- Check that the file is named exactly `config.json` (case-sensitive on Linux/Mac)

### "Module not found" errors
- Rebuild with additional `--hidden-import` flags
- Check BUILD_INSTRUCTIONS.md for details

### Program won't start
- Check `data_parser.log` for error messages
- Make sure all required files are in the same directory
- On Windows, try running as Administrator if there are permission issues

## Building for Different Platforms

### Cross-platform Building

You need to build on each target platform:
- **Windows executable**: Build on Windows
- **Linux executable**: Build on Linux
- **Mac executable**: Build on macOS

### Alternative: Use Docker

You can use Docker to build for different platforms, but you'll still need the target OS for final testing.

## Reducing Executable Size

If the executable is too large:

1. Use `--onedir` instead of `--onefile`:
   ```bash
   pyinstaller --onedir --name="MySQLDataParser" main.py
   ```
   This creates a folder with the executable and dependencies (smaller individual files, but more files total)

2. Exclude unused modules:
   ```bash
   --exclude-module=tkinter
   --exclude-module=matplotlib
   ```

3. Use UPX compression (already enabled in spec file)

## Code Signing (Optional)

For Windows, you can sign the executable to avoid antivirus warnings:

```bash
signtool sign /f certificate.pfx /p password MySQLDataParser.exe
```

This requires a code signing certificate.
