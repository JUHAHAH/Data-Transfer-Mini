"""
Configuration module for loading and validating JSON configuration.
"""
import json
import os
import sys
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


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
    
    def load(self):
        """Load and validate configuration from file."""
        # Try to find config file in multiple locations (priority order)
        config_locations = []
        
        # 1. Same directory as executable (for standalone builds)
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            config_locations.append(os.path.join(os.path.dirname(sys.executable), self.config_path))
        else:
            # Running as script
            config_locations.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.config_path))
        
        # 2. Current working directory
        config_locations.append(os.path.join(os.getcwd(), self.config_path))
        
        # 3. Original path (if absolute)
        if os.path.isabs(self.config_path):
            config_locations.insert(0, self.config_path)
        else:
            config_locations.append(self.config_path)
        
        # 4. PyInstaller resource path (if bundled)
        try:
            resource_path = get_resource_path(self.config_path)
            if resource_path not in config_locations:
                config_locations.append(resource_path)
        except:
            pass
        
        config_found = None
        for location in config_locations:
            if location and os.path.exists(location):
                config_found = location
                break
        
        if not config_found:
            raise ConfigError(f"Configuration file not found: {self.config_path}. Searched in: {', '.join([loc for loc in config_locations if loc])}")
        
        self.config_path = config_found
        
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
