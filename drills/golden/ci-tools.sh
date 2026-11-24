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
tmux -V; gitleaks version
