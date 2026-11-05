"""Print the sign-in method this Mac's IT policy requires for Claude Code, if any.

Claude Code reads IT policies ("managed settings") from MDM profiles and from
managed-settings files. When one of them sets forceLoginMethod (for example
"gateway", for an organization's own sign-in page), Claude Code accepts only
that sign-in and refuses API keys. This prints the method, or nothing when the
Mac has no such policy. It only reads.
"""
import getpass
import glob
import json
import os
import plistlib

# The places Claude Code reads managed settings from (macOS, then Linux)
MDM_PROFILES = [
    f"/Library/Managed Preferences/{getpass.getuser()}/com.anthropic.claudecode.plist",
    "/Library/Managed Preferences/com.anthropic.claudecode.plist",
]
MANAGED_FOLDERS = ["/Library/Application Support/ClaudeCode", "/etc/claude-code"]


def read_settings(path):
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f) if path.endswith(".plist") else json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Some profiles carry the settings as one JSON text under "Settings"
    if isinstance(data.get("Settings"), str):
        try:
            data = {**data, **json.loads(data["Settings"])}
        except ValueError:
            pass
    return data


paths = list(MDM_PROFILES)
for folder in MANAGED_FOLDERS:
    paths.append(os.path.join(folder, "managed-settings.json"))
    paths.extend(sorted(glob.glob(os.path.join(folder, "managed-settings.d", "*.json"))))

for path in paths:
    method = read_settings(path).get("forceLoginMethod")
    if isinstance(method, str) and method:
        print(method)
        break
