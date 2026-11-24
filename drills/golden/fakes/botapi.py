#!/usr/bin/env python3
"""A stand-in for Telegram's Bot API and for the owner's phone, on 127.0.0.1 only.

botapi.py <state folder> <bot token> <owner id>
  Writes <state folder>/port once it listens. Everything the bot sends is appended to <state folder>/sent.jsonl
  (one JSON object per line; a photo or document is saved under <state folder>/files/ and named there), and what the
  owner's phone shows, both ways and in order, to <state folder>/phone.jsonl.

The Bot API side (the token in the path must be the one given, else 401, as Telegram answers):
  /bot<token>/getUpdates   offset, timeout: the queued updates; an offset confirms (drops) the older ones
  /bot<token>/sendMessage  chat_id, text (form or JSON)
  /bot<token>/sendPhoto, /bot<token>/sendDocument   multipart: chat_id, caption, the file
  any other method         ok, recorded
The phone side (the drill plays the owner; never part of Telegram's API):
  POST /phone/say          JSON {"text": ..., "from": <id, default the owner>}: the owner (or a stranger) writes to the bot
  The owner answers a message that starts with "Test from the" by itself (the hub's bin/chat test waits for a reply).
Every Bot API method called is appended to <state folder>/methods.log (its name only).

Relay (story D4, the real-bot mode): with DRILL_TG_RELAY_TOKEN and DRILL_TG_RELAY_CHAT in the environment, everything
the bot sends to the owner is also sent, as it is, to that chat through the real Bot API (DRILL_TG_RELAY_API, default
https://api.telegram.org), and the row records "relayed": "ok" or why not. Only sendMessage, sendPhoto and
sendDocument are relayed: the relay never calls getUpdates or setWebhook, so a hub live on the same bot keeps its
messages. The real token is read once, taken out of the environment, and never written anywhere.
"""
import json, os, secrets, sys, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE, TOKEN, OWNER = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.join(STATE, "files"), exist_ok=True)
LOCK = threading.Condition()
UPDATES = []          # queued updates, oldest first
NEXT = [1000]         # the next update_id
MSG = [1]
RELAY_TOKEN = os.environ.pop("DRILL_TG_RELAY_TOKEN", ""); RELAY_CHAT = os.environ.pop("DRILL_TG_RELAY_CHAT", "")
RELAY_API = os.environ.pop("DRILL_TG_RELAY_API", "") or "https://api.telegram.org"
RELAYED = ("sendMessage", "sendPhoto", "sendDocument")


def relay(method, p, names):
    """the same message to the real chat: "ok", or why not (never the token: Telegram's own description at most)"""
    if method not in RELAYED: return "not relayed: %s" % method
    url = "%s/bot%s/%s" % (RELAY_API, RELAY_TOKEN, method)
    if method == "sendMessage":
        body = json.dumps({"chat_id": RELAY_CHAT, "text": str(p.get("text", ""))[:4096]}).encode(); ctype = "application/json"
    else:
        kind = "photo" if method == "sendPhoto" else "document"; b = "drill" + secrets.token_hex(8)
        parts = [("chat_id", None, RELAY_CHAT.encode()), ("caption", None, str(p.get("caption", "")).encode()),
                 (kind, names.get(kind, kind), p.get(kind) if isinstance(p.get(kind), bytes) else b"")]
        body = b"".join(b"--%s\r\nContent-Disposition: form-data; name=\"%s\"%s\r\n\r\n%s\r\n" % (
            b.encode(), n.encode(), (b'; filename="%s"' % os.path.basename(f).encode()) if f else b"", v) for n, f, v in parts) + b"--%s--\r\n" % b.encode()
        ctype = "multipart/form-data; boundary=" + b
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": ctype}), timeout=20) as r:
            return "ok" if json.load(r).get("ok") else "failed: not ok"
    except urllib.error.HTTPError as e:
        try: why = str(json.load(e).get("description", ""))[:120]
        except ValueError: why = ""
        return "failed: %d %s" % (e.code, why.replace(RELAY_TOKEN, "<token>") if RELAY_TOKEN else why)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return "failed: %s" % e.__class__.__name__


def record(row, name="sent.jsonl"):
    with open(os.path.join(STATE, name), "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def phone_says(text, sender=None):
    sender = int(sender or OWNER)
    record({"who": "you" if str(sender) == OWNER else "another account", "text": text}, "phone.jsonl")
    with LOCK:
        u = {"update_id": NEXT[0], "message": {"message_id": MSG[0], "date": int(time.time()), "text": text,
             "from": {"id": sender, "is_bot": False, "first_name": "Drill"},
             "chat": {"id": sender, "type": "private"}}}
        NEXT[0] += 1; MSG[0] += 1; UPDATES.append(u); LOCK.notify_all()


def multipart(body, ctype):
    """the fields of a multipart/form-data body: {name: bytes}, and {name: file name} for the files"""
    b = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
    fields, names = {}, {}
    for part in body.split(b"--" + b):
        if b"\r\n\r\n" not in part: continue
        head, _, data = part.partition(b"\r\n\r\n")
        data = data[:-2] if data.endswith(b"\r\n") else data
        disp = [l for l in head.decode("utf-8", "replace").split("\r\n") if l.lower().startswith("content-disposition")]
        if not disp: continue
        attrs = dict(p.strip().split("=", 1) for p in disp[0].split(";")[1:] if "=" in p)
        name = attrs.get("name", "").strip('"')
        fields[name] = data
        if "filename" in attrs: names[name] = attrs["filename"].strip('"')
    return fields, names


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def params(self):
        url = urllib.parse.urlsplit(self.path)
        p = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n) if n else b""
        ctype = self.headers.get("Content-Type", ""); names = {}
        if ctype.startswith("application/json") and body:
            try: p.update(json.loads(body.decode()))
            except ValueError: pass
        elif ctype.startswith("multipart/form-data"):
            fields, names = multipart(body, ctype)
            for k, v in fields.items(): p[k] = v if k in names else v.decode("utf-8", "replace")
        elif body:
            p.update({k: v[-1] for k, v in urllib.parse.parse_qs(body.decode("utf-8", "replace")).items()})
        return url.path, p, names

    def do_GET(self): self.handle_any()
    def do_POST(self): self.handle_any()

    def handle_any(self):
        path, p, names = self.params()
        if path == "/phone/say":
            phone_says(str(p.get("text", "")), p.get("from")); return self.reply(200, {"ok": True})
        if not path.startswith("/bot"): return self.reply(404, {"ok": False, "description": "Not Found"})
        token, _, method = path[4:].partition("/")
        if token != TOKEN: return self.reply(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        with open(os.path.join(STATE, "methods.log"), "a") as f: f.write(method + "\n")
        if method == "getUpdates":
            off = int(p.get("offset") or 0); wait = min(float(p.get("timeout") or 0), 2.0); end = time.time() + wait
            with LOCK:
                if off: UPDATES[:] = [u for u in UPDATES if u["update_id"] >= off]
                while not UPDATES and time.time() < end: LOCK.wait(end - time.time())
                return self.reply(200, {"ok": True, "result": list(UPDATES)})
        row = {"method": method, "chat_id": str(p.get("chat_id", ""))}
        if method == "sendMessage":
            row["text"] = str(p.get("text", ""))
            if "reply_markup" in p: row["buttons"] = True
            if row["text"].startswith("Test from the"): threading.Timer(0.5, phone_says, ("got it",)).start()
        elif method in ("sendPhoto", "sendDocument"):
            kind = "photo" if method == "sendPhoto" else "document"
            data = p.get(kind) if isinstance(p.get(kind), bytes) else b""
            name = "%d-%s" % (int(time.time() * 1000), os.path.basename(names.get(kind, kind)))
            with open(os.path.join(STATE, "files", name), "wb") as f: f.write(data)
            row.update(file=name, bytes=len(data), png=data[:8] == b"\x89PNG\r\n\x1a\n", caption=str(p.get("caption", "")))
        if RELAY_TOKEN and RELAY_CHAT and row["chat_id"] == OWNER: row["relayed"] = relay(method, p, names)
        record(row)
        if row["chat_id"] == OWNER:   # what the owner's phone shows
            record({"who": "your bot", "text": row.get("text") or "[a picture] " + row.get("caption", ""), "buttons": row.get("buttons", False)}, "phone.jsonl")
        with LOCK: MSG[0] += 1; mid = MSG[0]
        self.reply(200, {"ok": True, "result": {"message_id": mid}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
with open(os.path.join(STATE, "port.tmp"), "w") as f: f.write(str(srv.server_address[1]))
os.replace(os.path.join(STATE, "port.tmp"), os.path.join(STATE, "port"))
srv.serve_forever()
