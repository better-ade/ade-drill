#!/bin/bash
# Shared by every drill. A drill prints "ok" as its last line and exits 0, or fails with a reason.
set -u
ORG="${DRILL_ORG:-https://github.com/better-ade}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ade-drill.XXXXXX")"; trap 'rm -rf "$WORK"' EXIT
fail() { echo "DRILL FAIL: $*" >&2; exit 1; }
# clone <repo> [ref]: a shallow clone of a better-ade repo at main (or ref) into $WORK/<repo>; prints the path
clone() { local d="$WORK/$1"; git clone -q --depth 1 ${2:+--branch "$2"} "$ORG/$1" "$d" || fail "could not clone $1 ${2:-main}"; echo "$d"; }
# tag_exists <repo> <tag>
tag_exists() { [ -n "$(git ls-remote --tags "$ORG/$1" "refs/tags/$2" 2>/dev/null)" ]; }
