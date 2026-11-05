# LCLS drive migration kit

**Folder owner:** open **START-HERE.html**; everything you need is at the top of
it. You type `./gdm setup` once and `./gdm claude` each time; Claude then guides
you through the plan.

**Get the kit:** [download the ZIP](https://github.com/carbonscott/lcls-drive-migration-kit/archive/refs/heads/main.zip),
double-click it to unzip (somewhere outside iCloud Drive, for example your home
folder), and open START-HERE.html in the unzipped folder.

The rest of this file is a reference for whoever supports the folder owner.

This folder is a small, self-contained toolkit. Everything it installs or stores
stays inside this folder. It can **read** Google Drive and make **copies**; it has
no code to delete, move or re-share anything.

## Setup (about 10 minutes, Mac, SLAC VPN on)

In Terminal, in this folder: `./gdm setup`. It installs uv, a private Python and
rclone, then runs `install-claude-lcls.sh` (alone: `./gdm install-claude`):

- Downloads Claude Code into `.sandbox/bin/` (about 300 MB; nothing is installed
  on the Mac; checked against Anthropic's SHA-256) and writes
  `.sandbox/claude/settings.json` from `claude-settings.template.json`.
- Reads the Mac's IT policy for Claude Code (managed settings: the MDM profiles in
  `/Library/Managed Preferences/`, and `managed-settings.json` or
  `managed-settings.d/` in `/Library/Application Support/ClaudeCode/`), with
  `tools/claude_login_policy.py`.
  - **Policy requires a sign-in** (`forceLoginMethod`, e.g. `"gateway"` on
    SLAC-managed Macs): Claude Code refuses API keys there, so no key and no SLAC
    gateway settings. The owner signs in the first time Claude starts (`/login`).
  - **No such policy:** asks for a SLAC AI key (hidden input; paste markers and
    spaces are stripped; checked with the gateway; saved only in
    `.sandbox/config/`), adds the SLAC AI gateway address and model names, and
    asks Claude a one-line test question. Give the owner the key in person, not
    by email.
  - **No key (just Return), or `./gdm setup --claude-login`:** offers to sign in
    with a Claude account right away (`claude auth login`: personal Pro/Max, or
    the organization's Claude for Education, Team or Enterprise, which the
    sign-in page routes by email), then the same test question. `s` skips; Claude
    then asks at first start. The choice is remembered on later runs;
    `./gdm setup --slac-key` switches back. The sign-in lives in the macOS
    Keychain as `Claude Code-credentials-<first 8 hex of sha256 of
    .sandbox/claude's path>`, separate from other Claude logins; `./gdm clean`
    deletes that one entry.

`./gdm claude` then starts Claude. It marks the kit folder as trusted in the kit's
own Claude config (`tools/trust_folder.py`), so the "trust this folder?" question,
whose answer starts on "No, exit", never appears. The first start shows only the
color style and the security notes (Return, Return), plus the sign-in on
policy Macs.

## Later

- Update Claude Code: `./gdm setup` or `./gdm install-claude` (press Return to keep the key).
  `./gdm install-claude stable` or `./gdm install-claude 2.1.285` picks a version.
- SLAC tokens (plan step 2 only): Claude checks them and, when one is missing or
  expired, asks the owner to type `./gdm confluence-login` or `./gdm jira-login`
  in a second Terminal window.
- Resume the last conversation: `./gdm claude --continue`.
- Finished: `./gdm clean` removes `.sandbox/` (programs, Claude settings and
  history, key, Google logins, SLAC tokens) after typing `yes`; keeps `results/`;
  refuses inside a Claude session; a linked `.sandbox` loses only the link.
  Google still lists the "rclone" access at myaccount.google.com/connections.

## How Claude is kept contained

Always start Claude from this folder with `./gdm claude`, not plain `claude`. That
runs only the kit's own copy, keeps its settings, history, temporary files and key
in `.sandbox/`, turns off its usage statistics, error reports and auto-updates,
and ignores any other Claude login, key or gateway on the Mac.

`CLAUDE.md` tells Claude the plan and the safety rules; `.claude/settings.json`
keeps it asking before safety copies and Google logins (ask rules, which auto
mode honors) and stops it from running rclone, reading login files, changing the
kit's tools or its own settings, running setup or clean, or starting Claude
itself. These rules apply to any Claude Code
session started in this folder, including your own: to debug the kit with your
own Claude, start it from the folder above, or use a plain Terminal.

## Running the steps without Claude

```bash
./gdm login you@stanford.edu                  # read-only Google login
./gdm inventory "https://drive.google.com/drive/folders/<your folder ID>"
./gdm help                                    # all commands
```

The inventory is saved in `results/inventory-<time>/`. Every step's command is in
START-HERE.html, Appendix I.

## What is in here

| Path | What it is |
|---|---|
| `START-HERE.html` | the plan, written for the folder owner, with appendix and references |
| `gdm` | the one command; `./gdm help` lists what it does |
| `setup.sh` | installs uv, a private Python and rclone into `.sandbox/` (needs only curl and unzip) |
| `tools/drive_api.py` | the only code that talks to Google Drive (read and copy only) |
| `tools/inventory.py` | step 1: every item and its owner, plus folder sharing |
| `tools/safety_copy.py` | step 3: copies of at-risk files (preview unless `--yes`) |
| `tools/verify.py` | steps 5 and 8: is every old link still working? |
| `tools/gdrive_login.py` | Google login into a local profile |
| `tools/claude_login_policy.py` | reads the Mac's Claude Code IT policy: sign-in or key? |
| `tools/trust_folder.py` | marks the kit folder as trusted in the kit's own Claude config |
| `install-claude-lcls.sh` | `./gdm install-claude`: Claude Code, SLAC gateway settings and key, all in `.sandbox/` (simplified from the LCLS team's installer in github.com/carbonscott/deploy-opencode) |
| `claude-settings.template.json` | the settings claude-lcls uses: the template inside deploy-opencode's `claude/install-claude-lcls.sh` (9224681), with auto mode, the one-hour cache, fullscreen display and auto-memory off |
| `CLAUDE.md`, `.claude/settings.json` | instructions and guardrails for Claude Code |
| `practice/` | made-up data and the 75-second walkthrough recording embedded in START-HERE.html ("See it in action"); `transcript.txt` is the text version |
| `.claude/skills/` | SLAC confluence-search (5028e30) and jira-search (bce9f83), read-only, from github.com/carbonscott; `env.local` added so they use the kit's own uv |

Created when the kit is used, all inside this folder: `.sandbox/` (programs,
Claude Code itself, a private Python, Claude Code's settings and history in
`.sandbox/claude/`, its temporary files in `.sandbox/tmp/`, and the keys and logins
in `.sandbox/config/`, readable only by the owner) and `results/`. Once set up, the
folder holds logins: never send it to anyone. `./gdm clean` removes all of
`.sandbox/` after the person types `yes`, and keeps `results/`.
