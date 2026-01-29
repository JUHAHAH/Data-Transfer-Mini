"""
Parser module for flexible data parsing and transformation.
"""
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
import re


class ParserError(Exception):
    """Raised when parsing fails."""
    pass


class DataParser:
    """Flexible data parsing and transformation engine."""
    
    def __init__(self, parsing_rules: List[Dict[str, Any]], branch_rules: List[Dict[str, Any]], 
                 output_format: Optional[Dict[str, Any]] = None):
        """
        Initialize parser with rules.
        
        Args:
            parsing_rules: List of parsing rules to apply
            branch_rules: List of branch rules for routing
            output_format: Output format configuration
        """
        self.parsing_rules = parsing_rules
        self.branch_rules = branch_rules
        self.output_format = output_format
    
    def parse_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a single row according to parsing rules.
        
        Args:
            row: Raw row data from database
        
        Returns:
            Parsed row data
        """
        parsed_row = row.copy()
        
        # Group parsing rules by column
        rules_by_column: Dict[str, List[Dict[str, Any]]] = {}
        for rule in self.parsing_rules:
            column = rule.get('column')
            if column:
                if column not in rules_by_column:
                    rules_by_column[column] = []
                rules_by_column[column].append(rule)
        
        # Apply parsing rules
        for column, rules in rules_by_column.items():
            if column in parsed_row:
                value = parsed_row[column]
                for rule in rules:
                    try:
                        parsed_value = self._apply_parsing_rule(value, rule)
                        parsed_row[column] = parsed_value
                    except Exception as e:
                        print(f"Warning: Failed to parse column '{column}' with rule {rule}: {e}")
                        # Keep original value if parsing fails
        
        return parsed_row
    
    def _apply_parsing_rule(self, value: Any, rule: Dict[str, Any]) -> Any:
        """
        Apply a single parsing rule to a value.
        
        Args:
            value: Value to parse
            rule: Parsing rule configuration
        
        Returns:
            Parsed value
        """
        if value is None:
            return value
        
        rule_type = rule.get('type', '').lower()
        
        if rule_type == 'decimal':
            precision = rule.get('precision', 2)
            try:
                decimal_value = Decimal(str(value))
                rounded = decimal_value.quantize(
                    Decimal('0.1') ** precision,
                    rounding=ROUND_HALF_UP
                )
                return float(rounded)
            except (ValueError, TypeError):
                return value
        
        elif rule_type == 'integer':
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return value
        
        elif rule_type == 'string':
            format_str = rule.get('format', '')
            if format_str:
                # Support Python format string with {value} placeholder
                # Also support direct Python format() syntax
                try:
                    # Try as Python format string first
                    if '{value}' in format_str:
                        return format_str.replace('{value}', str(value))
                    else:
                        # Try as direct format string (e.g., "{:>10}", "{:.2f}")
                        return format(value, format_str)
                except (ValueError, TypeError):
                    # Fallback to simple replacement
                    return format_str.replace('{value}', str(value))
            return str(value)
        
        elif rule_type == 'date':
            input_format = rule.get('input_format', '%Y-%m-%d %H:%M:%S')
            output_format = rule.get('output_format', '%Y-%m-%d %H:%M:%S')
            try:
                # Handle datetime objects (including MySQL datetime)
                if isinstance(value, datetime):
                    return value.strftime(output_format)
                elif hasattr(value, 'strftime'):
                    # MySQL datetime objects and similar
                    return value.strftime(output_format)
                elif isinstance(value, str):
                    # Try multiple common date formats if input_format fails
                    date_formats = [
                        input_format,
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d %H:%M:%S.%f',
                        '%Y-%m-%d',
                        '%Y/%m/%d %H:%M:%S',
                        '%Y/%m/%d',
                        '%d-%m-%Y %H:%M:%S',
                        '%d/%m/%Y %H:%M:%S',
                        '%d-%m-%Y',
                        '%d/%m/%Y',
                        '%m/%d/%Y %H:%M:%S',
                        '%m/%d/%Y',
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%dT%H:%M:%S.%f',
                        '%Y-%m-%dT%H:%M:%SZ',
                    ]
                    
                    dt = None
                    for fmt in date_formats:
                        try:
                            dt = datetime.strptime(value, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if dt:
                        return dt.strftime(output_format)
                    else:
                        # If all formats fail, return original value
                        return value
                else:
                    return value
            except (ValueError, TypeError, AttributeError) as e:
                return value
        
        elif rule_type == 'custom':
            # Custom function/expression parsing
            expression = rule.get('expression', '')
            if expression:
                # Simple expression evaluation (be careful with security)
                # Replace {value} with actual value
                result = expression.replace('{value}', str(value))
                try:
                    # Try to evaluate as Python expression
                    return eval(result)
                except:
                    return result
            return value
        
        elif rule_type == 'regex':
            pattern = rule.get('pattern', '')
            replacement = rule.get('replacement', '')
            if pattern:
                try:
                    return re.sub(pattern, replacement, str(value))
                except:
                    return value
        
        # Unknown rule type, return original value
        return value
    
    def get_branch_folder(self, row: Dict[str, Any]) -> Optional[str]:
        """
        Determine output folder based on branch rules.
        
        Args:
            row: Parsed row data
        
        Returns:
            Folder path or None if no rule matches
        """
        for rule in self.branch_rules:
            column = rule.get('column')
            value = rule.get('value')
            folder = rule.get('folder')
            
            if column and column in row:
                row_value = row[column]
                
                # Support exact match or pattern matching
                if 'pattern' in rule:
                    # Regex pattern matching
                    pattern = rule['pattern']
                    try:
                        if re.match(pattern, str(row_value)):
                            return folder
                    except:
                        pass
                elif str(row_value) == str(value):
                    return folder
        
        return None
    
    def format_output(self, row: Dict[str, Any], format_type: str = 'json', 
                     action_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Format row data according to output format configuration.
        
        Args:
            row: Parsed row data
            format_type: Format type ('json', 'csv', 'custom', 'structured')
            action_config: Optional action-specific configuration
        
        Returns:
            Formatted string
        """
        if format_type == 'json':
            import json
            return json.dumps(row, default=str, ensure_ascii=False)
        
        elif format_type == 'csv':
            import csv
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=row.keys())
            writer.writerow(row)
            return output.getvalue().strip()
        
        elif format_type == 'custom' or format_type == 'structured':
            # Check for structured format configuration
            structure_config = None
            if action_config and 'structure' in action_config:
                structure_config = action_config['structure']
            elif self.output_format:
                structure_config = self.output_format
            
            if structure_config:
                # Structured format with column ordering
                columns = structure_config.get('columns', [])
                separator = structure_config.get('separator', ',')
                template = structure_config.get('template', '')
                
                if columns:
                    # Use specified column order
                    values = []
                    for col in columns:
                        value = row.get(col, '')
                        values.append(str(value))
                    return separator.join(values)
                
                elif template:
                    # Use template with placeholders
                    try:
                        formatted = template
                        for key, value in row.items():
                            placeholder = f"{{{key}}}"
                            formatted = formatted.replace(placeholder, str(value))
                        return formatted
                    except Exception as e:
                        print(f"Warning: Failed to format output: {e}")
                        return str(row)
            
            # Fallback to template if available
            if self.output_format and 'template' in self.output_format:
                template = self.output_format['template']
                separator = self.output_format.get('separator', '|')
                try:
                    # Check if template uses separator format (e.g., "{col1},{col2}")
                    if separator in template:
                        # Extract column names from template
                        import re
                        col_pattern = r'\{(\w+)\}'
                        columns = re.findall(col_pattern, template)
                        if columns:
                            values = [str(row.get(col, '')) for col in columns]
                            return separator.join(values)
                    
                    # Otherwise, replace placeholders directly
                    formatted = template
                    for key, value in row.items():
                        placeholder = f"{{{key}}}"
                        formatted = formatted.replace(placeholder, str(value))
                    return formatted
                except Exception as e:
                    print(f"Warning: Failed to format output: {e}")
                    return str(row)
            else:
                # Default to pipe-separated values
                return '|'.join(str(v) for v in row.values())
        
        else:
            return str(row)
    
    def parse_batch(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse a batch of rows.
        
        Args:
            rows: List of raw row data
        
        Returns:
            List of parsed row data
        """
        return [self.parse_row(row) for row in rows]
