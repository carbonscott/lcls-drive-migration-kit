#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""cqlsearch — query SLAC Confluence live via the CQL search REST API.

Standard library only, so it runs either way:

  uv run cqlsearch.py search 'space = PSDM and text ~ "psana"' --limit 10
  ./cqlsearch.py text "detector calibration" --space PSDM   # uv via shebang
  python3 cqlsearch.py page 146707279                       # python3 >= 3.9 only
  uv run cqlsearch.py spaces

Auth: a Confluence Data Center personal access token (Bearer), resolved in
order from $CONFLUENCE_TOKEN, $CONFLUENCE_TOKEN_FILE, then
~/.config/confluence-search/token. Per-user by design — there is no shared
default, so a central install never authenticates everyone as one account.
Run the sibling `confluence-login` to install your token, `whoami` to see which
identity you are using.
"""
from __future__ import annotations

import argparse
import getpass
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import pwd                      # unix only; absent on Windows
except ImportError:                 # pragma: no cover
    pwd = None

BASE = os.environ.get("CONFLUENCE_URL", "https://confluence.slac.stanford.edu")
PAT_URL = f"{BASE}/plugins/personalaccesstokens/usertokens.action"

# Setup instructions must point at *this* file, not at install.sh: install.sh
# lives in the repo, and a user of a central deployment has only the deployed
# skill directory (SKILL.md, reference/, scripts/). Absolute, so the hint stays
# correct after the reader cd's somewhere else.
SELF = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "cqlsearch.py"

# The command to hand a user who needs a token. `confluence-login` is a sibling
# wrapper shipped in the same scripts/ directory; fall back to the subcommand
# when cqlsearch.py was copied somewhere on its own.
_WRAPPER = os.path.join(os.path.dirname(SELF), "confluence-login")
LOGIN_CMD = _WRAPPER if os.path.exists(_WRAPPER) else f"{SELF} login"

# `whoami` as a command the USER pastes into their own terminal, right after
# confluence-login. That shell usually has no uv on PATH: confluence-login
# sources env.sh for itself, and that does not outlive it. So name env.sh
# explicitly, and wrap it in `bash -c` so it also works from tcsh or zsh.
_ENV_SH = os.path.join(os.path.dirname(os.path.dirname(SELF)), "env.sh")
WHOAMI_CMD = (f"bash -c 'source \"{_ENV_SH}\" && \"{SELF}\" whoami'"
              if os.path.exists(_ENV_SH) else f"{SELF} whoami")


def home_dir() -> str:
    """The invoking user's home.

    $HOME is inherited, so it lies under sudo, cron, and service accounts. The
    passwd database does not.
    """
    if pwd is not None:
        try:
            return pwd.getpwuid(os.getuid()).pw_dir
        except KeyError:
            pass
    return os.path.expanduser("~")


def default_token_file() -> str:
    """Per-user, by construction — never a shared path.

    A shared default would mean every user of a central install silently
    authenticating as whoever owns that file, seeing that account's view of the
    wiki. Deliberately absent: point CONFLUENCE_TOKEN_FILE at a shared file if
    you actually want that.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home_dir(), ".config")
    return os.path.join(xdg, "confluence-search", "token")


TOKEN_FILE = os.environ.get("CONFLUENCE_TOKEN_FILE") or default_token_file()

# S3DF nodes trust SLAC's internal CA through the system bundle; the uv-managed
# pythons look for /etc/ssl/cert.pem instead and fail verification without this.
CA_CANDIDATES = ("/etc/pki/tls/certs/ca-bundle.crt",
                 "/etc/ssl/certs/ca-certificates.crt")

HL_OPEN, HL_CLOSE = "@@@hl@@@", "@@@endhl@@@"
MAX_LIMIT = 200          # server accepts at least this much per page
PAGE_DELAY = 1.0         # between pages of a --all sweep


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

def ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE")
    if not cafile:
        cafile = next((c for c in CA_CANDIDATES if os.path.exists(c)), None)
    return ssl.create_default_context(cafile=cafile)


MINT_HELP = f"""\
You need a Confluence personal access token of your own — search results are
filtered by *your* wiki permissions, so this is not a credential anyone can
share with you.

There is no API for the first one (this instance has basic auth disabled), so
mint it in a browser, and set an expiry — tokens here default to never expiring:
    {PAT_URL}"""

SETUP_HELP = f"""\
error: no Confluence token.

Every user needs their own — results are filtered by *your* wiki permissions.

  1. mint one (browser; there is no API for the first token, this instance
     has basic auth disabled):
       {PAT_URL}
  2. install it — prompts without echoing, writes {TOKEN_FILE} mode 600:
       {LOGIN_CMD}

That is the whole setup, and it is yours alone to do: results are filtered by
your own wiki permissions, so nobody can install this token for you.

Or set CONFLUENCE_TOKEN / CONFLUENCE_TOKEN_FILE to override."""


def token_source() -> str:
    """Where the token came from. Never returns the token itself."""
    if os.environ.get("CONFLUENCE_TOKEN"):
        return "$CONFLUENCE_TOKEN"
    return TOKEN_FILE


def read_token_file(path: str) -> str:
    try:
        mode = os.stat(path).st_mode
    except OSError as e:
        sys.exit(f"error: cannot stat {path}: {e}")
    if mode & 0o077:
        # Group trees here are setgid and group-writable, so an inherited umask
        # leaks the token easily. Fail at setup rather than quietly.
        sys.exit(f"error: {path} is readable by group or others "
                 f"(mode {mode & 0o777:03o}).\n"
                 f"  fix: chmod 600 {path}")
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError as e:
        sys.exit(f"error: cannot read {path}: {e}")


def get_token() -> str:
    tok = os.environ.get("CONFLUENCE_TOKEN")
    if tok:
        return tok.strip()
    if not os.path.exists(TOKEN_FILE):
        sys.exit(SETUP_HELP)
    tok = read_token_file(TOKEN_FILE)
    if not tok:
        sys.exit(f"error: {TOKEN_FILE} is empty.\n\n{SETUP_HELP}")
    return tok


class Client:
    """Thin GET client with 429 backoff. The SLAC instance rate-limits."""

    def __init__(self, verbose: bool = False, token: str = ""):
        self.ctx = ssl_context()
        # `login` passes the token it just wrote, so its check tests that token
        # and not whatever $CONFLUENCE_TOKEN would otherwise win with.
        self.token = token or get_token()
        self.verbose = verbose

    def get(self, path: str, params: dict, tries: int = 5) -> dict:
        url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })
        delay = 10.0
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=60, context=self.ctx) as r:
                    return json.loads(r.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")
                if e.code == 429 and attempt < tries - 1:
                    wait = float(e.headers.get("Retry-After") or delay)
                    if self.verbose:
                        print(f"  (429 rate limited, sleeping {wait:.0f}s)",
                              file=sys.stderr)
                    time.sleep(wait)
                    delay *= 2
                    continue
                if e.code == 400:
                    sys.exit(f"CQL error (HTTP 400): {extract_message(body)}")
                if e.code == 401:
                    sys.exit(f"error: HTTP 401 — token rejected. It is invalid, "
                             f"expired, or revoked.\n"
                             f"  token came from: {token_source()}\n"
                             f"  mint a new one:  {PAT_URL}\n"
                             f"  then install it: {LOGIN_CMD} --force")
                sys.exit(f"HTTP {e.code} for {path}: {extract_message(body)}")
            except urllib.error.URLError as e:
                sys.exit(f"network/TLS error for {path}: {e.reason}\n"
                         f"hint: export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt")
        sys.exit("error: retries exhausted (rate limited)")


def extract_message(body: str) -> str:
    try:
        return json.loads(body).get("message", body[:300])
    except Exception:  # noqa: BLE001
        return body[:300]


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def clean_excerpt(text: str, markers: bool = False) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    if markers:
        text = text.replace(HL_OPEN, "**").replace(HL_CLOSE, "**")
    else:
        text = text.replace(HL_OPEN, "").replace(HL_CLOSE, "")
    return " ".join(text.split())


SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")
COMMENT_RE = re.compile(r"(?s)<!--.*?-->")


def strip_noise(markup: str) -> str:
    """Drop <script>, <style>, and comments. Everything else is kept verbatim.

    Page bodies are handed to an LLM, which reads HTML natively — links, heading
    levels, table structure and code blocks all carry meaning and are left alone.
    Only markup that renders to nothing is removed.
    """
    return COMMENT_RE.sub("", SCRIPT_STYLE_RE.sub("", markup)).strip()


def print_hit(i: int, r: dict, markers: bool) -> None:
    c = r.get("content", {}) or {}
    title = clean_excerpt(r.get("title") or c.get("title") or "(untitled)", markers)
    ctype = c.get("type") or r.get("entityType") or "?"
    space = (c.get("space") or {}).get("key") or ""
    ident = c.get("id") or ""
    url = r.get("url") or ""
    if url.startswith("/"):
        url = BASE + url
    print(f"\n[{i}] {title}")
    meta = [b for b in (ctype, f"space={space}" if space else "",
                        f"id={ident}" if ident else "",
                        r.get("friendlyLastModified", "")) if b]
    print(f"    {'  |  '.join(meta)}")
    if url:
        print(f"    {url}")
    ex = clean_excerpt(r.get("excerpt", ""), markers)
    if ex:
        print(f"    {ex[:400]}")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_search(args) -> int:
    client = Client(verbose=args.verbose)
    params = {"cql": args.cql, "limit": min(args.limit, MAX_LIMIT),
              "start": args.start, "excerpt": args.excerpt}
    if args.expand:
        params["expand"] = args.expand
    elif not args.json:
        params["expand"] = "content.space,content.version"

    data = client.get("/rest/api/search", params)
    results = data.get("results", [])
    total = data.get("totalSize")

    if args.all and total and total > len(results):
        want = args.limit if args.limit < MAX_LIMIT else total
        start = args.start + len(results)
        while len(results) < min(want, total) and start < total:
            time.sleep(PAGE_DELAY)
            params["start"] = start
            page = client.get("/rest/api/search", params)
            batch = page.get("results", [])
            if not batch:
                break
            results.extend(batch)
            start += len(batch)
        results = results[:want]

    if args.json:
        json.dump({"cql": args.cql, "totalSize": total, "returned": len(results),
                   "results": results}, sys.stdout, indent=2)
        print()
        return 0

    print(f"cql: {args.cql}")
    print(f"{total} match(es); showing {len(results)}")
    for i, r in enumerate(results, 1):
        print_hit(i, r, args.markers)
    if total and total > len(results):
        print(f"\n... {total - len(results)} more; "
              f"use --start {args.start + len(results)} or --all")
    return 0


def cmd_text(args) -> int:
    """Convenience wrapper that builds the CQL for you."""
    words = args.words.replace('"', r"\"")
    clauses = [f'{args.field} ~ "{words}"']
    if args.space:
        keys = ", ".join(args.space)
        clauses.append(f"space = {keys}" if len(args.space) == 1
                       else f"space in ({keys})")
    if args.type:
        clauses.append(f"type = {args.type}")
    if args.since:
        clauses.append(f'lastmodified > "{args.since}"')
    cql = " and ".join(clauses)
    if args.recent:
        cql += " order by lastmodified desc"
    args.cql = cql
    return cmd_search(args)


PAGE_ID_RE = re.compile(r"(?:pageId=|/pages/(?:viewpage\.action\?pageId=)?)(\d+)")

# --format name -> the body representation Confluence expands under. There is no
# Markdown representation; every one of these is markup.
BODY_KEY = {"view": "view", "export": "export_view",
            "storage": "storage", "json": "view"}


def cmd_page(args) -> int:
    client = Client(verbose=args.verbose)
    target = args.target
    m = PAGE_ID_RE.search(target)
    if m:
        page_id = m.group(1)
    elif target.isdigit():
        page_id = target
    else:
        hits = client.get("/rest/api/content/search",
                          {"cql": f'title = "{target}"', "limit": 1})
        rs = hits.get("results", [])
        if not rs:
            sys.exit(f"no page titled {target!r}")
        page_id = rs[0]["id"]

    body_key = BODY_KEY[args.format]
    data = client.get(f"/rest/api/content/{page_id}",
                      {"expand": f"body.{body_key},version,space,ancestors"})
    title = data.get("title", "")
    space = (data.get("space") or {}).get("key", "")
    ver = data.get("version") or {}
    crumb = " > ".join(a.get("title", "?") for a in data.get("ancestors", []))
    body = ((data.get("body") or {}).get(body_key) or {}).get("value", "")

    if args.format == "json":
        json.dump(data, sys.stdout, indent=2)
        print()
        return 0
    out = strip_noise(body)

    header = (f"# {title}\n\n"
              f"- space: {space}\n"
              f"- id: {page_id}\n"
              f"- version: {ver.get('number')} by "
              f"{(ver.get('by') or {}).get('displayName')} ({ver.get('when')})\n"
              f"- breadcrumb: {crumb}\n"
              f"- url: {BASE}/pages/viewpage.action?pageId={page_id}\n\n---\n\n")
    text = header + out
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
        print(f"wrote {args.out} ({len(text)} chars)")
    else:
        print(text)
    return 0


def print_identity(me: dict, source: str) -> None:
    print(f"{me.get('displayName') or '?'} <{me.get('username') or '?'}>")
    print(f"  instance: {BASE}")
    print(f"  token:    {source}")
    print("  note:     search results are filtered by your own permissions —")
    print("            another account sees a different set of spaces.")


def cmd_whoami(args) -> int:
    """One cheap call that proves the token works and says who it belongs to."""
    me = Client(verbose=args.verbose).get("/rest/api/user/current", {})
    print_identity(me, token_source())
    return 0


def collect_token(from_file: str) -> str:
    """The token, from a file, a pipe, or a hidden prompt. Never echoed."""
    if from_file:
        try:
            with open(from_file) as f:
                raw = f.read()
        except OSError as e:
            sys.exit(f"error: cannot read {from_file}: {e}")
    elif not sys.stdin.isatty():
        # `pass show confluence | cqlsearch.py login` — and how install.sh
        # forwards a piped token.
        raw = sys.stdin.read()
    else:
        print(MINT_HELP)
        print()
        try:
            raw = getpass.getpass("Paste token (input hidden, Enter when done): ")
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit("error: aborted; nothing was written.")
    tok = raw.strip()
    if not tok:
        sys.exit("error: empty token; nothing was written.")
    return tok


def write_token_file(path: str, token: str, force: bool) -> None:
    """Write the token so it is never, even briefly, readable by anyone else.

    O_CREAT|O_EXCL with mode 600 rather than write-then-chmod: on a shared
    filesystem the gap between those two is a window in which the token is
    world-readable. --force unlinks first so the new file really is created
    here — O_CREAT leaves an existing file's mode alone.
    """
    if os.path.lexists(path) and not force:
        sys.exit(f"error: {path} already exists; nothing was written.\n"
                 f"  re-run with --force to replace it "
                 f"(the old token is not recoverable afterwards).")
    old_umask = os.umask(0o077)          # covers the parent dirs makedirs creates
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, mode=0o700, exist_ok=True)
        if os.path.lexists(path):
            os.unlink(path)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token + "\n")
    except OSError as e:
        sys.exit(f"error: cannot write {path}: {e}")
    finally:
        os.umask(old_umask)


def cmd_login(args) -> int:
    """Install this user's token.

    Lives in this script rather than only in install.sh because this script is
    the one file that exists wherever the skill is deployed; install.sh stays
    behind in the repo, which end users of a central deployment never see.
    """
    token = collect_token(args.from_file)
    write_token_file(TOKEN_FILE, token, args.force)
    # flush: the verify call below writes to stderr, and a piped install log
    # otherwise shows the failure before the write it refers to.
    print(f"wrote {TOKEN_FILE} (mode 600)", flush=True)

    if os.environ.get("CONFLUENCE_TOKEN"):
        print("warning: $CONFLUENCE_TOKEN is set and takes precedence over the "
              "file.\n         Unset it, or the token just written is ignored.",
              file=sys.stderr)

    if args.no_verify:
        return 0
    try:
        me = Client(verbose=args.verbose, token=token).get("/rest/api/user/current", {})
    except SystemExit as e:      # Client.get() exits on HTTP/TLS failure
        print(f"\n{e}", file=sys.stderr)
        print(f"\nwarning: {TOKEN_FILE} was written, but the check above failed.\n"
              f"         The token may be wrong (a truncated paste is the usual\n"
              f"         cause) — or this instance rate-limited the check; it\n"
              f"         does that readily. Try this in a minute:\n"
              f"           {WHOAMI_CMD}",
              file=sys.stderr)
        return 1
    print()
    print_identity(me, TOKEN_FILE)
    return 0


def cmd_spaces(args) -> int:
    client = Client(verbose=args.verbose)
    start, rows = 0, []
    while True:
        d = client.get("/rest/api/space", {"limit": 100, "start": start,
                                           "type": args.type})
        batch = d.get("results", [])
        rows.extend(batch)
        if len(batch) < 100:
            break
        start += len(batch)
        time.sleep(PAGE_DELAY)
    for s in sorted(rows, key=lambda s: s.get("key", "")):
        if args.filter and args.filter.lower() not in json.dumps(s).lower():
            continue
        print(f"{s.get('key', ''):<20} {s.get('type', ''):<10} {s.get('name', '')}")
    print(f"\n{len(rows)} spaces visible to this token")
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cqlsearch",
        description="Query SLAC Confluence live via the CQL search API.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_search_flags(sp):
        sp.add_argument("--limit", type=int, default=10)
        sp.add_argument("--start", type=int, default=0)
        sp.add_argument("--all", action="store_true",
                        help="paginate until --limit (or everything) is collected")
        sp.add_argument("--json", action="store_true", help="raw JSON results")
        sp.add_argument("--expand", default="",
                        help="e.g. content.body.view,content.ancestors")
        sp.add_argument("--excerpt", default="highlight",
                        choices=["highlight", "indexed", "none"])
        sp.add_argument("--markers", action="store_true",
                        help="keep search highlights as **bold** in excerpts")

    s = sub.add_parser("search", help="run a raw CQL query")
    s.add_argument("cql")
    add_search_flags(s)
    s.set_defaults(func=cmd_search)

    t = sub.add_parser("text", help="free-text search; builds the CQL for you")
    t.add_argument("words")
    t.add_argument("--space", action="append",
                   help="space key; repeatable (PSDM, PSDMInternal, ...)")
    t.add_argument("--type", help="page | blogpost | attachment | comment")
    t.add_argument("--since", help='e.g. "2026-01-01" or "now(-30d)"')
    t.add_argument("--field", default="text",
                   choices=["text", "title", "siteSearch"],
                   help="text=body+title, siteSearch=whole-site relevance ranking")
    t.add_argument("--recent", action="store_true",
                   help="order by lastmodified desc instead of relevance")
    add_search_flags(t)
    t.set_defaults(func=cmd_text)

    g = sub.add_parser("page", help="fetch one page by id, URL, or exact title")
    g.add_argument("target")
    g.add_argument("--format", default="view",
                   choices=["view", "export", "storage", "json"],
                   help="body representation: view=rendered HTML (default), "
                        "export=export_view HTML, storage=Confluence storage "
                        "format, json=full API response")
    g.add_argument("--out", help="write to file instead of stdout")
    g.set_defaults(func=cmd_page)

    lg = sub.add_parser("login", help=f"install your token into {TOKEN_FILE}")
    lg.add_argument("--from", dest="from_file", metavar="FILE",
                    help="read the token from FILE instead of prompting")
    lg.add_argument("--force", action="store_true",
                    help="replace an existing token file")
    lg.add_argument("--no-verify", action="store_true",
                    help="skip the one live call that confirms the token works")
    lg.set_defaults(func=cmd_login)

    w = sub.add_parser("whoami", help="who this token authenticates as")
    w.set_defaults(func=cmd_whoami)

    sp = sub.add_parser("spaces", help="list spaces this token can see")
    sp.add_argument("--type", default="global", choices=["global", "personal"])
    sp.add_argument("--filter", help="substring filter")
    sp.set_defaults(func=cmd_spaces)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
