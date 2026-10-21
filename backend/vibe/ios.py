"""Local Apple device and Simulator access through Xcode's command-line tools."""
import json
import os
import plistlib
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


def ready() -> bool:
    """Everything an iOS build needs on this Mac: full Xcode plus CocoaPods."""
    return available() and shutil.which('pod') is not None


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


def _preferences() -> dict:
    if sys.platform != 'darwin':
        return {}
    try:
        # Let macOS locate this user's preferences, even when the launcher overrides HOME.
        result = subprocess.run(['defaults', 'export', 'com.apple.dt.Xcode', '-'],
                                capture_output=True, check=True, timeout=5)
        return plistlib.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def teams(prefs: dict | None = None) -> list[dict]:
    """Signing teams of the Apple accounts added in Xcode → Settings → Accounts."""
    if prefs is None:
        prefs = _preferences()
    found = {}
    # Xcode versions differ in the key; both hold {account: [team, ...]}.
    for key in ('IDEProvisioningTeamByIdentifier', 'IDEProvisioningTeams'):
        for account in prefs.get(key, {}).values():
            for t in account if isinstance(account, list) else []:
                if isinstance(t, dict) and t.get('teamID'):
                    found[t['teamID']] = {'id': t['teamID'], 'name': t.get('teamName', ''),
                                          'personal': bool(t.get('isFreeProvisioningTeam'))}
    return list(found.values())


def _phones() -> list[dict]:
    """Connected physical iPhones/iPads as devicectl reports them, including unpaired ones."""
    try:
        listed = _device(['list', 'devices'], 10).get('devices', [])
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return []
    return [d for d in listed if d.get('hardwareProperties', {}).get('platform') == 'iOS'
            and d.get('hardwareProperties', {}).get('reality') == 'physical'
            and d.get('connectionProperties', {}).get('transportType')]


def checks() -> list[dict]:
    """The iPhone/iPad setup checkpoints in the order a user completes them; `hint` is the next step."""
    xcode = available() and subprocess.run(['xcodebuild', '-checkFirstLaunchStatus'],
                                           capture_output=True, timeout=10).returncode == 0
    prefs = _preferences()
    found = teams(prefs)
    accounts = prefs.get('DVTDeveloperAccountManagerAppleIDLists', {})
    has_account = bool(found) or any(
        isinstance(account, dict) and bool(account.get('identifier'))
        for entries in accounts.values() if isinstance(entries, list)
        for account in entries)
    phones = _phones() if xcode else []
    paired = [d for d in phones if d.get('connectionProperties', {}).get('pairingState') == 'paired']
    names = ', '.join(f"{t['name']} ({t['id']})" for t in found)
    return [
        {'id': 'xcode', 'label': 'Xcode installed and set up', 'ok': xcode,
         'hint': 'Install Xcode from the App Store and open it once to finish setup. Then choose it in '
                 'Xcode → Settings → Locations → Command Line Tools.'},
        {'id': 'pods', 'label': 'CocoaPods installed', 'ok': shutil.which('pod') is not None,
         'hint': 'In Terminal run: brew install cocoapods (without Homebrew: sudo gem install cocoapods). '
                 'Then restart sayn.'},
        {'id': 'account', 'label': 'Apple account added to Xcode', 'ok': has_account,
         'hint': 'In Xcode → Settings → Accounts, click + and sign in with your Apple ID. A free account works.'},
        {'id': 'team', 'label': 'Signing team chosen in sayn', 'ok': bool(team()),
         'hint': (f'Found in Xcode: {names}. ' if names else '')
                 + "Choose your team in sayn's Settings → iPhone and iPad signing."},
        {'id': 'connected', 'label': 'iPhone or iPad connected', 'ok': bool(phones),
         'hint': 'Plug it into this Mac with a cable and unlock it.'},
        {'id': 'trusted', 'label': 'iPhone or iPad trusts this Mac', 'ok': bool(paired),
         'hint': 'Unlock it, tap Trust on "Trust This Computer?" and enter its passcode. '
                 'No prompt? Unplug it and plug it back in.'},
        {'id': 'devmode', 'label': 'Developer Mode on', 'ok': any(
            d.get('deviceProperties', {}).get('developerModeStatus') == 'enabled' for d in paired),
         'hint': 'On the iPhone: Settings → Privacy & Security → Developer Mode → On, restart and confirm. '
                 'Not listed? Open Xcode → Window → Devices and Simulators with it plugged in, then look again.'},
    ]


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


if __name__ == '__main__':
    # scripts/setup.sh prints this checklist on macOS.
    for c in checks():
        print('   \033[32mok\033[0m  ' + c['label'] if c['ok'] else f"   --  {c['label']}\n       {c['hint']}")
