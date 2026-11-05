"""Minimal Google Drive client for the migration kit: READ and COPY only.

What this file can do to Google Drive, and nothing else:
    - read file/folder details, folder contents and sharing  (HTTP GET)
    - make a copy of a file into a folder you choose          (POST .../files/<id>/copy)

It has no code to delete, trash, move, rename, edit or re-share anything:
the request function refuses every HTTP method except GET, and refuses any
POST that is not a copy. That is small enough to check by reading this file.

The Google login comes from a sandbox rclone profile (see gdrive_login.py).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/drive/v3"
RCLONE_CLIENT_ID = "202264815644.apps.googleusercontent.com"
RCLONE_OBSCURED_SECRET = "eX8GpZTVx3vxMWVkuuBdDWmAUE6rGhTwVrvG9GhllYccSdj2-mvHVg"
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}


def id_from_link(link_or_id: str) -> str:
    """Accept a Drive link (folder, file, doc) or a bare ID and return the ID."""
    match = re.search(r"(?:/folders/|/d/|[?&]id=)([A-Za-z0-9_-]{10,})", link_or_id)
    return match.group(1) if match else link_or_id.strip()


class DriveError(Exception):
    def __init__(self, status: int, body: str, what: str):
        self.status = status
        try:
            err = json.loads(body)["error"]
            self.reason = (err.get("errors") or [{}])[0].get("reason", "")
            self.message = err.get("message", body)
        except (ValueError, KeyError, TypeError):
            self.reason, self.message = "", body
        super().__init__(f"{what}: HTTP {status} {self.reason}: {self.message}")


def _rclone_profile(name: str) -> dict:
    out = subprocess.run(["rclone", "config", "dump"], capture_output=True, text=True, check=True)
    profiles = json.loads(out.stdout)
    if name not in profiles:
        sys.exit(f"Not logged in yet (no profile '{name}'). Run:  ./gdm login YOUR_EMAIL")
    section = profiles[name]
    section["token"] = json.loads(section["token"])
    return section


class DriveClient:
    def __init__(self, profile: str):
        section = _rclone_profile(profile)
        self.profile = profile
        self._refresh_token = section["token"]["refresh_token"]
        self._client_id = section.get("client_id") or RCLONE_CLIENT_ID
        self._client_secret = section.get("client_secret")
        self._access_token = None
        self._expires_at = 0.0

    def _token(self) -> str:
        if self._access_token is None or time.time() > self._expires_at - 120:
            secret = self._client_secret or subprocess.run(
                ["rclone", "reveal", RCLONE_OBSCURED_SECRET],
                capture_output=True, text=True, check=True).stdout.strip()
            body = urllib.parse.urlencode({
                "client_id": self._client_id, "client_secret": secret,
                "refresh_token": self._refresh_token, "grant_type": "refresh_token",
            }).encode()
            with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=body) as r:
                data = json.load(r)
            self._access_token = data["access_token"]
            self._expires_at = time.time() + data["expires_in"]
        return self._access_token

    def _request(self, method: str, path: str, params: dict, body: dict | None = None):
        # The only two kinds of request this kit ever makes:
        is_read = method == "GET"
        is_copy = method == "POST" and re.fullmatch(r"/files/[^/]+/copy", path)
        if not (is_read or is_copy):
            raise PermissionError(f"Refused: this kit only reads and copies ({method} {path}).")

        url = f"{API}{path}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else None
        attempts = 8   # Google rate limits: wait 1, 2, 4, 8, 16, 30, 30 s
        for attempt in range(attempts):
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {self._token()}")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req) as resp:
                    payload = resp.read()
                return json.loads(payload) if payload else {}
            except urllib.error.HTTPError as e:
                err_body = e.read().decode(errors="replace")
                retryable = e.code in (429, 500, 502, 503) or (
                    e.code == 403 and any(r in err_body for r in RATE_LIMIT_REASONS))
                if retryable and attempt < attempts - 1:
                    wait = min(2 ** attempt, 30)
                    print(f"  (Google is busy, retrying in {wait}s)", file=sys.stderr, flush=True)
                    time.sleep(wait)
                    continue
                raise DriveError(e.code, err_body, f"{method} {path}") from None

    # ------------------------------------------------------------ reading
    def about(self) -> dict:
        return self._request("GET", "/about", {"fields": "user"})

    def get_file(self, file_id: str, fields: str) -> dict:
        return self._request("GET", f"/files/{file_id}",
                             {"fields": fields, "supportsAllDrives": "true"})

    def list_children(self, folder_id: str, fields: str) -> list:
        params = {"q": f"'{folder_id}' in parents and trashed = false",
                  "fields": f"nextPageToken,files({fields})", "pageSize": "1000",
                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                  "corpora": "allDrives"}
        items, page_token = [], None
        while True:
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", "/files", params)
            items += data.get("files", [])
            page_token = data.get("nextPageToken")
            if not page_token:
                return items

    def list_permissions(self, file_id: str) -> list:
        data = self._request("GET", f"/files/{file_id}/permissions",
                             {"supportsAllDrives": "true",
                              "fields": "permissions(role,type,emailAddress,domain)"})
        return data.get("permissions", [])

    # ------------------------------------------------------------ copying
    def copy_file(self, file_id: str, dest_folder_id: str, new_name: str) -> dict:
        """Server-side copy (nothing is downloaded). The original is not touched."""
        return self._request("POST", f"/files/{file_id}/copy",
                             {"supportsAllDrives": "true", "fields": "id,name,webViewLink"},
                             {"parents": [dest_folder_id], "name": new_name})
