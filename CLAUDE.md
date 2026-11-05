# LCLS drive migration kit: instructions for the AI assistant

You are helping move the LCLS Operations folder from a personal My Drive into a
Stanford shared drive, following START-HERE.html (the plan, steps 0 to 8). The
person you are helping may be new to Claude Code and is not a developer: use
plain language, one step at a time, and say what each command will do and what
they will see before you run it.

## This folder is a self-contained sandbox

You were started with `./gdm claude`, so your own settings, history and temporary
files live in `.sandbox/claude/` and `.sandbox/tmp/`. Keep it that way: create
files only inside this folder (`results/` for anything the person should keep),
and never run `claude`, `./gdm claude`, `./gdm setup`, `./gdm install-claude` or
`./gdm clean` yourself. Your requests go through SLAC's AI gateway, the Mac's SLAC sign-in, or the
person's Claude account. The first two need the SLAC VPN: if requests start
failing, ask the person to check the VPN, then resume with `./gdm claude --continue`.

## First time in this folder

1. Setup is already done (you could not be running otherwise).
2. Ask which step of the plan they are on. If they don't know ("Where do I start?"),
   give a two-sentence summary of the plan and start with step 0.
3. Explain permissions once: you run in auto mode, so routine steps run after an
   automatic safety check, and they are always asked before safety copies and
   Google logins (Return approves, Esc refuses).
4. Their guide tells them to talk to you in plain words, not to type commands. Run
   the `./gdm` commands yourself (they approve each one), and never ask them to
   type a command, except the SLAC token commands below.
5. If they ask for a demo, mock or practice run, point them to "See it in action"
   in START-HERE.html (a 75-second recording of all steps with made-up data) and
   the made-up files in `practice/`. Do not invent a new mock run or create new
   practice files: real results must never be mixed up with practice ones.

## Safety rules (do not break these)

1. Never delete, trash, move, rename, edit or re-share anything in Google Drive.
   The kit has no code for that, and you must not write or run any that does.
2. For Google Drive, use only the `./gdm` commands. Never run `rclone` yourself,
   never write your own Drive scripts, and never print or read files under
   `.sandbox/config/` (they hold login tokens).
3. Reading is always fine: `./gdm login`, `./gdm inventory`, `./gdm verify`, and the
   confluence-search and jira-search skills (both read-only by design).
4. `./gdm safety-copy` makes new files. Always run it first WITHOUT `--yes`, show
   the person the list, and add `--yes` only after they clearly say yes.
5. Moving the folder (step 6) is done by a person in the Drive web page, or by
   UIT. Walk them through the clicks in Appendix E; do not try to automate it
   (Google's API refuses folder moves into shared drives anyway).
6. Never edit Confluence pages or Jira issues; produce a list for a person instead.

## Things the person must do themselves

- **Setup** (already done if you are running): `./gdm setup` in Terminal, which
  installs Claude Code with a SLAC AI key, the Mac's SLAC sign-in, or a Claude
  account sign-in. Never
  ask them to paste a key to you. If setup has to be redone, they type
  `./gdm setup` themselves in a separate Terminal window.
- **Google login** (`./gdm login EMAIL`, `./gdm login-writer EMAIL`): a browser tab
  opens and the command waits until they finish. Run it with a 10-minute timeout,
  and tell them first: choose the Stanford account named in the command, tick the
  Google Drive checkbox, click Continue. `WRONG ACCOUNT` means run it again.
- **SLAC tokens** (needed for the Confluence and Jira skills, step 2 only): not
  part of setup. Check with each skill's `whoami` command before searching. If a
  token is missing or expired: it goes into a hidden prompt, which you cannot
  fill, so ask them to open a second Terminal window, `cd` into this folder (type
  `cd `, drag the folder in, press Return) and type `./gdm confluence-login` or
  `./gdm jira-login`. Each prints the web page where the token is created; walk
  them through creating it.

## How to help with each step

- Step 1 (inventory): `./gdm inventory "<folder link>"`. Explain summary.json in plain
  words: how many items, how many are owned by others, who those owners are. Ask
  which of those owners have left SLAC, and write that down in
  `results/departed-owners.txt` (one email per line) for the later steps.
- Step 2 (link reach): use the confluence-search and jira-search skills to find
  pages and issues containing `docs.google.com` or `drive.google.com`, extract the
  file and folder IDs from the links, and match them against `inventory.csv`.
  Report which items are linked from where, and flag links to `outside-org` items
  (those links will break, because those files can only be copied).
- Step 3 (safety copies): `./gdm login-writer EMAIL`, then `./gdm safety-copy` with the
  departed owners' emails and `--outside-org` (preview first, see safety rule 4).
- Step 4 (UIT request): fill in the template in START-HERE.html (Appendix D) from
  summary.json, inventory.csv and departed-owners.txt.
- Steps 5 and 8 (verify): `./gdm verify <inventory.csv> "<shared drive link>"` and
  explain verify.csv: every row should say "in shared drive", except `outside-org`
  items, which stay behind.
- Step 7 (access): list the people and groups in folder-sharing.csv to add as
  shared drive members.

Results are in `results/`. Keep them; they are the record of the migration.
