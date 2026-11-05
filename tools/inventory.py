#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Step 1 of the plan: list everything in a Drive folder and who owns it. Read-only.

    ./gdm inventory "https://drive.google.com/drive/folders/<FOLDER_ID>"

Every item gets one of these labels:
    yours        you own it                 -> you can move it yourself, links keep working
    same-org     owned by a Stanford account -> the owner, or a UIT admin, must act
                                               (if the owner has left: UIT must act soon)
    outside-org  owned by a non-Stanford account (gmail, another lab)
                                            -> can't be moved into a Stanford shared drive;
                                               only a copy is possible (its links break)
    no-owner     no visible owner           -> ask UIT

Output folder (results/inventory-<time>/):
    inventory.csv        one row per item: label, path, type, owner, ID, link
    folder-sharing.csv   who each folder is shared with; people who only reach files
                         through folder sharing lose access after the move
    summary.json         counts per label and per owner (attach to the UIT request)
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_api import FOLDER_MIME, DriveClient, id_from_link  # noqa: E402

ITEM_FIELDS = "id,name,mimeType,webViewLink,modifiedTime,owners(emailAddress),driveId"


def label_for(item: dict, my_email: str, org_domain: str) -> str:
    owners = [o.get("emailAddress", "").lower() for o in item.get("owners", [])]
    if not owners:
        return "no-owner"
    if my_email in owners:
        return "yours"
    if any(o.endswith("@" + org_domain) for o in owners):
        return "same-org"
    return "outside-org"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", help="folder link or ID ('my-drive' for your whole My Drive)")
    p.add_argument("--profile", default="readonly", help="login profile (default: readonly)")
    p.add_argument("--org-domain", default="stanford.edu")
    p.add_argument("--out", default=None, help="output folder (default: results/inventory-<time>)")
    p.add_argument("--no-folder-sharing", action="store_true",
                   help="skip the per-folder sharing list (saves one call per folder)")
    args = p.parse_args()

    client = DriveClient(args.profile)
    me = client.about()["user"]["emailAddress"].lower()
    root_ref = "root" if args.folder == "my-drive" else id_from_link(args.folder)
    root = client.get_file(root_ref, "id,name")
    print(f"Reading '{root['name']}' as {me} (read-only)...", file=sys.stderr)

    # Walk the folder tree, one folder at a time
    rows, folders = [], []
    queue = [(root["id"], root["name"])]
    while queue:
        folder_id, folder_path = queue.pop(0)
        for item in client.list_children(folder_id, ITEM_FIELDS):
            path = f"{folder_path}/{item['name']}"
            rows.append({
                "label": label_for(item, me, args.org_domain),
                "path": path,
                "type": item["mimeType"].split(".")[-1].split("/")[-1],
                "owner": ", ".join(o.get("emailAddress", "?") for o in item.get("owners", [])),
                "id": item["id"],
                "link": item.get("webViewLink", ""),
                "modified": item.get("modifiedTime", ""),
            })
            if item["mimeType"] == FOLDER_MIME:
                queue.append((item["id"], path))
                folders.append((path, item["id"]))
        print(f"  {len(rows)} items so far", file=sys.stderr, flush=True)

    # Folder sharing (the root folder too): needed to restore access after the move
    sharing = []
    if not args.no_folder_sharing:
        for path, folder_id in [(root["name"], root["id"])] + folders:
            for perm in client.list_permissions(folder_id):
                sharing.append({"folder": path, "folder_id": folder_id, "role": perm.get("role"),
                                "type": perm.get("type"),
                                "who": perm.get("emailAddress") or perm.get("domain") or ""})

    out_dir = args.out or os.path.join("results", f"inventory-{datetime.now():%Y%m%d-%H%M}")
    os.makedirs(out_dir, exist_ok=True)
    rows.sort(key=lambda r: (r["label"] != "yours", r["label"], r["path"]))
    with open(os.path.join(out_dir, "inventory.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "path", "type", "owner", "id", "link",
                                               "modified"])
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(out_dir, "folder-sharing.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["folder", "folder_id", "role", "type", "who"])
        writer.writeheader()
        writer.writerows(sharing)

    owners_not_you = collections.Counter(r["owner"] for r in rows if r["label"] != "yours")
    summary = {
        "folder": root["name"], "folder_id": root["id"], "read_as": me,
        "items": len(rows), "folders": len(folders),
        "by_label": dict(collections.Counter(r["label"] for r in rows)),
        "items_not_owned_by_you_per_owner": dict(owners_not_you.most_common()),
        "people_and_groups_with_folder_access": sorted({s["who"] for s in sharing if s["who"]}),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"\nSaved to {out_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
