#!/bin/sh
# The image's apt hook (DPkg::Post-Invoke, as root, after every dpkg run): once apt has installed gh or curl, the
# golden drill's stand-in goes in front of the real one (gh signs in to the stand-in GitHub; curl sends Claude Code's
# installer and the Bot API to the stand-ins and everything else to the real curl, /usr/bin/curl.real). Nothing else.
F=/drill/drills/golden/fakes
for n in gh curl; do
  p="/usr/bin/$n"
  if [ -f "$p" ] && [ ! -L "$p" ]; then
    mv -f "$p" "$p.real" && ln -s "$F/$n" "$p" && echo "$(date -u +%FT%TZ) $p is the stand-in now; the real one: $p.real" >> /var/log/drill-stand-ins.log
  fi
done
exit 0
