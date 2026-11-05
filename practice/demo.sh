#!/bin/bash
# PRACTICE walkthrough, as it looks in a Claude session started with ./gdm claude:
# you ask in plain words, Claude runs the toolkit's commands (the ▸ lines) and
# explains the results. It only prints made-up output from the files in this
# folder: it never runs ./gdm and never contacts Google Drive, Confluence or Jira.
#
# Recorded for START-HERE.html ("See it in action") with:
#   script -q -r recording bash ./demo.sh       (inside a 110x36 terminal)
cd "$(dirname "$0")"
B=$'\e[1m'; D=$'\e[2m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'
P=${PAUSE:-1.2}
INV="results/inventory-20261105-1430"

step() {   # a new screen for each step of the checklist
  sleep "$P"; clear
  echo "${D}PRACTICE ONLY - made-up data, no Google Drive access.${N}"
  echo "${D}You type only plain words; the ▸ lines are commands Claude runs for you.${N}"
  echo
  echo "${B}${C}=== $1 ===${N}"; echo; sleep 0.6
}
you() {    # the person types a request
  printf '%s' "${B}${C}You:${N} "
  local s="$1" i=0
  while [ $i -lt ${#s} ]; do printf '%s' "${s:$i:1}"; sleep 0.025; i=$((i + 1)); done
  echo; sleep 0.7
}
say() { echo "${Y}Claude:${N} $1"; sleep 0.9; }
runs() {   # $1 = command, $2 = "ask" (Claude asks first) or "auto" (runs on its own)
  if [ "$2" = "ask" ]; then
    echo "  ▸ Claude runs ${G}$1${N}  ${Y}[asks you first: you press Return]${N}"
  else
    echo "  ▸ Claude runs ${G}$1${N}  ${D}[runs on its own]${N}"
  fi
  sleep 1
}
out() { echo "      $1"; sleep 0.25; }

step "Step 0: Create the shared drive"
you "Where do I start?"
say "With an empty shared drive. In Google Drive: Shared drives > New > 'LCLS Operations'."
say "Add a second Manager, so the drive never depends on one person. No command here."
you "Done."
sleep "$P"

step "Step 1: Take the inventory (read-only)"
you "Take the inventory of https://drive.google.com/drive/folders/1AaRoot"
say "First a read-only Google login. A browser tab opens: choose your Stanford account,"
say "tick Google Drive, click Continue."
runs './gdm login pat@stanford.edu' ask
out "${G}Logged in READ-ONLY as pat@stanford.edu${N}"
runs './gdm inventory "https://drive.google.com/drive/folders/1AaRoot"' auto
out "Reading 'LCLS Operations' as pat@stanford.edu (read-only)..."
out "4 items so far"; out "9 items so far"; out "11 items so far"
out "Saved to $INV/"
say "11 items: 4 are yours, 5 belong to colleagues, 2 to people outside Stanford."
say "The colleagues are jlee (2), mchen (2) and rgarcia (1). Which of them have left SLAC?"
you "mchen left last year."
echo "  ▸ Claude writes ${G}results/departed-owners.txt${N}  ${D}(mchen@stanford.edu)${N}"; sleep 1
sleep "$P"

step "Step 2: Where are these files linked from?"
you "Which Confluence pages and Jira issues link to these files?"
runs 'uv run --script .claude/skills/confluence-search/scripts/cqlsearch.py whoami' auto
out "pat (SLAC Confluence)"
runs "uv run --script .claude/skills/confluence-search/scripts/cqlsearch.py search 'text ~ \"drive.google.com\" OR text ~ \"docs.google.com\"'" auto
out "PCDS / Beamline startup   -> Beamline startup checklist   (same-org)"
out "PCDS / Shift handover     -> Run 24 schedule              (yours)"
out "PCDS / Detector notes     -> Detector cooldown            (same-org)"
runs "uv run --script .claude/skills/jira-search/scripts/jqlsearch.py search 'text ~ \"drive.google.com\"'" auto
out "LCLSECSD-1234  Vacuum pump service  -> Vendor pump manual  ${R}(outside-org)${N}"
say "3 links point at files that will move, so they keep working."
say "${R}1 will break${N}: LCLSECSD-1234 links the vendor pump manual, which can only be copied."
say "Someone should update that ticket after the move."
sleep "$P"

step "Step 3: Safety copies (preview first)"
you "Make safety copies in https://drive.google.com/drive/folders/1BackupFolder"
say "That needs a second Google login that can create copies (the same clicks)."
runs './gdm login-writer pat@stanford.edu' ask
out "${G}Logged in (can create copies) as pat@stanford.edu${N}"
runs "./gdm safety-copy $INV/inventory.csv \"https://drive.google.com/drive/folders/1BackupFolder\" --owners mchen@stanford.edu --outside-org" ask
out "PREVIEW - nothing copied yet. 4 files would be copied:"
awk -F, 'NR>1 && ($4=="mchen@stanford.edu" || $1=="outside-org") {printf "        %-55s %s\n",$2,$4}' inventory.csv; sleep 0.5
say "That's the preview. Shall I make these 4 copies?"
you "Yes."
runs "./gdm safety-copy $INV/inventory.csv \"https://drive.google.com/drive/folders/1BackupFolder\" --owners mchen@stanford.edu --outside-org --yes" ask
awk -F, 'NR>1 && ($4=="mchen@stanford.edu" || $1=="outside-org") {printf "        '"$G"'copied'"$N"'  %s\n",$2}' inventory.csv; sleep 0.5
out "Log saved to $INV/safety-copies.csv"
say "Done. The originals are untouched; the copies are insurance while UIT works."
sleep "$P"

step "Step 4: Request to UIT"
you "Draft the UIT request."
say "Here it is, filled in from the inventory (the template is in Appendix D):"
out "Folder:           LCLS Operations (11 items, 2 folders)"
out "Destination:      shared drive 'LCLS Operations'"
out "Owned by others:  jlee (2), mchen (2), rgarcia (1)"
out "Departed owner:   mchen@stanford.edu - please transfer ownership of 2 items"
out "Outside owners:   2 items (safety copies already made)"
say "Attach summary.json and inventory.csv from $INV/ and send it to UIT."
sleep "$P"

step "Step 5: Check UIT's work"
you "UIT says they're done. Check their work."
runs "./gdm verify $INV/inventory.csv" auto
out '{ "checked": 11, "by_status": { "still in My Drive": 11 }, "owner_changed": 2 }'
say "Ownership of mchen's 2 items has moved to you, as UIT promised."
say "Nothing is in the shared drive yet, which is expected before step 6."
sleep "$P"

step "Step 6: Move the folder (you click, Appendix E)"
you "How do I move the folder?"
say "1. In My Drive, right-click 'LCLS Operations' > Organize > Move."
say "2. Choose Shared drives > LCLS Operations > Move, then confirm."
say "3. Wait until Drive says the move is complete. (No command: Google only lets a person do this.)"
you "Done."
sleep "$P"

step "Step 7: Give people access again"
you "Who needs access to the shared drive?"
echo "  ▸ Claude reads ${G}$INV/folder-sharing.csv${N}"; sleep 1
say "Add these as members of the shared drive:"
awk -F, 'NR>1 && $5!="pat@stanford.edu" {printf "        %-32s %-7s (was %s on %s)\n",$5,$4,$3,$1}' folder-sharing.csv; sleep 0.5
sleep "$P"

step "Step 8: Final check"
you "Check every file against https://drive.google.com/drive/folders/0ASharedDrive"
runs "./gdm verify $INV/inventory.csv \"https://drive.google.com/drive/folders/0ASharedDrive\"" auto
out '{ "checked": 11, "by_status": { "in shared drive": 8, "still in My Drive": 3 }, "owner_changed": 0 }'
awk -F, 'NR>1 {c=($1=="in shared drive")?"'"$G"'":"'"$R"'"; printf "        %s%-18s'"$N"' %s\n",c,$1,$2}' verify.csv; sleep 0.5
say "The 2 outside-Stanford files are expected to stay behind."
say "${R}'Run 23 schedule (archive)' did not move${N}: follow up with UIT. Its safety copy from step 3 protects it."
say "Everything else is in the shared drive. Keep results/ as the record."
sleep 3
echo; echo "${B}End of practice walkthrough.${N}"
