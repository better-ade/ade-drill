#!/bin/bash
# The real tools the golden-path drill needs on a CI runner (it installs none itself): tmux, gitleaks and Playwright's
# Chromium (ade shot takes its pictures with it; every ade since the 0.2.10 release has ade shot).
set -eu
if [ "$(uname -s)" = Darwin ]; then
  command -v tmux >/dev/null 2>&1 || brew install tmux
  command -v gitleaks >/dev/null 2>&1 || brew install gitleaks
else
  command -v tmux >/dev/null 2>&1 || { sudo apt-get update -qq && sudo apt-get install -y -qq tmux; }
  command -v gitleaks >/dev/null 2>&1 || {
    curl -fsSL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz | tar xz gitleaks
    sudo mv gitleaks /usr/local/bin/; }
fi
npx -y playwright install chromium
# a freshly downloaded Chromium's first start on a Mac runner is slow (the system checks the new app), long enough to
# use up ade shot's whole time limit; start it once here so the drill's shot meets a browser that has run before
if [ "$(uname -s)" = Darwin ]; then
  exe="$(find "$HOME/Library/Caches/ms-playwright" -path '*chromium-*' -type f -perm -u+x -name 'Google Chrome for Testing' | sort | tail -1)"
  [ -n "$exe" ] && { s=$(date +%s); perl -e 'alarm 180; exec @ARGV' "$exe" --headless --disable-gpu --no-first-run --dump-dom about:blank >/dev/null 2>&1 || true
    echo "chromium first start: $(( $(date +%s) - s )) s"; }
fi
tmux -V; gitleaks version
