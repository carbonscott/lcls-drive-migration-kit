"""Mark the kit folder as trusted in the kit's own Claude Code config.

Usage: trust_folder.py CONFIG_JSON KIT_FOLDER

./gdm claude runs this before starting Claude Code, so the person is not asked
"Do you trust this folder?" (that question starts on "No, exit", which is easy to
get wrong). It is the same setting Claude Code records when the person answers
yes. It only touches the kit's own config (.sandbox/claude/.claude.json).
"""
import json
import os
import sys

config_path, kit_folder = sys.argv[1], sys.argv[2]

config = {}
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            config = json.load(f)
    except ValueError:
        sys.exit(0)   # a file we cannot read is left alone; Claude asks the question instead

projects = config.setdefault("projects", {})
for path in {kit_folder, os.path.realpath(kit_folder)}:
    projects.setdefault(path, {})["hasTrustDialogAccepted"] = True

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
