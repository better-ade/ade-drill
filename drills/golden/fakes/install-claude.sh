#!/bin/bash
# The stand-in for https://claude.ai/install.sh: puts the Claude Code stand-in in ~/.local/bin, as the real installer does.
set -eu; mkdir -p "$HOME/.local/bin"; cp "${DRILL_CLAUDE_SRC:?}" "$HOME/.local/bin/claude"; chmod +x "$HOME/.local/bin/claude"
echo "Claude Code successfully installed (stand-in)"
