#!/bin/bash
# PRACTICE walkthrough: prints pretend commands and made-up output from the files in
# this folder. It never runs ./gdm and never contacts Google Drive.
cd "$(dirname "$0")"
B=$'\e[1m'; D=$'\e[2m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'
P=${PAUSE:-1.2}

type_cmd() {  # show a command being typed
  printf "${G}\$ ${N}"
  s="$1"; i=0
  while [ $i -lt ${#s} ]; do printf "%s" "${s:$i:1}"; sleep 0.02; i=$((i+1)); done
  echo; sleep 0.5
}
step() { sleep $P; clear; echo "${D}PRACTICE ONLY - made-up data, no Google Drive access${N}"; echo
         echo "${B}${C}=== $1 ===${N}"; echo; sleep 0.6; }
say()  { echo "${Y}Claude:${N} $1"; sleep 0.8; }
you()  { echo "${B}You:${N} $1"; sleep 0.8; }
pause(){ sleep $P; }

step "Step 0: Create the shared drive"
say "In the Drive web page: Shared drives > New > name it 'LCLS Operations'."
say "Nothing to run here. Copy the new shared drive's link for steps 5 and 8."
pause

step "Step 1: Take the inventory (read-only)"
type_cmd './gdm login pat@stanford.edu'
echo "A browser tab opened. Choose pat@stanford.edu, tick Google Drive, click Continue."
echo "${G}Logged in READ-ONLY as pat@stanford.edu${N}"; pause
type_cmd './gdm inventory "https://drive.google.com/drive/folders/1AaRoot"'
echo "Reading 'LCLS Operations' as pat@stanford.edu (read-only)..."
echo "  4 items so far"; sleep 0.3; echo "  9 items so far"; sleep 0.3; echo "  11 items so far"
cat summary.json; echo; echo "Saved to results/inventory-20261105-1430/"; pause
say "11 items: 4 are yours, 5 belong to colleagues, 2 belong to people outside Stanford."
say "Which of jlee, mchen and rgarcia have left SLAC?"
you "mchen left last year."
type_cmd 'cat results/departed-owners.txt'
cat departed-owners.txt
pause

step "Step 2: Where are these files linked from?"
type_cmd 'confluence-search whoami'
echo "Logged in to Confluence as pat"
type_cmd "confluence-search 'text ~ \"docs.google.com\" OR text ~ \"drive.google.com\"'"
cat <<T
  PCDS / Beamline startup        -> 1BbStartup     (Beamline startup checklist)  same-org
  PCDS / Shift handover          -> 1AaRun24Sched  (Run 24 schedule)             yours
  PCDS / Detector notes          -> 1BbCooldown    (Detector cooldown)           same-org
T
type_cmd "jira-search 'text ~ \"drive.google.com\"'"
cat <<T
  LCLSECSD-1234  Vacuum pump service  -> 1CcPumpManual (Vendor pump manual)  ${R}outside-org${N}
T
say "3 links will keep working after the move."
say "${R}1 will break${N}: the pump manual in LCLSECSD-1234. Someone should update that ticket later."
pause

step "Step 3: Safety copies (preview first)"
type_cmd './gdm login-writer pat@stanford.edu'
echo "${G}Logged in (can create copies) as pat@stanford.edu${N}"
type_cmd './gdm safety-copy inventory.csv "https://drive.google.com/drive/folders/1BackupFolder" --owners mchen@stanford.edu --outside-org'
echo "PREVIEW - nothing copied yet. 4 files would be copied:"
awk -F, 'NR>1 && ($4=="mchen@stanford.edu" || $1=="outside-org") {printf "  %-55s %s\n",$2,$4}' inventory.csv
echo "Run again with --yes to copy."
say "Shall I make these 4 copies?"
you "Yes."
type_cmd './gdm safety-copy inventory.csv "https://drive.google.com/drive/folders/1BackupFolder" --owners mchen@stanford.edu --outside-org --yes'
awk -F, 'NR>1 && ($4=="mchen@stanford.edu" || $1=="outside-org") {printf "  '"$G"'copied'"$N"'  %s\n",$2}' inventory.csv
echo "Log saved to results/inventory-20261105-1430/safety-copies.csv"
pause

step "Step 4: Request to UIT"
say "I filled in the template from Appendix D:"
cat <<T
  Folder:        LCLS Operations (11 items, 2 folders)
  Destination:   shared drive 'LCLS Operations'
  Owned by others: jlee (2), mchen (2), rgarcia (1)
  Departed owner:  mchen@stanford.edu - please transfer ownership of 2 items
  Outside owners:  2 items (safety copies already made)
  Attached:      summary.json, inventory.csv
T
pause

step "Step 5: Check UIT's work"
type_cmd './gdm verify results/inventory-20261105-1430/inventory.csv "https://drive.google.com/drive/folders/0ASharedDrive"'
cat <<T
{ "checked": 11, "by_status": { "still in My Drive": 11 }, "owner_changed": 2 }
T
say "Ownership of mchen's items has moved, as UIT promised. Nothing is in the shared drive yet, which is expected before step 6."
pause

step "Step 6: Move the folder (you click, Appendix E)"
say "1. In My Drive, right-click 'LCLS Operations' > Organize > Move."
say "2. Choose Shared drives > LCLS Operations > Move > Move (confirm)."
say "3. Wait until Drive says the move is complete."
you "Done."
pause

step "Step 7: Give people access again"
say "From folder-sharing.csv, add these as shared drive members:"
awk -F, 'NR>1 && $5!="pat@stanford.edu" {printf "  %-35s %-8s (was %s on %s)\n",$5,$4,$3,$1}' folder-sharing.csv
pause

step "Step 8: Final check"
type_cmd './gdm verify results/inventory-20261105-1430/inventory.csv "https://drive.google.com/drive/folders/0ASharedDrive"'
cat <<T
{ "checked": 11, "by_status": { "in shared drive": 8, "still in My Drive": 3 }, "owner_changed": 0 }
T
echo
awk -F, 'NR>1 {c=($1=="in shared drive")?"'"$G"'":"'"$R"'"; printf "  %s%-18s'"$N"' %s\n",c,$1,$2}' verify.csv
echo
say "The 2 outside-Stanford files are expected to stay behind."
say "${R}'Run 23 schedule (archive)' did not move${N}: follow up with UIT. The safety copy from step 3 protects it."
say "Everything else is in the shared drive. Keep results/ as the record."
sleep 3
echo; echo "${B}End of practice walkthrough.${N}"
