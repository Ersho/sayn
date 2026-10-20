"""Local Apple device and Simulator access through Xcode's command-line tools."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import workspace


def available() -> bool:
    if sys.platform != 'darwin' or not shutil.which('xcodebuild'):
        return False
    r = subprocess.run(['xcode-select', '-p'], capture_output=True, text=True, timeout=5)
    return r.returncode == 0 and (Path(r.stdout.strip()) / 'usr/bin/devicectl').exists()


def team() -> str:
    cfg = workspace.config() if workspace.CONFIG.exists() else {}
    return os.environ.get('VIBE_IOS_TEAM', '') or cfg.get('ios_team', '')


def _run(args: list[str], timeout: int = 30) -> str:
    r = subprocess.run(['xcrun', *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-3000:])
    return r.stdout


def _device(args: list[str], timeout: int = 30) -> dict:
    # devicectl documents --json-output as its only supported scripting interface.
    with tempfile.TemporaryDirectory(prefix='sayn-ios-') as tmp:
        dest = Path(tmp) / 'result.json'
        _run(['devicectl', *args, '--timeout', str(timeout), '--json-output', str(dest)], timeout + 5)
        result = json.loads(dest.read_text())
        if result.get('error'):
            raise RuntimeError(json.dumps(result['error'])[-3000:])
        return result.get('result', {})


def list_devices() -> list[dict]:
    if not available():
        return []
    out = []
    try:
        physical = json.loads(_run(['xcdevice', 'list', '--timeout', '2'], 10))
        for d in physical:
            if not d.get('simulator') and d.get('platform') == 'com.apple.platform.iphoneos':
                out.append({'serial': d['identifier'], 'model': d.get('modelName', 'iPhone'),
                            'platform': 'ios', 'kind': 'device', 'state': 'device' if d.get('available') else 'offline'})
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        simulators = json.loads(_run(['simctl', 'list', 'devices', 'available', '--json'], 10))
        for group in simulators.get('devices', {}).values():
            for d in group:
                if d.get('state') != 'Booted':
                    continue
                out.append({'serial': d['udid'], 'model': d['name'] + ' (Simulator)', 'platform': 'ios',
                            'kind': 'simulator', 'state': 'device'})
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        pass
    return out


def installed_packages(device: dict) -> set[str]:
    try:
        if device['kind'] == 'simulator':
            # simctl's property-list output needs conversion before JSON parsing.
            raw = _run(['simctl', 'listapps', device['serial']], 10)
            converted = subprocess.run(['plutil', '-convert', 'json', '-o', '-', '--', '-'],
                                       input=raw, capture_output=True, text=True, check=True, timeout=10)
            return set(json.loads(converted.stdout))
        data = _device(['device', 'info', 'apps', '--device', device['serial']], 10)
        return {a['bundleIdentifier'] for a in data.get('apps', [])}
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return set()


def install(device: dict, app: Path) -> None:
    serial = device['serial']
    if device['kind'] == 'simulator':
        states = json.loads(_run(['simctl', 'list', 'devices', '--json']))
        state = next(d['state'] for group in states['devices'].values() for d in group if d['udid'] == serial)
        if state != 'Booted':
            _run(['simctl', 'boot', serial])
        _run(['simctl', 'bootstatus', serial, '-b'], 180)
        _run(['simctl', 'install', serial, str(app)], 120)
    else:
        _device(['device', 'install', 'app', '--device', serial, str(app)], 120)


def launch(device: dict, package: str) -> None:
    if device['kind'] == 'simulator':
        _run(['simctl', 'launch', device['serial'], package])
    else:
        _device(['device', 'process', 'launch', '--device', device['serial'], '--terminate-existing', package])


def screenshot(device: dict, dest: Path) -> bool:
    if device['kind'] != 'simulator':
        # devicectl has no physical-device screenshot command. Installation still succeeds.
        return False
    _run(['simctl', 'io', device['serial'], 'screenshot', str(dest)])
    return True
