# Data Formatting Guide

This guide explains how to configure custom date formats, string formatting, and structured output formats.

## Date Format Parsing

The parser supports flexible date format parsing. Configure date parsing rules in `parsing_rules`:

```json
{
  "column": "created_at",
  "type": "date",
  "input_format": "%Y-%m-%d %H:%M:%S",
  "output_format": "%Y/%m/%d %H:%M"
}
```

### Supported Date Formats

The parser automatically tries multiple common formats if `input_format` doesn't match:
- `%Y-%m-%d %H:%M:%S` (e.g., "2024-01-28 14:30:00")
- `%Y-%m-%d %H:%M:%S.%f` (with microseconds)
- `%Y-%m-%d` (date only)
- `%Y/%m/%d %H:%M:%S`
- `%d-%m-%Y %H:%M:%S`
- `%Y-%m-%dT%H:%M:%S` (ISO format)
- And more...

### Output Format Examples

```json
// Output as: "2024/01/28 14:30"
{
  "column": "created_at",
  "type": "date",
  "output_format": "%Y/%m/%d %H:%M"
}

// Output as: "28-Jan-2024"
{
  "column": "created_at",
  "type": "date",
  "output_format": "%d-%b-%Y"
}

// Output as: "20240128"
{
  "column": "created_at",
  "type": "date",
  "output_format": "%Y%m%d"
}
```

## String Formatting

String formatting supports Python format string syntax:

```json
{
  "column": "name",
  "type": "string",
  "format": "{value}"
}
```

### Format Examples

```json
// Right-align with 10 characters width
{
  "column": "status",
  "type": "string",
  "format": "{:>10}"
}

// Left-align with 15 characters width
{
  "column": "name",
  "type": "string",
  "format": "{:<15}"
}

// Center-align with 20 characters width
{
  "column": "title",
  "type": "string",
  "format": "{:^20}"
}

// Uppercase
{
  "column": "code",
  "type": "string",
  "format": "{value}".upper()
}
```

## Structured Output Formats

Instead of JSON, you can output data in custom structured formats like CSV with specific column ordering.

### Method 1: Column-Based Structure

Specify columns and separator in the action configuration:

```json
{
  "type": "file",
  "path": "output/data.txt",
  "format": "structured",
  "structure": {
    "columns": ["Column1", "Column2"],
    "separator": ","
  }
}
```

Output example:
```
XYZ,123.12
ABC,456.78
```

### Method 2: Template-Based Structure

Use a template with placeholders:

```json
{
  "type": "file",
  "path": "output/data.txt",
  "format": "custom",
  "structure": {
    "template": "{Column1},{Column2}",
    "separator": ","
  }
}
```

Or use the global `output_format`:

```json
{
  "output_format": {
    "structure": "custom",
    "template": "{Column1},{Column2}"
  }
}
```

### Separator Options

- Comma: `","`
- Pipe: `"|"`
- Tab: `"\t"`
- Space: `" "`
- Custom: Any string

## Complete Example Configuration

```json
{
  "parsing_rules": [
    {
      "column": "price",
      "type": "decimal",
      "precision": 2
    },
    {
      "column": "created_at",
      "type": "date",
      "input_format": "%Y-%m-%d %H:%M:%S",
      "output_format": "%Y/%m/%d"
    },
    {
      "column": "name",
      "type": "string",
      "format": "{value}"
    }
  ],
  "actions": [
    {
      "type": "file",
      "path": "output/data.txt",
      "format": "structured",
      "structure": {
        "columns": ["name", "price", "created_at"],
        "separator": ","
      }
    }
  ]
}
```

This will output:
```
Product A,123.45,2024/01/28
Product B,678.90,2024/01/29
```

## Format Types

- `json`: Standard JSON format (default)
- `csv`: CSV format with all columns
- `custom`: Template-based format
- `structured`: Column-ordered format with custom separator
