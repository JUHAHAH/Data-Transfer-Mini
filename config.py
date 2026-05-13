"""
Configuration module for loading and validating JSON configuration.
"""
import json
import logging
import os
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

logger = logging.getLogger(__name__)


def get_resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    
    Args:
        relative_path: Relative path to resource
    
    Returns:
        Absolute path to resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Running as script, use current directory
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


def _get_default_config() -> Dict[str, Any]:
    """
    Get default configuration template.
    
    Returns:
        Default configuration dictionary
    """
    return {
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
        "branch_rules": [],
        "actions": [
            {
                "type": "file",
                "path": "output/data.txt",
                "format": "structured",
                "structure": {
                    "columns": ["column_a"],
                    "separator": ","
                }
            }
        ],
        "output_format": {
            "structure": "custom",
            "template": "{column_a}"
        }
    }


class Config:
    """Configuration loader and validator."""
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize configuration from JSON file.
        
        Args:
            config_path: Path to the configuration JSON file
        """
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self.load()
    
    def _create_default_config(self, config_path: str):
        """
        Create a default configuration file if it doesn't exist.
        
        Args:
            config_path: Path where to create the default config file
        """
        try:
            # Ensure directory exists
            config_dir = os.path.dirname(config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            # Try to load template from config_template.json if it exists
            default_config = None
            
            # First, try to find config_template.json in the same directory as the executable
            if getattr(sys, 'frozen', False):
                template_path = os.path.join(os.path.dirname(sys.executable), "config_template.json")
            else:
                template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_template.json")
            
            if os.path.exists(template_path):
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        default_config = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load config_template.json: {e}. Using built-in default.")
            
            # If template not found, use built-in default
            if default_config is None:
                default_config = _get_default_config()
            
            # Write default config to the target location
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Created default configuration file at: {config_path}")
            logger.info("Please edit the configuration file with your settings before running the application.")
            
        except Exception as e:
            raise ConfigError(f"Failed to create default configuration file at {config_path}: {e}")
    
    def load(self):
        """Load and validate configuration from file."""
        # Determine the primary config location (executable directory for built programs)
        if getattr(sys, 'frozen', False):
            # Running as compiled executable - use executable's directory
            primary_config_dir = os.path.dirname(sys.executable)
            primary_config_path = os.path.join(primary_config_dir, self.config_path)
        else:
            # Running as script - use script's directory
            primary_config_dir = os.path.dirname(os.path.abspath(__file__))
            primary_config_path = os.path.join(primary_config_dir, self.config_path)
        
        # If config doesn't exist in primary location, create default one
        if not os.path.exists(primary_config_path):
            if getattr(sys, 'frozen', False):
                # For built executables, create default config.json in executable directory
                self._create_default_config(primary_config_path)
            else:
                # For development, try to find config in other locations
                config_locations = [
                    os.path.join(os.getcwd(), self.config_path),
                    self.config_path if os.path.isabs(self.config_path) else None
                ]
                config_found = None
                for location in config_locations:
                    if location and os.path.exists(location):
                        config_found = location
                        break
                
                if not config_found:
                    raise ConfigError(f"Configuration file not found: {self.config_path}. Searched in: {', '.join([loc for loc in config_locations if loc])}")
                
                self.config_path = config_found
        else:
            self.config_path = primary_config_path
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        
        self._substitute_env_vars()
        self._validate()
    
    def _substitute_env_vars(self):
        """Substitute environment variables in configuration values."""
        def replace_env_vars(obj):
            if isinstance(obj, dict):
                return {k: replace_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
                env_var = obj[2:-1]
                return os.getenv(env_var, obj)
            return obj
        
        self._config = replace_env_vars(self._config)
    
    def _validate(self):
        """Validate configuration structure."""
        required_keys = ['database', 'interval_seconds', 'parsing_rules', 'branch_rules', 'actions']
        for key in required_keys:
            if key not in self._config:
                raise ConfigError(f"Missing required configuration key: {key}")
        
        # Validate database config
        db_config = self._config['database']
        required_db_keys = ['host', 'port', 'user', 'password', 'database', 'table', 'id_column']
        for key in required_db_keys:
            if key not in db_config:
                raise ConfigError(f"Missing required database configuration key: {key}")
        
        # Validate optional custom query (must have exactly one %s for cursor)
        custom_query = db_config.get('query')
        if custom_query is not None:
            if not isinstance(custom_query, str) or not custom_query.strip():
                raise ConfigError("database.query must be a non-empty string")
            if custom_query.count('%s') != 1:
                raise ConfigError("database.query must contain exactly one %s placeholder for the cursor value")
        
        # Validate interval
        if not isinstance(self._config['interval_seconds'], (int, float)) or self._config['interval_seconds'] <= 0:
            raise ConfigError("interval_seconds must be a positive number")
        
        # Validate parsing_rules
        if not isinstance(self._config['parsing_rules'], list):
            raise ConfigError("parsing_rules must be a list")
        
        # Validate branch_rules
        if not isinstance(self._config['branch_rules'], list):
            raise ConfigError("branch_rules must be a list")
        
        # Validate actions
        if not isinstance(self._config['actions'], list) or len(self._config['actions']) == 0:
            raise ConfigError("actions must be a non-empty list")
        
        for action in self._config['actions']:
            if 'type' not in action:
                raise ConfigError("Each action must have a 'type' field")
            if action['type'] not in ['api', 'file', 'ftp']:
                raise ConfigError(f"Unknown action type: {action['type']}")
            
            # Validate action-specific fields
            if action['type'] == 'api':
                if 'url' not in action:
                    raise ConfigError("API action must have 'url' field")
            elif action['type'] == 'file':
                if 'path' not in action:
                    raise ConfigError("File action must have 'path' field")
            elif action['type'] == 'ftp':
                required_ftp_keys = ['host', 'port', 'user', 'password', 'remote_path']
                for key in required_ftp_keys:
                    if key not in action:
                        raise ConfigError(f"FTP action must have '{key}' field")
    
    @property
    def database(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self._config['database']
    
    @property
    def interval_seconds(self) -> float:
        """Get check interval in seconds."""
        return float(self._config['interval_seconds'])
    
    @property
    def monitoring_restart_on_error(self) -> bool:
        """If True (default), GUI will schedule monitoring restart after a fatal processing error."""
        return bool(self._config.get('monitoring_restart_on_error', True))
    
    @property
    def monitoring_restart_delay_seconds(self) -> float:
        """Seconds to wait before auto-restarting monitoring after an error."""
        return float(self._config.get('monitoring_restart_delay_seconds', 90))
    
    @property
    def monitoring_restart_max_attempts(self) -> int:
        """Max consecutive error-triggered restarts before giving up (0 = unlimited)."""
        return int(self._config.get('monitoring_restart_max_attempts', 0))
    
    @property
    def ftp_global_defaults(self) -> Dict[str, Any]:
        """
        Optional root-level keys merged into every FTP action (action-specific values win).
        Supported: connect_timeout (seconds).
        """
        d: Dict[str, Any] = {}
        if 'connect_timeout' in self._config:
            try:
                d['connect_timeout'] = float(self._config['connect_timeout'])
            except (TypeError, ValueError):
                pass
        return d
    
    @property
    def parsing_rules(self) -> List[Dict[str, Any]]:
        """Get parsing rules."""
        return self._config['parsing_rules']
    
    @property
    def branch_rules(self) -> List[Dict[str, Any]]:
        """Get branch rules."""
        return self._config['branch_rules']
    
    @property
    def actions(self) -> List[Dict[str, Any]]:
        """Get actions configuration."""
        return self._config['actions']
    
    @property
    def output_format(self) -> Optional[Dict[str, Any]]:
        """Get output format configuration."""
        return self._config.get('output_format')
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self._config.get(key, default)
    
    def save(self):
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            raise ConfigError(f"Failed to save configuration: {e}")
    
    def update_database_config(self, **kwargs):
        """Update database configuration."""
        if 'database' not in self._config:
            self._config['database'] = {}
        self._config['database'].update(kwargs)
        self._validate()
    
    def update_interval(self, interval_seconds: float):
        """Update check interval."""
        if not isinstance(interval_seconds, (int, float)) or interval_seconds <= 0:
            raise ConfigError("interval_seconds must be a positive number")
        self._config['interval_seconds'] = interval_seconds
    
    def add_action(self, action: Dict[str, Any]):
        """Add a new action."""
        if 'type' not in action:
            raise ConfigError("Action must have a 'type' field")
        if action['type'] not in ['api', 'file', 'ftp']:
            raise ConfigError(f"Unknown action type: {action['type']}")
        self._config['actions'].append(action)
        self._validate()
    
    def update_action(self, index: int, action: Dict[str, Any]):
        """Update an existing action."""
        if index < 0 or index >= len(self._config['actions']):
            raise ConfigError(f"Invalid action index: {index}")
        if 'type' not in action:
            raise ConfigError("Action must have a 'type' field")
        if action['type'] not in ['api', 'file', 'ftp']:
            raise ConfigError(f"Unknown action type: {action['type']}")
        self._config['actions'][index] = action
        self._validate()
    
    def remove_action(self, index: int):
        """Remove an action."""
        if index < 0 or index >= len(self._config['actions']):
            raise ConfigError(f"Invalid action index: {index}")
        if len(self._config['actions']) <= 1:
            raise ConfigError("Cannot remove last action. At least one action is required.")
        del self._config['actions'][index]
    
    def add_parsing_rule(self, rule: Dict[str, Any]):
        """Add a new parsing rule."""
        if 'column' not in rule:
            raise ConfigError("Parsing rule must have a 'column' field")
        self._config['parsing_rules'].append(rule)
    
    def update_parsing_rule(self, index: int, rule: Dict[str, Any]):
        """Update an existing parsing rule."""
        if index < 0 or index >= len(self._config['parsing_rules']):
            raise ConfigError(f"Invalid parsing rule index: {index}")
        if 'column' not in rule:
            raise ConfigError("Parsing rule must have a 'column' field")
        self._config['parsing_rules'][index] = rule
    
    def remove_parsing_rule(self, index: int):
        """Remove a parsing rule."""
        if index < 0 or index >= len(self._config['parsing_rules']):
            raise ConfigError(f"Invalid parsing rule index: {index}")
        del self._config['parsing_rules'][index]
    
    def add_branch_rule(self, rule: Dict[str, Any]):
        """Add a new branch rule."""
        if 'column' not in rule or 'value' not in rule or 'folder' not in rule:
            raise ConfigError("Branch rule must have 'column', 'value', and 'folder' fields")
        self._config['branch_rules'].append(rule)
    
    def update_branch_rule(self, index: int, rule: Dict[str, Any]):
        """Update an existing branch rule."""
        if index < 0 or index >= len(self._config['branch_rules']):
            raise ConfigError(f"Invalid branch rule index: {index}")
        if 'column' not in rule or 'value' not in rule or 'folder' not in rule:
            raise ConfigError("Branch rule must have 'column', 'value', and 'folder' fields")
        self._config['branch_rules'][index] = rule
    
    def remove_branch_rule(self, index: int):
        """Remove a branch rule."""
        if index < 0 or index >= len(self._config['branch_rules']):
            raise ConfigError(f"Invalid branch rule index: {index}")
        del self._config['branch_rules'][index]