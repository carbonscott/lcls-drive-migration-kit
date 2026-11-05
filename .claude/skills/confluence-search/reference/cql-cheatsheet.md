# CQL cheat sheet

Distilled from the archived Atlassian docs in `../../docs/md/`, then **verified
against `confluence.slac.stanford.edu`** (Confluence Data Center) on 2026-08-12.
Where this instance disagrees with the published docs, this file follows the
instance.

## Endpoints

| Endpoint | Returns | Notes |
|---|---|---|
| `GET /rest/api/search?cql=…` | content + spaces + users | Has `excerpt`, `friendlyLastModified`, `url`. **Use this.** |
| `GET /rest/api/content/search?cql=…` | content only | No excerpts; plain content objects. |
| `GET /rest/api/content/{id}?expand=body.view` | one page's body | Also `version`, `space`, `ancestors`. |
| `GET /rest/api/space?limit=100&start=N` | space list | Paginate via `_links.next`. |

Common query params: `limit` (200 accepted), `start` (offset paging),
`expand` (`content.space`, `content.version`, `content.ancestors`,
`content.body.view`), `excerpt` (`highlight` | `indexed` | `none`).

Auth header: `Authorization: Bearer <personal-access-token>`.

## Anatomy

```
space = PSDM AND type = page AND text ~ "detector calibration" ORDER BY lastmodified DESC
└─field─┘ │  └value┘                    └─── operator + quoted value ───┘  └─── sort ───┘
          └ operator
```

## Fields

| Field | Example |
|---|---|
| `text` | `text ~ "psana"` — body **and** title |
| `title` | `title ~ "geometry"` |
| `siteSearch` | `siteSearch ~ "calibration"` — ranks like the UI search box |
| `space` | `space = PSDM`, `space in (PSDM, PSDMInternal)` |
| `space.key` `space.title` `space.type` `space.category` | `space.type = global` |
| `type` | `type = page` \| `blogpost` \| `attachment` \| `comment` |
| `id` | `id = 146707279` |
| `parent` | `parent = 146707279` — direct children only |
| `ancestor` | `ancestor = 146707279` — whole subtree (186 hits for the psana root) |
| `container` | content inside a given space/page |
| `created` `lastmodified` | `lastmodified > "2026-01-01"` |
| `creator` `contributor` | `creator = currentUser()` |
| `mention` `watcher` | `mention = jsmith` |
| `label` | `label = "psana"` |
| `macro` | `macro = toc` — pages using a macro |
| `content` | `content = 146707279` |

**Not available on this instance:** `status`. The server replies
`No field exists with the name: 'status'`. There is no CQL-level way to filter
archived vs current content here.

## Operators

| Operator | Meaning | Caveat |
|---|---|---|
| `=` `!=` | exact match | **Not valid on `text`** — use `~` |
| `>` `>=` `<` `<=` | ranges | dates and numbers |
| `in` `not in` | set membership | `space in (PSDM, LCLSIIData)` |
| `~` `!~` | contains / does not contain | the one you want for prose |

Keywords: `AND`, `OR`, `NOT`, `ORDER BY … ASC|DESC`. Parentheses set precedence.
Keywords are case-insensitive; **space keys are case-sensitive**.

## Functions

Verified working here: `currentUser()`, `now("-7d")`, `startOfDay()`,
`endOfDay()`, `startOfWeek()`, `endOfWeek()`, `startOfMonth()`, `endOfMonth()`,
`startOfYear()`, `endOfYear()`, `favouriteSpaces()`, `recentlyViewedContent()`,
`recentlyViewedSpaces()`.

Date offsets take `w` weeks, `d` days, `h` hours, `m` minutes:
`created > now("-30d")`.

## Text-search syntax (inside `~ "…"`)

- Multiple words are OR-ed and relevance-ranked; quote a phrase inside the value
  for adjacency.
- `*` is a suffix wildcard: `text ~ "detect*"`. No leading wildcards.
- `+` requires a term, `-` excludes it: `text ~ "+psana -lcls2"`.
- Reserved characters (`+ - & | ! ( ) { } [ ] ^ ~ * ? \ :`) need escaping with `\`.
- Confluence applies English stemming, so `calibrate` also matches `calibration`.

## Result shape (`/rest/api/search`)

```json
{ "totalSize": 3323, "size": 3, "start": 0, "limit": 3, "cqlQuery": "...",
  "results": [ { "title": "…", "excerpt": "…@@@hl@@@detector@@@endhl@@@…",
                 "url": "/spaces/PSDM/pages/349278859/Detector+Calibration…",
                 "friendlyLastModified": "Apr 14, 2026",
                 "content": { "id": "349278859", "type": "page",
                              "space": {"key": "PSDM"}, "version": {…} } } ] }
```

- `@@@hl@@@` / `@@@endhl@@@` wrap the matched terms in `excerpt`. Strip or convert
  them before showing a user (`cqlsearch.py` does this).
- `url` is site-relative — prefix `https://confluence.slac.stanford.edu`.
- `totalSize` is the true match count; `size` is what this page returned.

## Errors and limits

| Symptom | Cause / fix |
|---|---|
| HTTP 400 `No field exists with the name: 'x'` | typo'd field; message names the valid neighbours |
| HTTP 429 `Rate limit exceeded` | ~1 req/s sustained trips it; back off ≥10 s and retry |
| `CERTIFICATE_VERIFY_FAILED` | uv-managed pythons miss SLAC's CA. `export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt` |
| Results are all `.png` / `.vtt` | add `and type = page` |

## Measured scope (2026-08-12)

| Query | `totalSize` |
|---|---|
| `type = page` (whole instance) | 57,666 |
| `type in (page, blogpost, attachment, comment)` | 262,516 |
| `space = PSDM and type = page` | 233 |
| `space = PSDMInternal and type = page` | 872 |
| spaces visible to the token | 207 global |
| SQLite ETL snapshot, for comparison | 1,364 docs |
