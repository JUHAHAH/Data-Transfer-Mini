"""
Test FTP connection with config from dist/config.json.
Run from project root: python test_ftp_connect.py
"""
import json
import os
import sys
import ssl

# Load config from dist/config.json
config_path = os.path.join(os.path.dirname(__file__), 'dist', 'config.json')
if not os.path.isfile(config_path):
    config_path = 'config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

actions = config.get('actions', [])
ftp_config = None
for a in actions:
    if a.get('type') == 'ftp':
        ftp_config = a
        break
if not ftp_config:
    print("No FTP action in config")
    sys.exit(1)

host = ftp_config.get('host')
port = ftp_config.get('port', 21)
user = ftp_config.get('user')
password = ftp_config.get('password')
use_tls = ftp_config.get('use_tls', False)
remote_path = ftp_config.get('remote_path', '/')

print(f"Config: host={host} port={port} user={user} use_tls={use_tls}")
print()

# Test 1: Plain FTP (no TLS) on port 21
print("=== Test 1: Plain FTP (no TLS) on port 21 ===")
try:
    import ftplib
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=10)
    print("  Connect OK. Welcome:", getattr(ftp, 'welcome', '') or ftp.getwelcome()[:80])
    ftp.login(user, password)
    print("  Login OK")
    ftp.set_pasv(True)
    try:
        ftp.cwd(remote_path)
        print("  CWD", remote_path, "OK")
    except Exception as e:
        print("  CWD failed:", e)
    ftp.quit()
    print("  Result: SUCCESS (use_tls should be false in config)")
except Exception as e:
    print("  Failed:", e)
print()

# Test 2: Explicit TLS (FTP_TLS) on port 21
print("=== Test 2: Explicit TLS (FTP_TLS) on port 21 ===")
try:
    from ftplib import FTP_TLS
    ftp = FTP_TLS()
    ftp.ssl_version = ssl.PROTOCOL_TLS_CLIENT
    ftp.connect(host, port, timeout=10)
    print("  Connect OK")
    ftp.login(user, password)
    ftp.prot_p()
    print("  Login OK")
    try:
        ftp.cwd(remote_path)
        print("  CWD", remote_path, "OK")
    except Exception as e:
        print("  CWD failed:", e)
    ftp.quit()
    print("  Result: SUCCESS (use_tls true)")
except Exception as e:
    print("  Failed:", e)
print()

# Test 3: Implicit TLS on port 990 (common for FTPS)
print("=== Test 3: Implicit TLS on port 990 ===")
try:
    from ftplib import FTP_TLS
    ftp = FTP_TLS()
    ftp.ssl_version = ssl.PROTOCOL_TLS_CLIENT
    ftp.connect(host, 990, timeout=10)
    ftp.login(user, password)
    ftp.prot_p()
    print("  Login OK")
    try:
        ftp.cwd(remote_path)
        print("  CWD", remote_path, "OK")
    except Exception as e:
        print("  CWD failed:", e)
    ftp.quit()
    print("  Result: SUCCESS (use port 990 + use_tls true)")
except Exception as e:
    print("  Failed:", e)

print()
print("Done. Use the test that succeeded to set your config.")
