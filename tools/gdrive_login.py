#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Log a Google account into a sandbox login profile (used by ./gdm login).

    ./gdm login you@stanford.edu          read-only profile "readonly"
    ./gdm login-writer you@stanford.edu   full-access profile "writer" (safety copies only)

A browser tab opens; pick the account named on the command line and tick the
Google Drive permission box. Any other account is refused and nothing is saved.

Technical notes: the login is stored as an rclone profile in
.sandbox/config/rclone/rclone.conf (mode 600). It listens on a free local port
(rclone's fixed port 53682 is often taken by SSH tunnels). If
.sandbox/config/oauth-client.json exists (a "Desktop app" OAuth client from
Google Cloud Console), it is used; otherwise rclone's shared client is used,
which Google rate-limits heavily and rclone is retiring.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RCLONE_CLIENT_ID = "202264815644.apps.googleusercontent.com"
RCLONE_OBSCURED_SECRET = "eX8GpZTVx3vxMWVkuuBdDWmAUE6rGhTwVrvG9GhllYccSdj2-mvHVg"
ALLOWED_SCOPES = {"drive", "drive.readonly"}
CLIENT_FILE = os.path.join(os.environ.get("GDM_SANDBOX", ".sandbox"), "config",
                           "oauth-client.json")


def load_oauth_client() -> tuple[str, str, bool]:
    """Return (client_id, client_secret, is_own_client). Secrets are never printed."""
    if os.path.exists(CLIENT_FILE):
        with open(CLIENT_FILE) as f:
            data = json.load(f)
        installed = data.get("installed") or data.get("web") or {}
        return installed["client_id"], installed["client_secret"], True
    result = subprocess.run(["rclone", "reveal", RCLONE_OBSCURED_SECRET],
                            capture_output=True, text=True, check=True)
    return RCLONE_CLIENT_ID, result.stdout.strip(), False


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_auth_code(port: int, expected_state: str) -> str:
    """Serve exactly one request: Google's redirect carrying ?code=..."""
    received = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            received["code"] = query.get("code", [None])[0]
            received["state"] = query.get("state", [None])[0]
            received["error"] = query.get("error", [None])[0]
            ok = received["code"] and received["state"] == expected_state
            message = ("Login complete. You can close this tab and go back to the terminal."
                       if ok else f"Login failed: {received['error'] or 'bad state'}")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>{message}</h2>".encode())

        def log_message(self, *args):
            pass  # keep the terminal quiet

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    while "code" not in received:
        server.handle_request()
    server.server_close()

    if received["error"]:
        sys.exit(f"Google returned an error: {received['error']}")
    if received["state"] != expected_state:
        sys.exit("State mismatch - ignoring this login attempt.")
    return received["code"]


def exchange_code_for_token(code, client_id, client_secret, redirect_uri, code_verifier) -> dict:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=body) as resp:
        return json.load(resp)


def who_am_i(access_token: str) -> dict:
    """One read-only call. Retries for ~2 minutes if Google is rate limiting."""
    req = urllib.request.Request(
        "https://www.googleapis.com/drive/v3/about?fields=user",
        headers={"Authorization": f"Bearer {access_token}"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)["user"]
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if "rateLimitExceeded" in body and attempt < 7:
                time.sleep(min(2 ** attempt, 30))
                continue
            sys.exit(f"Drive API refused the new login (HTTP {e.code}):\n{body}")


def write_rclone_remote(name: str, scope: str, token: dict, client_id: str,
                        client_secret: str, own_client: bool) -> None:
    """Append a [name] drive section to the sandbox rclone config."""
    config_path = os.environ.get("RCLONE_CONFIG", "")
    if ".sandbox" not in config_path:
        sys.exit("RCLONE_CONFIG is not the sandbox config. Run `source env.sh` first.")

    existing = ""
    if os.path.exists(config_path):
        with open(config_path) as f:
            existing = f.read()
    if f"[{name}]" in existing:
        sys.exit(f"Remote [{name}] already exists in {config_path}; not overwriting.")

    lines = [f"[{name}]", "type = drive", f"scope = {scope}"]
    if own_client:
        lines += [f"client_id = {client_id}", f"client_secret = {client_secret}"]
    lines.append(f"token = {json.dumps(token, separators=(',', ':'))}")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "a") as f:
        f.write("\n" + "\n".join(lines) + "\n")
    os.chmod(config_path, 0o600)


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[2] not in ALLOWED_SCOPES:
        sys.exit(__doc__)
    remote_name, scope = sys.argv[1], sys.argv[2]
    expected_email = sys.argv[3].lower() if len(sys.argv) == 4 else None

    client_id, client_secret, own_client = load_oauth_client()
    port = find_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/"
    state = secrets.token_urlsafe(16)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()

    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"https://www.googleapis.com/auth/{scope}",
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        **({"login_hint": expected_email} if expected_email else {}),
    })

    print(f"Logging in remote '{remote_name}' with scope '{scope}' "
          f"({'your own OAuth client' if own_client else 'rclone shared client'}).", flush=True)
    print(f"If no browser tab opens, open this link:\n{auth_url}\n", flush=True)
    subprocess.run(["open", auth_url], check=False)

    code = wait_for_auth_code(port, state)
    token_response = exchange_code_for_token(code, client_id, client_secret, redirect_uri,
                                             code_verifier)
    granted = token_response.get("scope", "")
    print(f"Permissions granted: {granted}", flush=True)
    if f"https://www.googleapis.com/auth/{scope}" not in granted.split():
        sys.exit("The Drive permission was not granted (the checkbox on Google's consent "
                 "screen must be ticked). Please run this again.")
    if "refresh_token" not in token_response:
        sys.exit("Google did not return a refresh token; please retry.")

    expiry = datetime.now(timezone.utc) + timedelta(seconds=token_response["expires_in"])
    rclone_token = {
        "access_token": token_response["access_token"],
        "token_type": "Bearer",
        "refresh_token": token_response["refresh_token"],
        "expiry": expiry.isoformat(timespec="seconds"),
    }
    user = who_am_i(token_response["access_token"])   # retries through rate limits
    email = user.get("emailAddress", "").lower()
    if expected_email and email != expected_email:
        sys.exit(f"WRONG ACCOUNT: you logged in as {email}, expected {expected_email}. "
                 f"Nothing was saved; please run this again.")
    write_rclone_remote(remote_name, scope, rclone_token, client_id, client_secret, own_client)
    print(f"OK: remote '{remote_name}' is logged in as "
          f"{user.get('displayName')} <{user.get('emailAddress')}> (scope: {scope})", flush=True)


if __name__ == "__main__":
    main()
