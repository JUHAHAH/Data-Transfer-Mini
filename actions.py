"""
Action handlers for API transmission, file operations, and FTP upload.
"""
import os
import re
import json
import requests
import ftplib
from ftplib import FTP_TLS
import ssl
from typing import Dict, Any, List, Optional
from datetime import datetime
import threading
import time


def _apply_template(template: str, data: Dict[str, Any], sanitize_for_path: bool = False) -> str:
    """
    Replace {column_name} placeholders in template with values from data.
    Uses alphanumeric + underscore only for placeholder names.
    """
    if not template:
        return template

    def replace_placeholder(match: re.Match) -> str:
        key = match.group(1)
        value = str(data.get(key, ''))
        if sanitize_for_path:
            value = value.replace('\\', '_').replace('/', '_').replace('..', '_')
        return value

    return re.sub(r'\{(\w+)\}', replace_placeholder, template)


def _sanitize_resolved_path(resolved: str) -> str:
    """Reject path traversal; normalize path parts that contain '..'."""
    parts = resolved.replace('\\', '/').split('/')
    out = []
    for p in parts:
        if p == '..':
            continue
        if p == '.':
            continue
        out.append(p)
    if not out:
        return '.'
    return '/'.join(out) if '/' in resolved else os.path.join(*out)


class ActionError(Exception):
    """Raised when action execution fails."""
    pass


class ActionHandler:
    """Base class for action handlers."""
    
    def execute(self, data: Dict[str, Any], config: Dict[str, Any], parser: Any) -> bool:
        """
        Execute the action.
        
        Args:
            data: Parsed row data
            config: Action configuration
            parser: DataParser instance for formatting
        
        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError


class APIActionHandler(ActionHandler):
    """Handler for API transmission."""
    
    def execute(self, data: Dict[str, Any], config: Dict[str, Any], parser: Any) -> bool:
        """
        Send data to API endpoint.
        
        Args:
            data: Parsed row data
            config: API action configuration
            parser: DataParser instance
        
        Returns:
            True if successful
        """
        url = config.get('url')
        method = config.get('method', 'POST').upper()
        headers = config.get('headers', {})
        timeout = config.get('timeout', 30)
        max_retries = config.get('max_retries', 3)
        retry_delay = config.get('retry_delay', 1.0)
        
        # Format data as JSON
        payload = json.dumps(data, default=str, ensure_ascii=False)
        
        # Set default headers
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'
        
        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    data=payload,
                    headers=headers,
                    timeout=timeout
                )
                response.raise_for_status()
                print(f"Successfully sent data to API: {url}")
                return True
            
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"API request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to send data to API after {max_retries} attempts: {e}")
                    raise ActionError(f"API transmission failed: {e}")
        
        return False


class FileActionHandler(ActionHandler):
    """Handler for file appending."""
    
    def __init__(self):
        """Initialize file handler with thread lock."""
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
    
    def _get_lock(self, file_path: str) -> threading.Lock:
        """Get or create a lock for a file path."""
        with self._locks_lock:
            if file_path not in self._locks:
                self._locks[file_path] = threading.Lock()
            return self._locks[file_path]
    
    def execute(self, data: Dict[str, Any], config: Dict[str, Any], parser: Any) -> bool:
        """
        Append data to file.
        
        Path may contain {column_name} placeholders; each row can write to a different file
        (e.g. output/{id}.txt). Values used in path are sanitized for safety.
        
        Args:
            data: Parsed row data
            config: File action configuration
            parser: DataParser instance
        
        Returns:
            True if successful
        """
        path_template = config.get('path')
        file_path = _apply_template(path_template, data, sanitize_for_path=True)
        file_path = _sanitize_resolved_path(file_path)
        format_type = config.get('format', 'json')
        branch_folder = parser.get_branch_folder(data)
        
        # Apply branch folder if specified
        if branch_folder:
            # Modify path to include branch folder
            directory = os.path.dirname(file_path)
            filename = os.path.basename(file_path)
            
            # Create branch directory if it doesn't exist
            branch_dir = os.path.join(directory, branch_folder)
            os.makedirs(branch_dir, exist_ok=True)
            
            file_path = os.path.join(branch_dir, filename)
        else:
            # Ensure directory exists
            directory = os.path.dirname(file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        
        # Format data - pass action config for structured formats
        formatted_data = parser.format_output(data, format_type, config)
        
        # Append to file with locking
        lock = self._get_lock(file_path)
        with lock:
            try:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(formatted_data + '\n')
                print(f"Successfully appended data to file: {file_path}")
                return True
            except IOError as e:
                print(f"Failed to write to file {file_path}: {e}")
                raise ActionError(f"File write failed: {e}")


class FTPActionHandler(ActionHandler):
    """Handler for FTP upload with TLS/SSL support."""
    
    def execute(self, data: Dict[str, Any], config: Dict[str, Any], parser: Any) -> bool:
        """
        Upload data as file to FTP server.
        
        Args:
            data: Parsed row data
            config: FTP action configuration
            parser: DataParser instance
        
        Returns:
            True if successful
        """
        host = config.get('host')
        port = config.get('port', 21)
        user = config.get('user')
        password = config.get('password')
        remote_path_template = config.get('remote_path', '/')
        filename_template = config.get('filename_template', 'data_{timestamp}.txt')
        use_tls = config.get('use_tls', False)
        format_type = config.get('format', 'json')
        branch_folder = parser.get_branch_folder(data)
        
        # Format data - pass action config for structured formats
        formatted_data = parser.format_output(data, format_type, config)
        
        # Generate filename: {timestamp} and {column_name} placeholders
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = filename_template.replace('{timestamp}', timestamp)
        filename = _apply_template(filename, data, sanitize_for_path=True)
        
        # Remote path may contain {column_name} placeholders
        remote_path = _apply_template(remote_path_template, data, sanitize_for_path=True)
        remote_path = remote_path.replace('\\', '/')
        
        # Apply branch folder to remote path if specified
        if branch_folder:
            remote_path = os.path.join(remote_path, branch_folder).replace('\\', '/')
        
        # Create temporary local file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tmp_file:
            tmp_file.write(formatted_data)
            tmp_file_path = tmp_file.name
        
        try:
            # Connect and upload
            if use_tls:
                ftp = FTP_TLS()
                ftp.ssl_version = ssl.PROTOCOL_TLS
                ftp.connect(host, port)
                ftp.login(user, password)
                ftp.prot_p()  # Switch to secure data connection
            else:
                ftp = ftplib.FTP()
                ftp.connect(host, port)
                ftp.login(user, password)
            
            # Ensure remote directory exists
            try:
                ftp.cwd(remote_path)
            except:
                # Create directory if it doesn't exist
                self._create_remote_directory(ftp, remote_path)
                ftp.cwd(remote_path)
            
            # Upload file
            with open(tmp_file_path, 'rb') as f:
                ftp.storbinary(f'STOR {filename}', f)
            
            ftp.quit()
            print(f"Successfully uploaded file to FTP: {remote_path}/{filename}")
            return True
        
        except Exception as e:
            print(f"Failed to upload to FTP: {e}")
            raise ActionError(f"FTP upload failed: {e}")
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_file_path)
            except:
                pass
    
    def _create_remote_directory(self, ftp: ftplib.FTP, remote_path: str):
        """Create remote directory structure."""
        parts = remote_path.strip('/').split('/')
        current_path = ''
        
        for part in parts:
            if not part:
                continue
            current_path += '/' + part
            try:
                ftp.cwd(current_path)
            except:
                try:
                    ftp.mkd(current_path)
                    ftp.cwd(current_path)
                except:
                    pass


class ActionExecutor:
    """Executes configured actions."""
    
    def __init__(self, actions_config: List[Dict[str, Any]]):
        """
        Initialize action executor.
        
        Args:
            actions_config: List of action configurations
        """
        self.actions_config = actions_config
        self.handlers = {
            'api': APIActionHandler(),
            'file': FileActionHandler(),
            'ftp': FTPActionHandler()
        }
    
    def execute_actions(self, data: Dict[str, Any], parser: Any) -> List[bool]:
        """
        Execute all configured actions for a data row.
        
        Args:
            data: Parsed row data
            parser: DataParser instance
        
        Returns:
            List of success flags for each action
        """
        results = []
        
        for action_config in self.actions_config:
            action_type = action_config.get('type')
            handler = self.handlers.get(action_type)
            
            if not handler:
                print(f"Warning: Unknown action type: {action_type}")
                results.append(False)
                continue
            
            try:
                success = handler.execute(data, action_config, parser)
                results.append(success)
            except ActionError as e:
                print(f"Action execution failed: {e}")
                results.append(False)
            except Exception as e:
                print(f"Unexpected error executing action: {e}")
                results.append(False)
        
        return results
