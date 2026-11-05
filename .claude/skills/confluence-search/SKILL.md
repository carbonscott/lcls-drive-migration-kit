---
name: confluence-search
description: Search SLAC Confluence live using CQL (Confluence Query Language) via the REST search API. Covers every space your account can see (~200 spaces, tens of thousands of pages), not just the exported PSDM subset. Use for questions about LCLS docs, psana, AMI, smalldata_tools, detectors, DAQ, experiment procedures, meeting notes, or any SLAC wiki content; also for "who wrote/changed X", "what changed recently", "find the page about X".
---

# Confluence live search (CQL)

Query `confluence.slac.stanford.edu` directly. Unlike the SQLite snapshot at
`/sdf/group/lcls/ds/dm/apps/dev/data/confluence-doc/lcls-docs.db` (1,364 docs,
PSDM + PSDMInternal only, rebuilt nightly), this searches **every space the
user's own account can see, always current** — around 200 spaces and tens of
thousands of pages for a typical LCLS account.

Results are filtered by the token owner's permissions, so coverage differs
between users. `cqlsearch.py whoami` says which identity is in play.

## Running the script

No venv, no `pip install`, no dependencies — the script carries PEP 723 inline
metadata and uses only the standard library, so all three of these work. (A
token is the one thing you do need; see **Auth** below.)

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR}"                       # this skill's directory, filled in for you
source "$SKILL_DIR/env.sh"                            # puts the shared uv on PATH
CQL="$SKILL_DIR/scripts/cqlsearch.py"                 # see below
uv run --script "$CQL" text "detector calibration"    # preferred
"$CQL"          text "detector calibration"           # shebang runs it through uv
python3 "$CQL"  text "detector calibration"           # only if python3 is >= 3.9
```

Source `env.sh` in the *same* bash command as the script — each command runs in a
fresh shell, so a `source` from an earlier one is already gone. It puts the
facility's shared `uv` on `PATH` (S3DF `/sdf/group/lcls/ds/dm/apps/dev/bin`, OLCF
`/ccs/home/cwang31/.local/bin`) and sets a per-user uv cache, so these commands
work without a personal `~/.local/bin/uv`.

**Use `uv` unless you know the local `python3` is 3.9 or newer.** The script
declares `requires-python = ">=3.9"` and uv provisions that automatically; the
system python on SLAC login nodes is 3.6 and cannot parse the file at all
(`SyntaxError: future feature annotations is not defined`).

`SKILL_DIR` above is the absolute path of the directory holding this
`SKILL.md`. Claude Code fills it in when it loads the skill, and the shared
opencode deployment has it written in at deploy time. If it is not an absolute
path as you read it, use the "Base directory for this skill" path printed when
the skill loaded. Do not guess `~/.claude/skills/confluence-search`: claude-lcls
keeps its skills under `~/.claude-lcls/skills`, and opencode under its own
config directory.

Examples below use `uv run`. Copy `cqlsearch.py` anywhere you like — it is
standard-library-only and has no repo-relative dependencies.

## Auth

Each user needs their own personal access token. It is resolved in this order:

1. `$CONFLUENCE_TOKEN`
2. `$CONFLUENCE_TOKEN_FILE`
3. `~/.config/confluence-search/token` — the default

There is deliberately **no shared fallback path**, so a central install never
authenticates everyone as one account. If the token is missing the script prints
setup instructions; if it is group- or world-readable the script refuses to use
it. `CONFLUENCE_URL` points at a different instance.

### Never announce a missing token you have not observed

**Do not tell the user to set up a token unless a command you actually ran just
failed with a token error.** Most users already have one, and being told to redo
setup they completed is worse than useless — it makes them doubt a working
install. The instructions below are a *reaction* to a failure, never a
precondition to check first.

If you are unsure whether auth works, do not guess and do not read it off this
file. Run one cheap command and look at the output:

```bash
uv run --script "$CQL" whoami
```

A name and email means auth is fine — proceed with the real query. Only if a
command exits with an error mentioning the token do the following apply.

### When a command really did fail on the token

Stop and tell the user to set one up themselves, in a terminal of their own. The
command ships in this skill directory, so it works even for someone who only
ever received the deployed skill:

```bash
${CLAUDE_SKILL_DIR}/scripts/confluence-login           # prompts, hidden, writes mode 600
${CLAUDE_SKILL_DIR}/scripts/confluence-login --force   # replace an expired or wrong token
```

Hand it over with the path written out in full, exactly as it appears above,
never as `$SKILL_DIR/...` or `~/.claude/...`. Their terminal has none of your
shell variables, and the skill is not under `~/.claude` for everyone. (If the
path above does not start with `/`, build it from the base-directory path, as
described under **Running the script**.) That one path is all they need:
`confluence-login` loads the shared `uv` itself, so it works from a fresh login
shell with no `uv` on `PATH` and no `source` line first.

It prompts for the token with input hidden, so it needs a real terminal of the
user's own, not your shell.

**Inside opencode-sandbox** (your shell has `APPTAINER_NAME=opencode-sandbox.sif`):
the sandbox hides the user's real home directory and copies the token in only
when it starts. Tell the user to run the command in a normal S3DF terminal,
outside the sandbox, and then quit and restart `opencode-sandbox`. The same goes
for `--force`: a running sandbox keeps the old copy until it restarts.

They mint the token first, in a browser, at
`https://confluence.slac.stanford.edu/plugins/personalaccesstokens/usertokens.action`
— there is no API for the first one.

Quote the error you actually got. If it was HTTP 401 the token exists but is
invalid, expired, or revoked, and they need `--force`; if it was "no Confluence
token" there is nothing installed yet. Those are different problems and the
`--force` flag is the difference.

**Do not** read, print, guess, or type a token yourself, and do not run
`confluence-login` for the user — it prompts them, deliberately, so the secret
never passes through you or through a command line.

## Commands

| Command | Use it for |
|---|---|
| `text "<words>"` | Free-text search. Builds the CQL for you. **Start here.** |
| `search "<cql>"` | A raw CQL query when you need full control. |
| `page <id\|url\|title>` | Fetch one page's full body as HTML. |
| `spaces` | List the spaces this account can see (find the right space key). |
| `whoami` | Which identity the token belongs to. One cheap call; good first check. |

The sibling `scripts/confluence-login` installs the user's own token. See
**Auth** — you never run it for them.

### text — the common case

```bash
uv run "$CQL" text "smalldata producer"                    # whole instance
uv run "$CQL" text "psana" --space PSDM --space PSDMInternal
uv run "$CQL" text "DAQ" --type page --recent              # newest first
uv run "$CQL" text "epix" --since "2026-01-01" --limit 20
uv run "$CQL" text "geometry" --field title                # title only
```

`--field siteSearch` ranks like the Confluence UI's own search box; `--field text`
(default) matches body and title.

### search — raw CQL

```bash
uv run "$CQL" search 'space = LCLSIIData and type = page and text ~ "timing"'
uv run "$CQL" search 'creator = currentUser() order by lastmodified desc'
uv run "$CQL" search 'ancestor = 146707279' --limit 50 --all
uv run "$CQL" search 'label = "psana"' --json
```

### page — read the actual content

Search returns ~300-char excerpts. To answer a real question you usually need the
page body:

```bash
uv run "$CQL" page 337058697                    # metadata header + rendered HTML
uv run "$CQL" page 337058697 --out /tmp/p.html  # save instead of printing
uv run "$CQL" page "Area Detector Interface"    # exact title lookup
uv run "$CQL" page 337058697 --format storage   # Confluence storage format
```

The body comes back as **HTML** — read it directly, don't convert it. Confluence
has no Markdown representation, and flattening the markup destroys exactly what
you need: `<a href>` targets for citing sources, heading levels, table structure,
and code-block boundaries. `<script>`, `<style>`, and comments are stripped;
everything else is verbatim.

`--format` picks the representation: `view` (default, rendered), `export`
(`export_view`, absolute links), `storage` (source form with `<ac:>` macros),
`json` (full API response).

## Workflow

1. **Search broadly first** — `text "<words>"` with no `--space`. The DB-era habit
   of restricting to PSDM/PSDMInternal hides most of the wiki.
2. **Read `totalSize`.** Thousands of hits means the query is too vague; add
   `--space`, `--type page`, or more specific words.
3. **Fetch the promising pages** with `page <id>` — excerpts are fragments and
   routinely mislead.
4. **Cite the URL** printed with each hit so the user can open the source.

## Rules

- **Space keys are case-sensitive** and are *not* the display names. `PSDM`,
  `PSDMInternal`, `LCLSIIData` are the LCLS-relevant ones; use `spaces` to find
  others.
- **`~` for text, `=` for exact.** `title ~ "psana"` matches substrings;
  `title = "psana"` demands the whole title. Using `=` on `text` is an error.
- **Quote multi-word values**: `text ~ "detector calibration"`.
- **Attachments dominate some queries.** `lastmodified > now("-7d")` returns
  mostly `.png`/`.vtt` files; add `and type = page`.
- **Rate limits are real.** The instance returns HTTP 429 under roughly
  1 request/second sustained. The script backs off and retries automatically —
  don't wrap it in a tight loop, and prefer one `--limit 50` call over 50 calls.
- **Never print the token** or paste it into a command line.

## Reference

`reference/cql-cheatsheet.md` (next to this file) — fields, operators, functions,
and the quirks verified against *this* instance. Read it before writing a
non-obvious CQL query.

The source repo also carries offline copies of Atlassian's CQL documentation
under `docs/md/`; those are not part of the installed skill.
