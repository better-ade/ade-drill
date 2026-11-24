#!/bin/bash
# Drill: the ade-cli README's user flow on a raw Ubuntu server or desktop (story D4): Claude Code, the Telegram bot,
# then five focus agents from one Telegram message, with a stand-in for every account. Each target is a fresh
# ubuntu:24.04 container of its own, thrown away afterwards; drills/raw/run.py is the person inside it.
#   RAW_TARGET=server  bash drills/raw-ubuntu.sh   ubuntu:24.04 as published, plus sudo and a normal user (the default)
#   RAW_TARGET=desktop bash drills/raw-ubuntu.sh   plus what Ubuntu Desktop 24.04 ships that matters here, and Xvfb
# GOLDEN_ADE_REF (empty: the release; main: the README's git clone line), GOLDEN_BRAIN_REF (the hub template, default
# main), GOLDEN_OUT (report.md and transcripts/; default drills/raw/out), RAW_CACHE (the drill's Python, kept between
# runs). With ADE_DRILL_TELEGRAM_TOKEN and ADE_DRILL_TELEGRAM_CHAT set, what the bot sends also goes to that real chat;
# they reach the container by name only (docker exec -e NAME), never on a command line. Needs Docker and the network.
set -u; here="$(cd "$(dirname "$0")" && pwd)"; repo="$(dirname "$here")"
target="${RAW_TARGET:-server}"
case "$target" in server|desktop) ;; *) echo "DRILL FAIL: RAW_TARGET is server or desktop" >&2; exit 1 ;; esac
command -v docker >/dev/null 2>&1 || { echo "DRILL FAIL: the raw-ubuntu drill needs Docker" >&2; exit 1; }
out="${GOLDEN_OUT:-$here/raw/out}"; mkdir -p "$out" && chmod 777 "$out" || exit 1
cache="${RAW_CACHE:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ade-raw-cache}"; mkdir -p "$cache" || exit 1

# the drill's own Python (python-build-standalone, pinned by its sha256): runs the harness and the stand-ins, never on
# the person's PATH
PY_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20251014/cpython-3.12.12+20251014-x86_64-unknown-linux-gnu-install_only.tar.gz
PY_SHA=1ab2b6594d1c3d76cbebea09d6bc3e6ba68d8eb3b6322080375c4cc3dd188f34
if [ ! -x "$cache/python/bin/python3" ]; then
  curl -fsSL --retry 3 -o "$cache/python.tar.gz" "$PY_URL" || { echo "DRILL FAIL: could not download the drill's Python" >&2; exit 1; }
  got="$( (sha256sum "$cache/python.tar.gz" 2>/dev/null || shasum -a 256 "$cache/python.tar.gz") | cut -d' ' -f1)"
  [ "$got" = "$PY_SHA" ] || { rm -f "$cache/python.tar.gz"; echo "DRILL FAIL: the drill's Python has sha256 $got, not $PY_SHA" >&2; exit 1; }
  rm -rf "$cache/python" && tar -xzf "$cache/python.tar.gz" -C "$cache" || exit 1
fi

# what the person already has, prepared here (the container has no git yet): the hub template the stand-in GitHub
# copies, the person's five repos, and the README the flow is read from
data="$(mktemp -d "${TMPDIR:-/tmp}/ade-raw-data.XXXXXX")" || exit 1; trap 'rm -rf "$data"' EXIT
git clone -q --depth 1 --branch "${GOLDEN_BRAIN_REF:-main}" https://github.com/better-ade/ade-brain "$data/ade-brain" || { echo "DRILL FAIL: could not clone ade-brain" >&2; exit 1; }
readme_ref="${GOLDEN_ADE_REF:-main}"
curl -fsSL --retry 3 -o "$data/README.md" "https://raw.githubusercontent.com/better-ade/ade-cli/$readme_ref/README.md" || { echo "DRILL FAIL: could not read ade-cli's README at $readme_ref" >&2; exit 1; }
for i in 1 2 3 4 5; do
  r="$data/repos/svc-$i"; mkdir -p "$r" && printf '# svc-%s\n\nOne of the five repos the person already has.\n' "$i" > "$r/README.md"
  git -C "$r" init -q -b main && git -C "$r" add -A && git -C "$r" -c user.name=Someone -c user.email=someone@example.invalid commit -q -m "svc-$i" || exit 1
done
chmod -R a+rX "$data"

# the image: ubuntu:24.04, the person `you` in the sudo group (as an installer's first user is) with password-less sudo (every use logged), the apt hook for the stand-ins
common='RUN useradd -m -s /bin/bash -G sudo you && printf "you ALL=(ALL) NOPASSWD:ALL\nDefaults logfile=/var/log/sudo-drill.log, log_year, loglinelen=0\n" > /etc/sudoers.d/you && chmod 440 /etc/sudoers.d/you \
 && printf "DPkg::Post-Invoke { \"sh /drill/drills/raw/stand-ins.sh || true\"; };\n" > /etc/apt/apt.conf.d/99drill-stand-ins && touch /etc/ade-raw-drill \
 && for t in curl git tmux gh gitleaks; do if command -v $t; then echo "the image has $t" >&2; exit 1; fi; done'
if [ "$target" = server ]; then
  df="FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends sudo && rm -rf /var/lib/apt/lists/*
$common"
else
  # Ubuntu Desktop 24.04's own packages that matter here (the 24.04.5 desktop manifest, docs/stories/D4), and Xvfb as
  # its screen; command-not-found needs its index, which apt-get update builds; the lists stay, as a desktop keeps them
  df="FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends sudo python3 wget xdg-utils ca-certificates procps unzip x11-utils command-not-found xvfb && apt-get update
$common"
fi
image="ade-raw-$target:drill"
printf '%s\n' "$df" | docker build -q -t "$image" - >/dev/null || { echo "DRILL FAIL: could not build the $target image" >&2; exit 1; }

name="ade-raw-$target-$$"
docker run -d --name "$name" -v "$repo:/drill:ro" -v "$cache/python:/opt/drill/python:ro" -v "$data:/drill-data:ro" -v "$out:/out" \
  "$image" sleep infinity >/dev/null || { echo "DRILL FAIL: could not start the container" >&2; exit 1; }
trap 'docker rm -f "$name" >/dev/null 2>&1; rm -rf "$data"' EXIT
display=()
if [ "$target" = desktop ]; then docker exec -d "$name" Xvfb :99 -screen 0 1280x800x24 -nolisten tcp || exit 1; display=(-e DISPLAY=:99); fi
docker exec -u you -w /home/you -e HOME=/home/you -e USER=you -e RAW_TARGET="$target" -e GOLDEN_ADE_REF="${GOLDEN_ADE_REF:-}" \
  -e GOLDEN_OUT=/out -e RAW_DATA=/drill-data -e ADE_DRILL_TELEGRAM_TOKEN -e ADE_DRILL_TELEGRAM_CHAT "${display[@]}" \
  "$name" /opt/drill/python/bin/python3 -I /drill/drills/raw/run.py
