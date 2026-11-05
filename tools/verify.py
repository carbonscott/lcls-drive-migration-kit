#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Steps 5 and 8 of the plan: check every item from an earlier inventory, by its ID.

    ./gdm verify results/inventory-<time>/inventory.csv "<shared drive link>"

Looking an item up by its original ID is exactly what an old link does, so this
answers "does every old link still work, and where does it lead now?". Read-only.

Status per item:
    in shared drive      the old link works and leads into the shared drive
    still in My Drive    not moved yet (or could not be moved)
    other shared drive   the old link works, but leads into a different shared drive
    trashed              someone put it in the trash
    NOT FOUND            the old link is dead for you (deleted, or you lost access)

Also reports items whose owner changed (for example after a UIT ownership transfer).
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_api import RATE_LIMIT_REASONS, DriveClient, DriveError, id_from_link  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inventory_csv")
    p.add_argument("shared_drive", nargs="?", default="",
                   help="shared drive link or ID (optional)")
    p.add_argument("--profile", default="readonly")
    args = p.parse_args()

    client = DriveClient(args.profile)
    shared_drive_id = id_from_link(args.shared_drive) if args.shared_drive else None
    with open(args.inventory_csv) as f:
        before = list(csv.DictReader(f))

    results = []
    for n, row in enumerate(before, 1):
        try:
            now = client.get_file(row["id"], "id,name,driveId,trashed,owners(emailAddress)")
            # Items in a shared drive belong to the organization, not to a person
            owner_now = ("(shared drive)" if now.get("driveId") else
                         ", ".join(o["emailAddress"] for o in now.get("owners", [])))
            if now.get("trashed"):
                status = "trashed"
            elif not now.get("driveId"):
                status = "still in My Drive"
            elif now["driveId"] == shared_drive_id:
                status = "in shared drive"
            else:
                status = "other shared drive"
        except DriveError as e:
            if e.reason in RATE_LIMIT_REASONS:
                raise
            status, owner_now = "NOT FOUND", ""
        results.append({"status": status, "path": row["path"], "type": row["type"],
                        "owner_before": row["owner"], "owner_now": owner_now,
                        "owner_changed": ("yes" if owner_now not in ("", "(shared drive)", row["owner"])
                                          else ""),
                        "id": row["id"], "link": row["link"]})
        if n % 50 == 0:
            print(f"  checked {n}/{len(before)}", file=sys.stderr, flush=True)

    out_path = os.path.join(os.path.dirname(args.inventory_csv), "verify.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(sorted(results, key=lambda r: (r["status"], r["path"])))

    summary = {"checked": len(results),
               "by_status": dict(collections.Counter(r["status"] for r in results)),
               "owner_changed": sum(1 for r in results if r["owner_changed"])}
    print(json.dumps(summary, indent=2))
    print(f"\nDetails saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
