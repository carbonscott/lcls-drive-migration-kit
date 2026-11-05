#!/usr/bin/env bash
# Install Claude Code for this kit. Runs as the second half of ./gdm setup, or
# alone as ./gdm install-claude.
#
# A kit-sized version of claude/install-claude-lcls.sh from
# github.com/carbonscott/deploy-opencode, without pass or keyswitch.
# Everything stays inside this folder:
#   .sandbox/bin/claude             Claude Code itself, downloaded from Anthropic
#                                   and checked against Anthropic's SHA-256
#   .sandbox/claude/settings.json   settings, from claude-settings.template.json
#   .sandbox/config/slac-ai-key     the SLAC AI key, when one is used (only your
#                                   account can read it)
#
# How Claude Code signs in depends on the Mac:
#   - Macs whose IT policy for Claude Code requires a sign-in (forceLoginMethod
#     in managed settings, e.g. "gateway" for the organization's sign-in page):
#     no key. The person signs in the first time Claude starts. Claude Code
#     refuses API keys on such Macs, so the kit does not set one.
#   - Other Macs: a SLAC AI key, used through SLAC's AI gateway
#     (ai-api.slac.stanford.edu, on the SLAC network or VPN).
#   - On request, where no IT policy decides: --claude-login signs in with a
#     Claude account (Pro, Max, Team, Enterprise) or an Anthropic Console account
#     instead of the SLAC key. Later runs remember it; --slac-key switches back.
#
# Safe to run again: it updates Claude Code to the newest release, refreshes the
# settings from the template, and keeps the key unless a new one is pasted.
#
#   ./gdm install-claude                 the newest release
#   ./gdm install-claude stable          Anthropic's "stable" channel (about a week behind)
#   ./gdm install-claude 2.1.285         one exact version
#   ./gdm install-claude --claude-login  (or ./gdm setup --claude-login) Claude account sign-in
#   ./gdm install-claude --slac-key      back to the SLAC AI key
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Always run through ./gdm, so this script sees the kit's own environment
if [ -z "${GDM_SANDBOX:-}" ]; then
  exec "$KIT/gdm" install-claude "$@"
fi
SANDBOX="$GDM_SANDBOX"

RELEASES="https://downloads.claude.ai/claude-code-releases"
WANTED="latest"
choice=""   # "sign-in" for --claude-login, "key" for --slac-key
for arg in "$@"; do
  case "$arg" in
    --claude-login) choice="sign-in" ;;
    --slac-key)     choice="key" ;;
    -*)             echo "Unknown option: $arg (use --claude-login or --slac-key)" >&2; exit 2 ;;
    *)              WANTED="$arg" ;;
  esac
done
CLAUDE_BIN="$SANDBOX/bin/claude"
SETTINGS="$SANDBOX/claude/settings.json"
KEY_FILE="$SANDBOX/config/slac-ai-key"

py() { uv run --quiet --no-project python "$@"; }   # the kit's own Python
die() { echo "  ✗ $*" >&2; exit 1; }

# ─── 1. Claude Code ───────────────────────────────────────────────────────
echo
echo "── Claude Code"
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  platform="darwin-arm64" ;;
  Darwin-x86_64) platform="darwin-x64" ;;
  Linux-x86_64)  platform="linux-x64" ;;
  Linux-aarch64) platform="linux-arm64" ;;
  *) die "Unsupported computer: $(uname -s) $(uname -m)" ;;
esac

case "$WANTED" in
  latest|stable) version="$(curl -fsSL -m 30 "$RELEASES/$WANTED")" \
                   || die "Could not ask Anthropic for the $WANTED version (no internet?)" ;;
  *)             version="$WANTED" ;;
esac
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Not a Claude Code version: $version"

installed=""
if [ -x "$CLAUDE_BIN" ]; then
  installed="$("$CLAUDE_BIN" --version 2>/dev/null | awk '{print $1}')" || installed=""
fi

if [ "$installed" = "$version" ]; then
  echo "  ✓ Claude Code $version is already installed"
else
  manifest="$(curl -fsSL -m 60 "$RELEASES/$version/manifest.json")" \
    || die "Anthropic has no Claude Code $version"
  expected_sum="$(printf '%s' "$manifest" | py -c '
import json, sys
print(json.load(sys.stdin)["platforms"][sys.argv[1]]["checksum"])' "$platform")" \
    || die "Anthropic publishes no Claude Code $version for $platform"

  mkdir -p "$SANDBOX/downloads"
  download="$SANDBOX/downloads/claude-$version"
  echo "  Downloading Claude Code $version (about 300 MB, a minute or two)..."
  curl -fL --progress-bar -m 1800 "$RELEASES/$version/$platform/claude" -o "$download" \
    || die "Download failed. Check the internet connection and run ./gdm setup again."

  actual_sum="$(py -c '
import hashlib, sys
with open(sys.argv[1], "rb") as f:
    print(hashlib.file_digest(f, "sha256").hexdigest())' "$download")"
  if [ "$actual_sum" != "$expected_sum" ]; then
    rm -f "$download"
    die "The download does not match Anthropic's checksum. Nothing installed; run ./gdm setup again."
  fi
  chmod 755 "$download"
  mv -f "$download" "$CLAUDE_BIN"
  echo "  ✓ Claude Code $("$CLAUDE_BIN" --version | awk '{print $1}') installed in this folder (checksum verified)"
fi

# ─── 2. How Claude Code signs in on this Mac ──────────────────────────────
forced_login="$(py "$KIT/tools/claude_login_policy.py")"
if [ -n "$forced_login" ]; then
  mode="sign-in"; why="policy"          # the Mac's IT policy decides
elif [ -n "$choice" ]; then
  mode="$choice"; why="chosen"          # --claude-login or --slac-key
elif [ -f "$SETTINGS" ] && ! grep -q '"apiKeyHelper"' "$SETTINGS"; then
  mode="sign-in"; why="chosen"          # a sign-in chosen on an earlier run
else
  mode="key"; why="default"
fi

# ─── 3. Settings ──────────────────────────────────────────────────────────
# write_settings key|sign-in: settings.json from the template, for that route
write_settings() {
  mkdir -p "$SANDBOX/claude"
  py - "$KIT/claude-settings.template.json" "$SETTINGS" "$1" <<'PY'
import json, os, sys

template_path, settings_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
with open(template_path) as f:
    template = json.load(f)

# The template's "// ..." entries are comments, not settings
template = {k: v for k, v in template.items() if not k.startswith("//")}
template["env"] = {k: v for k, v in template["env"].items() if not k.startswith("//")}

if mode == "key":
    # Read the key from this kit (./gdm claude sets GDM_SANDBOX)
    template["apiKeyHelper"] = 'cat "$GDM_SANDBOX/config/slac-ai-key"'
else:
    # The Mac's sign-in decides where requests go and which models exist, so drop
    # the key, the SLAC AI gateway address and its model names
    template.pop("apiKeyHelper", None)

# Keep anything saved since (such as a /model choice); the template wins where both set a value
settings = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except ValueError:
        settings = {}
env = {**settings.get("env", {}), **template["env"]}
settings.update(template)
settings["env"] = env
if mode != "key":
    settings.pop("apiKeyHelper", None)
    settings["env"] = {k: v for k, v in env.items() if not k.startswith("ANTHROPIC_")}

with open(settings_path, "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PY
  chmod 600 "$SETTINGS"
}

print_done() {
  echo
  echo "Setup is done. From now on, every time:"
  echo "  1. Turn on the SLAC VPN."
  echo "  2. In Terminal, in this folder, type:  ./gdm claude"
  echo "  3. Ask Claude: \"Where do I start?\""
}

ask_test_question() {   # one short question to Claude, through the kit's own launcher
  "$KIT/gdm" claude -p 'Reply with exactly: PONG' --model haiku 2>&1 < /dev/null || true
}

test_failed() {   # $1 = what Claude Code printed
  echo "  ✗ Claude did not answer. Claude Code is installed; the message below says why:" >&2
  printf '%s\n' "$1" | sed 's/^/      /' >&2
  echo "    Fix that, then run ./gdm setup again." >&2
  echo "    If the message is unclear, send this whole window to the person who gave you this folder." >&2
  exit 1
}

signed_in() {   # is this folder's Claude Code signed in to an account?
  "$KIT/gdm" claude auth status --json < /dev/null 2>/dev/null | grep -q '"loggedIn": *true'
}

finish_with_sign_in() {   # no key: Claude Code signs in with an account
  echo "── Sign-in"
  if [ "$why" = "policy" ]; then
    echo "  This Mac's IT settings require Claude Code to sign in through your"
    echo "  organization, so no key is needed. The first time you start Claude, it"
    echo "  asks you to sign in: follow the steps it shows, with your SLAC or Stanford"
    echo "  account. (If it doesn't ask, type /login.)"
    print_done
    exit 0
  fi

  if signed_in; then
    echo "  ✓ this folder's Claude Code is already signed in"
  else
    echo "  Sign in with a Claude account: your own (Pro, Max) or your organization's"
    echo "  (Claude for Education, Team, Enterprise). Both use the same sign-in page;"
    echo "  for an organization account, sign in with your work email."
    printf '  Press Return to open the sign-in page in your browser, or type s to skip: '
    IFS= read -r answer || answer="s"
    if [ "$answer" = "s" ] || [ "$answer" = "S" ]; then
      echo "  Skipped. Claude asks you to sign in the first time it starts (or type /login)."
      echo "  To use a SLAC AI key instead:  ./gdm setup --slac-key"
      print_done
      exit 0
    fi
    if ! "$KIT/gdm" claude auth login; then
      echo "  ✗ The sign-in did not finish. Type ./gdm setup to try again, or start" >&2
      echo "    Claude with ./gdm claude and type /login." >&2
      exit 1
    fi
  fi
  echo "  (The sign-in is kept in the macOS Keychain under a name of its own for this"
  echo "  folder, and ./gdm clean removes it. For a SLAC AI key instead: ./gdm setup --slac-key)"

  echo "── Test: one short question to Claude"
  reply="$(ask_test_question)"
  if printf '%s' "$reply" | grep -q PONG; then
    echo "  ✓ Claude answered"
    print_done
    exit 0
  fi
  test_failed "$reply"
}

echo "── Settings"
write_settings "$mode"
echo "  ✓ Claude Code settings written (from claude-settings.template.json)"

# ─── 4a. Sign-in instead of a key (IT policy, or chosen) ──────────────────
if [ "$mode" = "sign-in" ]; then
  if [ "$why" = "policy" ]; then
    echo "  (this Mac's Claude Code policy: forceLoginMethod \"$forced_login\")"
    [ "$choice" = "key" ] && echo "  (--slac-key is not possible here: the policy requires a sign-in)"
  fi
  finish_with_sign_in
fi

# ─── 4b. The SLAC AI key ──────────────────────────────────────────────────
echo "── SLAC AI key"

# Key on stdin. 0 = the gateway accepts it, 1 = it rejects it, 2 = gateway not reachable.
# The key goes to curl on stdin, never on a command line.
check_key() {
  local code
  code="$(sed -n '1s/^/x-api-key: /p' \
          | curl -q -s -o /dev/null -m 20 -w '%{http_code}' -H @- "$GDM_GATEWAY/v1/models")" \
    || code=000
  case "$code" in
    2??)     return 0 ;;
    401|403) return 1 ;;
    *)       return 2 ;;
  esac
}

save_key() {
  mkdir -p "$SANDBOX/config"; chmod 700 "$SANDBOX/config"
  (umask 077; printf '%s\n' "$1" > "$KEY_FILE")
}

if [ -s "$KEY_FILE" ]; then
  prompt="  Paste a new SLAC AI key, or press Return to keep the current one: "
else
  echo "  Paste the SLAC AI key you were given, then press Return. Nothing appears on"
  echo "  the screen while you paste: that is normal."
  echo "  No SLAC key? Just press Return to sign in with a Claude account instead."
  prompt="  Key (or just Return): "
fi

key_ready=0
no_key=0
for attempt in 1 2 3; do
  printf '%s' "$prompt"
  IFS= read -rs key || key=""
  echo
  # Drop the paste markers some terminals add, and any spaces or line breaks
  key="${key//$'\e[200~'/}"
  key="${key//$'\e[201~'/}"
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
  if [ -z "$key" ]; then
    if [ -s "$KEY_FILE" ]; then
      echo "  ✓ kept the key already in this folder"
      key_ready=1
    else
      no_key=1
    fi
    break
  fi
  status=0
  printf '%s\n' "$key" | check_key || status=$?
  case "$status" in
    0) save_key "$key"
       echo "  ✓ SLAC accepted the key; saved in this folder"
       key_ready=1; break ;;
    1) echo "  SLAC did not accept this key (a typo, or it was revoked). Try again." >&2 ;;
    2) save_key "$key"
       echo "  Could not reach SLAC to check the key, so it is saved unchecked." >&2
       echo "  (Is the SLAC VPN on? The test below will tell.)" >&2
       key_ready=1; break ;;
  esac
done
unset key
if [ "$no_key" = 1 ]; then
  # No key: sign in with a Claude account instead
  write_settings sign-in
  echo "  ✓ no key: Claude Code settings changed to sign in with an account instead"
  why="chosen"
  finish_with_sign_in
fi
[ "$key_ready" = 1 ] || die "No key saved. Run ./gdm setup again with the key at hand."

# ─── 5. Test ──────────────────────────────────────────────────────────────
echo "── Test: one short question to Claude"
reply="$(ask_test_question)"
if printf '%s' "$reply" | grep -q PONG; then
  echo "  ✓ Claude answered"
  print_done
elif printf '%s' "$reply" | grep -q -i -e 'administrator policy' -e 'managed settings require'; then
  # An IT policy we did not find in the usual places refuses the key: use the sign-in
  echo "  Claude Code says this Mac's IT policy requires a sign-in instead of a key."
  write_settings sign-in
  echo "  ✓ Claude Code settings changed to use that sign-in"
  why="policy"
  finish_with_sign_in
else
  test_failed "$reply"
fi
