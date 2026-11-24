# The golden path by hand, once per release

The drill (`bash drills/golden.sh`) runs this path with a stand-in for every account. This list is the same path with
your real accounts: what no stand-in can show (the real sign-ins, the real model, the Mac's Keychain and launchd, your
phone). Run it on a fresh Mac user or a fresh ADE Computer, with a throwaway bot and a throwaway hub name. Tick each
line; write what you saw beside any that fails, and the release waits.

Before: the drill is green for this release (Actions → ci or nightly → golden path), and you have read its
`report.md` (the artifact).

| # | Do | Expect | Seen |
|---|---|---|---|
| 1 | `curl -fsSL https://raw.githubusercontent.com/better-ade/ade-cli/main/install.sh \| bash` | `installed ade <this release> to ~/.local/bin/ade`; the tools it lacks are named, and installed only after your yes | [ ] |
| 2 | `ade setup` (the guide) | the six steps listed with their state | [ ] |
| 3 | Step 1 | Claude Code installed by its own installer, after your yes | [ ] |
| 4 | Step 2: your Claude account | your browser opens Claude's own sign-in; `ade` shows no key and stores none | [ ] |
| 5 | Step 3: GitHub | `gh`'s one-time code, typed at github.com/login/device; no token asked or shown | [ ] |
| 6 | Step 4: a hub name, a kind of teammate, who it works for, your name | a private repository on your GitHub with the hub's first version (open it on github.com: no key, no token in it) | [ ] |
| 7 | Step 4: your Claude account for the main agent and for focus agents | `anthropic: ready (Ns)`: one real, tiny request | [ ] |
| 8 | Step 6: yes, then the token of a bot you made with @BotFather | the token is not echoed; "checked: the token is in the hub's key store" (on a Mac: your login Keychain asks once) | [ ] |
| 9 | Second terminal: `cd ~/hubs/<hub> && bin/chat start`; message the bot; `/telegram:access pair <code>`; `/telegram:access policy allowlist` | each "checked:" line in the guide; the bot's test message arrives on your phone and your reply ends the test | [ ] |
| 10 | The guide's last lines | "The chat now runs in auto mode"; "All set"; on your phone, the auto-mode notice, once | [ ] |
| 11 | `ade setup --check` | `telegram: on (auto)` | [ ] |
| 12 | From another Telegram account, message the bot | no answer; nothing happens in the hub | [ ] |
| 13 | Restart the machine (or log out and in) | `ade chat status`: running, locked to you, auto: launchd (or systemd) brought the session back | [ ] |
| 14 | `ade project add <a repo of yours with one failing test>` (from the release that has it) | `projects/<name>` in the hub; its ACCESS.md names your checkout and no credential | [ ] |
| 15 | On Telegram: "fix the failing test in <name>" | the main agent answers without anything asked at a terminal; a focus agent opens as a tab (`ade ui`) | [ ] |
| 16 | Wait | the fix is in your checkout (`git diff`); the reviewer, not the builder, ran the verification command; its real output is in the tab | [ ] |
| 17 | Your phone | "Done", and a picture of the proof (from the release that has `ade shot`) | [ ] |
| 18 | `ade chat logs`, the hub's journal, your shell history | no token, no key, no Telegram id | [ ] |
| 19 | Clean up: `ade chat stop`; delete the throwaway hub repository on GitHub and the bot in @BotFather | nothing of the run is left signed in | [ ] |

What the drill cannot tell you and this run can: whether the real model takes the route the scripted one takes at 15
to 17 (stories G6 and G7), how long each step takes with real services, and what the Keychain and launchd ask.
