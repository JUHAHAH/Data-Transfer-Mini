"""
Action handlers for API transmission, file operations, and FTP upload.
"""
import os
import re
import json
import logging
import requests
import ftplib
from ftplib import FTP_TLS, error_perm
import ssl
from typing import Dict, Any, List, Optional
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)


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


class FTPLoginFailedException(Exception):
    """Raised when FTP login fails repeatedly and monitoring should stop."""
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
    
    # Class-level tracking for consecutive login failures across all instances
    _consecutive_login_failures = 0
    _lock = threading.Lock()
    
    def prepare_upload(self, data: Dict[str, Any], config: Dict[str, Any], parser: Any) -> tuple:
        """Compute (remote_path, filename, formatted_data) for one row (no network). Used for batch upload."""
        remote_path_template = config.get('remote_path', '/')
        filename_template = config.get('filename_template', 'data_{timestamp}.txt')
        format_type = config.get('format', 'json')
        branch_folder = parser.get_branch_folder(data)
        formatted_data = parser.format_output(data, format_type, config)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = filename_template.replace('{timestamp}', timestamp)
        filename = _apply_template(filename, data, sanitize_for_path=True)
        remote_path = _apply_template(remote_path_template, data, sanitize_for_path=True)
        remote_path = remote_path.replace('\\', '/')
        if branch_folder:
            remote_path = os.path.join(remote_path, branch_folder).replace('\\', '/')
        if not filename or not filename.strip() or filename.strip() in ('.', '.txt') or filename.startswith('.'):
            filename = f"data_{timestamp}.txt"
        elif not filename.endswith('.txt'):
            filename = filename + '.txt'
        return (remote_path.strip('/') or remote_path, filename, formatted_data)
    
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
        
        # Create temporary local file (one line; we append to remote file like local file action)
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8', newline='\n') as tmp_file:
            tmp_file.write(formatted_data + '\n')
            tmp_file_path = tmp_file.name
        
        ftp = None
        connect_timeout = float(config.get('connect_timeout', 60))
        try:
            # Retry FTP connection/login up to 3 times
            max_retries = 3
            
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"FTP connection attempt {attempt}/{max_retries}: Connecting to {host}:{port} (TLS: {use_tls})")
                    # Connect and login
                    if use_tls:
                        ftp = FTP_TLS()
                        ftp.ssl_version = ssl.PROTOCOL_TLS
                        ftp.connect(host, port, timeout=connect_timeout)
                        logger.debug(f"FTP TLS connected, attempting login as user: {user}")
                        ftp.login(user, password)
                        ftp.prot_p()  # Switch to secure data connection
                    else:
                        ftp = ftplib.FTP()
                        ftp.connect(host, port, timeout=connect_timeout)
                        # Read welcome message if any
                        try:
                            welcome_msg = ftp.getwelcome()
                            logger.debug(f"FTP welcome message: {welcome_msg}")
                        except:
                            pass
                        logger.debug(f"FTP connected, attempting login as user: {user}")
                        # Login first (some servers require login before setting passive mode)
                        ftp.login(user, password)
                        logger.debug(f"FTP login successful, setting passive mode")
                        # Set passive mode after successful login
                        try:
                            ftp.set_pasv(True)  # Enable passive mode (required by many FTP servers)
                        except Exception as pasv_err:
                            logger.warning(f"Failed to set passive mode: {pasv_err}, continuing with active mode")
                    
                    logger.info(f"FTP login successful on attempt {attempt}")
                    # Reset failure counter on successful login
                    with FTPActionHandler._lock:
                        FTPActionHandler._consecutive_login_failures = 0
                    break  # Success, exit retry loop
                
                except error_perm as e:
                    error_msg = str(e)
                    logger.error(f"FTP login failed (attempt {attempt}/{max_retries}): {error_msg}")
                    if attempt == max_retries:
                        # Increment consecutive failure counter
                        with FTPActionHandler._lock:
                            FTPActionHandler._consecutive_login_failures += 1
                            failures = FTPActionHandler._consecutive_login_failures
                        
                        logger.error(f"FTP login failed after {max_retries} attempts (consecutive failures: {failures}).")
                        
                        # After 3 consecutive failures, stop monitoring entirely
                        if failures >= 3:
                            logger.error("FTP login failed 3 times consecutively. Stopping monitoring.")
                            raise FTPLoginFailedException(f"FTP login failed after {max_retries} attempts (3 consecutive failures). Monitoring stopped.")
                        
                        raise ActionError(f"FTP login failed after {max_retries} attempts: {error_msg}")
                    # Close connection if it exists before retrying
                    if ftp:
                        try:
                            ftp.quit()
                        except:
                            try:
                                ftp.close()
                            except:
                                pass
                        ftp = None
                    time.sleep(1)  # Brief delay before retry
                
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"FTP connection error (attempt {attempt}/{max_retries}): {error_msg}")
                    if attempt == max_retries:
                        logger.error(f"FTP connection failed after {max_retries} attempts. Stopping FTP upload.")
                        raise ActionError(f"FTP connection failed after {max_retries} attempts: {error_msg}")
                    if ftp:
                        try:
                            ftp.quit()
                        except:
                            try:
                                ftp.close()
                            except:
                                pass
                        ftp = None
                    time.sleep(1)
            
            if not ftp:
                raise ActionError("Failed to establish FTP connection after all retries")
            
            # Ensure remote directory exists and navigate there.
            # Many servers (e.g. vsFTPd with chroot) show "/" as root; use relative path (e.g. DATA/LH/GNSS).
            remote_rel = remote_path.strip('/')
            cwd_ok = False
            for try_path in (remote_rel, remote_path):
                if not try_path:
                    continue
                try:
                    ftp.cwd(try_path)
                    cwd_ok = True
                    remote_path = try_path  # use working path for logs
                    break
                except Exception:
                    continue
            if not cwd_ok:
                self._create_remote_directory(ftp, remote_rel or remote_path)
                for try_path in (remote_rel, remote_path):
                    if not try_path:
                        continue
                    try:
                        ftp.cwd(try_path)
                        cwd_ok = True
                        remote_path = try_path
                        break
                    except Exception as e:
                        logger.error(f"FTP: Cannot change to directory {try_path}: {e}")
                if not cwd_ok:
                    raise ActionError(f"FTP: Cannot access directory {remote_path}. Check path and permissions.")
            
            # Validate filename (553 often caused by empty or invalid name)
            if not filename or not filename.strip() or filename.strip() in ('.', '.txt') or filename.startswith('.'):
                filename = f"data_{timestamp}.txt"
            elif not filename.endswith('.txt'):
                filename = filename + '.txt'
            
            # Append to remote file (APPE) so multiple rows accumulate like local file; use STOR only if APPE not supported
            logger.debug(f"Appending to file {filename} at {remote_path}")
            stored = False
            with open(tmp_file_path, 'rb') as f:
                def try_upload(cmd_prefix: str, path_arg: str) -> bool:
                    f.seek(0)
                    try:
                        ftp.storbinary(f'{cmd_prefix} {path_arg}', f)
                        return True
                    except ftplib.error_perm:
                        return False
                # Prefer APPE (append): same file gets multiple lines like local file action
                for cmd in ('APPE', 'STOR'):
                    f.seek(0)
                    try:
                        ftp.storbinary(f'{cmd} {filename}', f)
                        stored = True
                        break
                    except ftplib.error_perm as e:
                        err_msg = str(e)
                        if cmd == 'APPE' and '550' in err_msg:
                            continue  # File doesn't exist, try STOR
                        if '553' in err_msg or 'Could not create' in err_msg:
                            for full_path in (
                                (f"{remote_path}/{filename}".replace('//', '/') if remote_path else filename),
                                (f"/{remote_path}/{filename}".replace('//', '/') if remote_path else None),
                            ):
                                if full_path is None:
                                    continue
                                if try_upload(cmd, full_path):
                                    stored = True
                                    break
                            if stored:
                                break
                        if not stored:
                            logger.error(f"FTP {cmd} failed (path={remote_path}, file={filename}): {err_msg}")
                            raise ActionError(f"FTP could not create file: {err_msg}. Check path exists and user has write permission.")
                        break
            if not stored:
                raise ActionError("FTP could not create or append to file. Check path and permissions.")
            ftp.quit()
            logger.info(f"Successfully appended to FTP file: {remote_path}/{filename}")
            print(f"Successfully appended to FTP file: {remote_path}/{filename}")
            return True
        
        except ActionError:
            # Re-raise ActionError (login failures) without wrapping
            raise
        
        except Exception as e:
            logger.error(f"Failed to upload file to FTP: {e}")
            print(f"Failed to upload to FTP: {e}")
            if ftp:
                try:
                    ftp.quit()
                except:
                    try:
                        ftp.close()
                    except:
                        pass
            raise ActionError(f"FTP upload failed: {e}")
        
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_file_path)
            except:
                pass
    
    def upload_batch(self, config: Dict[str, Any], remote_path: str, filename: str, lines: List[str]) -> None:
        """Upload multiple lines to one remote file in one connection (one APPE/STOR)."""
        from io import BytesIO
        content = ('\n'.join(lines) + '\n').encode('utf-8')
        blob = BytesIO(content)
        host = config.get('host')
        port = int(config.get('port', 21))
        user = config.get('user')
        password = config.get('password')
        use_tls = config.get('use_tls', False)
        connect_timeout = float(config.get('connect_timeout', 60))
        remote_path = (remote_path or '').strip('/')
        ftp = None
        try:
            if use_tls:
                ftp = FTP_TLS()
                ftp.ssl_version = ssl.PROTOCOL_TLS
                ftp.connect(host, port, timeout=connect_timeout)
                ftp.login(user, password)
                ftp.prot_p()
            else:
                ftp = ftplib.FTP()
                ftp.connect(host, port, timeout=connect_timeout)
                ftp.login(user, password)
                try:
                    ftp.set_pasv(True)
                except Exception:
                    pass
            with FTPActionHandler._lock:
                FTPActionHandler._consecutive_login_failures = 0
            remote_rel = remote_path.strip('/')
            cwd_ok = False
            for try_path in (remote_rel, remote_path):
                if not try_path:
                    continue
                try:
                    ftp.cwd(try_path)
                    cwd_ok = True
                    remote_path = try_path
                    break
                except Exception:
                    continue
            if not cwd_ok:
                self._create_remote_directory(ftp, remote_rel or remote_path)
                for try_path in (remote_rel, remote_path):
                    if not try_path:
                        continue
                    try:
                        ftp.cwd(try_path)
                        cwd_ok = True
                        remote_path = try_path
                        break
                    except Exception as e:
                        logger.error(f"FTP: Cannot change to directory {try_path}: {e}")
                if not cwd_ok:
                    raise ActionError(f"FTP: Cannot access directory {remote_path}. Check path and permissions.")
            stored = False
            for cmd in ('APPE', 'STOR'):
                blob.seek(0)
                try:
                    ftp.storbinary(f'{cmd} {filename}', blob)
                    stored = True
                    break
                except ftplib.error_perm as e:
                    err_msg = str(e)
                    if cmd == 'APPE' and '550' in err_msg:
                        continue
                    if '553' in err_msg or 'Could not create' in err_msg:
                        for full_path in (
                            (f"{remote_path}/{filename}".replace('//', '/') if remote_path else filename),
                            (f"/{remote_path}/{filename}".replace('//', '/') if remote_path else None),
                        ):
                            if full_path is None:
                                continue
                            blob.seek(0)
                            try:
                                ftp.storbinary(f'{cmd} {full_path}', blob)
                                stored = True
                                break
                            except ftplib.error_perm:
                                pass
                    if not stored:
                        raise ActionError(f"FTP could not create file: {err_msg}. Check path and permissions.")
                    break
            if not stored:
                raise ActionError("FTP could not create or append to file.")
            ftp.quit()
            logger.info(f"Successfully uploaded batch to FTP: {remote_path}/{filename} ({len(lines)} lines)")
        except ActionError:
            raise
        except Exception as e:
            logger.error(f"FTP batch upload failed: {e}")
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    try:
                        ftp.close()
                    except Exception:
                        pass
            raise ActionError(f"FTP batch upload failed: {e}")
    
    def _create_remote_directory(self, ftp: ftplib.FTP, remote_path: str):
        """Create remote directory structure (relative path, one segment at a time for chrooted servers)."""
        path = remote_path.strip('/')
        if not path:
            return
        parts = [p for p in path.split('/') if p]
        for part in parts:
            try:
                ftp.cwd(part)
            except Exception:
                try:
                    ftp.mkd(part)
                    ftp.cwd(part)
                except ftplib.error_perm as e:
                    logger.warning(f"FTP MKD {part} failed: {e}")
                    try:
                        ftp.cwd(part)
                    except Exception:
                        raise


class ActionExecutor:
    """Executes configured actions."""
    
    def __init__(self, actions_config: List[Dict[str, Any]], ftp_global_defaults: Optional[Dict[str, Any]] = None):
        """
        Initialize action executor.
        
        Args:
            actions_config: List of action configurations
            ftp_global_defaults: Optional root-level FTP defaults (e.g. connect_timeout) merged into each FTP action
        """
        self.actions_config = actions_config
        self._ftp_global_defaults = dict(ftp_global_defaults) if ftp_global_defaults else {}
        self.handlers = {
            'api': APIActionHandler(),
            'file': FileActionHandler(),
            'ftp': FTPActionHandler()
        }
        # FTP batch: when active, FTP actions buffer instead of uploading per row
        self._ftp_batch: Optional[Dict[int, Dict[tuple, List[str]]]] = None  # action_ix -> (path, filename) -> lines
    
    def _ftp_merged_config(self, action_ix: int) -> Dict[str, Any]:
        """Merge root FTP defaults with the action entry (action wins on key conflicts)."""
        base = self.actions_config[action_ix]
        return {**self._ftp_global_defaults, **base}
    
    def start_ftp_batch(self) -> None:
        """Start buffering FTP uploads; flush with flush_ftp_buffers()."""
        self._ftp_batch = {}
    
    def flush_ftp_buffers(self) -> None:
        """Upload all buffered FTP data (one connection per file, one APPE per file)."""
        if not self._ftp_batch:
            return
        ftp_handler = self.handlers['ftp']
        for action_ix, file_buffers in self._ftp_batch.items():
            config = self._ftp_merged_config(action_ix)
            for (remote_path, filename), lines in file_buffers.items():
                if not lines:
                    continue
                try:
                    ftp_handler.upload_batch(config, remote_path, filename, lines)
                except ActionError as e:
                    print(f"FTP batch upload failed: {e}")
                    raise
        self._ftp_batch = None
    
    def execute_actions(self, data: Dict[str, Any], parser: Any) -> List[bool]:
        """
        Execute all configured actions for a data row.
        When FTP batch is active, FTP actions buffer; other actions run immediately.
        """
        results = []
        
        for action_ix, action_config in enumerate(self.actions_config):
            action_type = action_config.get('type')
            handler = self.handlers.get(action_type)
            
            if not handler:
                print(f"Warning: Unknown action type: {action_type}")
                results.append(False)
                continue
            
            try:
                if action_type == 'ftp' and self._ftp_batch is not None:
                    # Buffer for batch upload
                    merged = self._ftp_merged_config(action_ix)
                    remote_path, filename, formatted_data = handler.prepare_upload(data, merged, parser)
                    key = (remote_path, filename)
                    if action_ix not in self._ftp_batch:
                        self._ftp_batch[action_ix] = {}
                    if key not in self._ftp_batch[action_ix]:
                        self._ftp_batch[action_ix][key] = []
                    self._ftp_batch[action_ix][key].append(formatted_data)
                    results.append(True)
                else:
                    cfg = self._ftp_merged_config(action_ix) if action_type == 'ftp' else action_config
                    success = handler.execute(data, cfg, parser)
                    results.append(success)
            except ActionError as e:
                print(f"Action execution failed: {e}")
                results.append(False)
            except Exception as e:
                print(f"Unexpected error executing action: {e}")
                results.append(False)
        
        return results
