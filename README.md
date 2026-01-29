# MySQL Data Parser and Transmitter

A standalone Python program that monitors a MySQL database table for new rows, parses data according to configurable rules, and executes customizable actions (API transmission, file appending, FTP upload) at configurable intervals.

## Features

- **Database Monitoring**: Tracks a specific MySQL table for new rows using auto-increment ID tracking
- **Flexible Data Parsing**: Configurable parsing rules for decimal rounding, string formatting, date parsing, and more
- **Branch Processing**: Route data to different folders based on column values
- **Multiple Action Types**:
  - **API Transmission**: Send data as JSON to HTTP endpoints
  - **File Appending**: Append processed data to files (supports JSON, CSV, custom formats)
  - **FTP Upload**: Upload data files to FTP servers with TLS/SSL support
- **Custom Output Formats**: Configurable templates for structuring output data
- **Interval Scheduling**: Configurable check intervals (e.g., every 1min, 2min)
- **State Persistence**: Tracks last processed ID to avoid reprocessing data

## Installation

### Option 1: Run as Python Script

1. Install Python 3.7 or higher
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the program:
   ```bash
   python main.py
   ```

### Option 2: Standalone Executable (Portable)

Build a standalone executable that doesn't require Python:

**Windows:**
```bash
pip install -r requirements-build.txt
build.bat
```

**Linux/Mac:**
```bash
pip install -r requirements-build.txt
chmod +x build.sh
./build.sh
```

The executable will be created in the `dist` folder as `MySQLDataParser.exe` (Windows) or `MySQLDataParser` (Linux/Mac).

**Note:** The executable includes all dependencies and can be distributed without Python. Make sure to include `config.json` in the same directory as the executable.

## Configuration

Create a `config.json` file with your settings. See the example below:

```json
{
  "database": {
    "host": "localhost",
    "port": 3306,
    "user": "username",
    "password": "password",
    "database": "dbname",
    "table": "tablename",
    "id_column": "id"
  },
  "interval_seconds": 60,
  "parsing_rules": [
    {
      "column": "column_a",
      "type": "decimal",
      "precision": 2
    }
  ],
  "branch_rules": [
    {
      "column": "column_a",
      "value": "X",
      "folder": "folder/x"
    }
  ],
  "actions": [
    {
      "type": "api",
      "url": "https://api.example.com/endpoint",
      "method": "POST",
      "headers": {}
    },
    {
      "type": "file",
      "path": "output/data.txt",
      "format": "json"
    },
    {
      "type": "ftp",
      "host": "ftp.example.com",
      "port": 21,
      "user": "ftpuser",
      "password": "ftppass",
      "use_tls": true,
      "remote_path": "/uploads/",
      "filename_template": "data_{timestamp}.txt"
    }
  ],
  "output_format": {
    "structure": "custom",
    "template": "{column_a}|{column_b}|{column_c}"
  }
}
```

### Configuration Options

#### Database Configuration
- `host`: MySQL server hostname
- `port`: MySQL server port (default: 3306)
- `user`: MySQL username
- `password`: MySQL password (can use `${ENV_VAR}` for environment variables)
- `database`: Database name
- `table`: Table name to monitor
- `id_column`: Auto-increment ID column name

#### Parsing Rules
Each parsing rule supports:
- `column`: Column name to parse
- `type`: Rule type (`decimal`, `integer`, `string`, `date`, `regex`, `custom`)
- Additional type-specific options:
  - `decimal`: `precision` (number of decimal places)
  - `date`: `input_format`, `output_format` (strftime formats)
  - `regex`: `pattern`, `replacement`
  - `custom`: `expression` (Python expression with `{value}` placeholder)

#### Branch Rules
- `column`: Column to check
- `value`: Value to match (exact match)
- `pattern`: Regex pattern (alternative to `value`)
- `folder`: Folder path to use when rule matches

#### Actions

**API Action:**
```json
{
  "type": "api",
  "url": "https://api.example.com/endpoint",
  "method": "POST",
  "headers": {
    "Authorization": "Bearer token"
  },
  "timeout": 30,
  "max_retries": 3
}
```

**File Action:**
```json
{
  "type": "file",
  "path": "output/data.txt",
  "format": "json"
}
```
Formats: `json`, `csv`, `custom`

**FTP Action:**
```json
{
  "type": "ftp",
  "host": "ftp.example.com",
  "port": 21,
  "user": "ftpuser",
  "password": "ftppass",
  "use_tls": true,
  "remote_path": "/uploads/",
  "filename_template": "data_{timestamp}.txt",
  "format": "json"
}
```

#### Output Format
- `structure`: `custom` for template-based formatting
- `template`: String template with `{column_name}` placeholders

## Usage

Run the program:
```bash
python main.py
```

Or specify a custom config file:
```bash
python main.py --config custom_config.json
```

The program will:
1. Load configuration
2. Connect to the database
3. Check for new rows at the specified interval
4. Parse each row according to parsing rules
5. Execute all configured actions
6. Update the state with the last processed ID

## State Management

The program maintains state in `state.json` to track the last processed ID. This ensures:
- No data is reprocessed after restart
- Processing continues from where it left off
- Safe to stop and restart the program

To reset state (start from beginning):
```python
from state import StateManager
sm = StateManager()
sm.reset()  # Reset all state
sm.reset("tablename")  # Reset state for specific table
```

## Logging

Logs are written to:
- Console (stdout)
- `data_parser.log` file

Log levels: INFO, WARNING, ERROR

## Environment Variables

You can use environment variables in configuration by using `${VAR_NAME}` syntax:
```json
{
  "database": {
    "password": "${DB_PASSWORD}"
  }
}
```

Create a `.env` file or set environment variables before running.

## Error Handling

- Database connection errors: Retries with exponential backoff
- Action failures: Logged but processing continues for other rows
- Parsing errors: Original value preserved, warning logged
- State corruption: Automatically resets to safe state

## Examples

### Example 1: Round Decimal Values
```json
{
  "parsing_rules": [
    {
      "column": "price",
      "type": "decimal",
      "precision": 2
    }
  ]
}
```
Converts `123.123456789` → `123.12`

### Example 2: Branch by Category
```json
{
  "branch_rules": [
    {
      "column": "category",
      "value": "A",
      "folder": "category_a"
    },
    {
      "column": "category",
      "value": "B",
      "folder": "category_b"
    }
  ]
}
```

### Example 3: Custom Output Format
```json
{
  "output_format": {
    "structure": "custom",
    "template": "{id}|{name}|{price}|{timestamp}"
  }
}
```

## License

This project is provided as-is for use in your projects.
