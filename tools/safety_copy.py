#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Step 3 of the plan: safety copies of files that are at risk of being deleted.

    ./gdm safety-copy results/inventory-<time>/inventory.csv "<destination folder link>" \\
        --owners departed1@stanford.edu,departed2@stanford.edu [--outside-org]

Without --yes it only PRINTS what it would copy. Add --yes to make the copies.

The copies are made inside Google (nothing is downloaded). The originals are not
changed in any way, so every existing link keeps working exactly as before.
A copy has a NEW ID: it protects the content, it does not keep links. Folders
and shortcuts are skipped; copies are named "<name> (safety copy)".

Writes safety-copies.csv next to the inventory: original ID/link -> copy ID/link.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_api import DriveClient, DriveError, id_from_link  # noqa: E402

SKIP_TYPES = {"folder", "shortcut"}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inventory_csv")
    p.add_argument("destination", help="link or ID of the folder that receives the copies")
    p.add_argument("--owners", default="", help="comma-separated owner emails to copy")
    p.add_argument("--outside-org", action="store_true",
                   help="also copy every file owned by a non-Stanford account")
    p.add_argument("--yes", action="store_true", help="really make the copies")
    p.add_argument("--profile", default="writer")
    args = p.parse_args()

    owners = {o.strip().lower() for o in args.owners.split(",") if o.strip()}
    if not owners and not args.outside_org:
        sys.exit("Say which files to copy: --owners a@stanford.edu,b@stanford.edu and/or "
                 "--outside-org")
    with open(args.inventory_csv) as f:
        rows = list(csv.DictReader(f))
    chosen = [r for r in rows if r["type"] not in SKIP_TYPES and (
        r["owner"].lower() in owners or (args.outside_org and r["label"] == "outside-org"))]

    print(f"{len(chosen)} file(s) selected for a safety copy:")
    for r in chosen:
        print(f"  [{r['owner']}] {r['path']}")
    if not args.yes:
        print("\nNothing was copied (preview only). Add --yes to make these copies.")
        return

    client = DriveClient(args.profile)
    dest_id = id_from_link(args.destination)
    out_path = os.path.join(os.path.dirname(args.inventory_csv), "safety-copies.csv")
    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["time", "result", "path", "owner", "original_id",
                                               "original_link", "copy_id", "copy_link"])
        if new_file:
            writer.writeheader()
        for r in chosen:
            name = r["path"].rsplit("/", 1)[-1] + " (safety copy)"
            record = {"time": datetime.now().isoformat(timespec="seconds"), "path": r["path"],
                      "owner": r["owner"], "original_id": r["id"], "original_link": r["link"]}
            try:
                copy = client.copy_file(r["id"], dest_id, name)
                record.update(result="copied", copy_id=copy["id"],
                              copy_link=copy.get("webViewLink", ""))
            except DriveError as e:
                record.update(result=f"FAILED: {e.reason or e.status}", copy_id="", copy_link="")
            writer.writerow(record)
            print(f"  {record['result']:10} {r['path']}")
    print(f"\nRecord saved to {out_path}")


if __name__ == "__main__":
    main()
