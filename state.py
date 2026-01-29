"""
State management module for tracking last processed ID.
"""
import json
import os
import threading
from typing import Optional


class StateManager:
    """Manages persistent state for tracking last processed database ID."""
    
    def __init__(self, state_file: str = "state.json"):
        """
        Initialize state manager.
        
        Args:
            state_file: Path to the state file
        """
        self.state_file = state_file
        self._lock = threading.Lock()
        self._state: dict = {}
        self.load()
    
    def load(self):
        """Load state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                # If state file is corrupted, start fresh
                print(f"Warning: Could not load state file ({e}). Starting with fresh state.")
                self._state = {}
        else:
            self._state = {}
    
    def get_last_processed_id(self, table_name: Optional[str] = None) -> Optional[int]:
        """
        Get the last processed ID.
        
        Args:
            table_name: Optional table name for multi-table tracking
        
        Returns:
            Last processed ID or None if not set
        """
        key = f"last_processed_id_{table_name}" if table_name else "last_processed_id"
        return self._state.get(key)
    
    def set_last_processed_id(self, last_id: int, table_name: Optional[str] = None):
        """
        Set the last processed ID.
        
        Args:
            last_id: The last processed ID
            table_name: Optional table name for multi-table tracking
        """
        key = f"last_processed_id_{table_name}" if table_name else "last_processed_id"
        with self._lock:
            self._state[key] = last_id
            self._save()
    
    def _save(self):
        """Save state to file atomically."""
        # Write to temporary file first, then rename (atomic on most systems)
        temp_file = f"{self.state_file}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, indent=2)
            
            # Atomic rename
            if os.name == 'nt':  # Windows
                # On Windows, remove target first if it exists
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)
                os.rename(temp_file, self.state_file)
            else:  # Unix-like
                os.rename(temp_file, self.state_file)
        except Exception as e:
            print(f"Error saving state: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
    
    def reset(self, table_name: Optional[str] = None):
        """
        Reset state for a table or all state.
        
        Args:
            table_name: Optional table name to reset, or None to reset all
        """
        with self._lock:
            if table_name:
                key = f"last_processed_id_{table_name}"
                if key in self._state:
                    del self._state[key]
            else:
                self._state = {}
            self._save()
    
    def get_state(self) -> dict:
        """Get the entire state dictionary."""
        return self._state.copy()
