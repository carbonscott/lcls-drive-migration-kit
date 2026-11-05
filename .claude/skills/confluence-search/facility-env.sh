#!/bin/bash
# Site detection for confluence-search skill.
# Sets CONFLUENCE_SEARCH_BIN with a facility-appropriate default: the directory
# holding the shared uv, so the PEP 723 scripts' `uv run --script` shebang
# resolves without a personal ~/.local/bin/uv.
# Can always be overridden by setting CONFLUENCE_SEARCH_BIN before sourcing.

if [ -d /sdf ]; then
    # S3DF (SLAC)
    export CONFLUENCE_SEARCH_BIN="${CONFLUENCE_SEARCH_BIN:-/sdf/group/lcls/ds/dm/apps/dev/bin}"
elif [ -d /lustre/orion ]; then
    # OLCF (Frontier)
    export CONFLUENCE_SEARCH_BIN="${CONFLUENCE_SEARCH_BIN:-/ccs/home/cwang31/.local/bin}"
fi

if [ -n "${CONFLUENCE_SEARCH_BIN:-}" ]; then
    export PATH="$CONFLUENCE_SEARCH_BIN:$PATH"
fi
