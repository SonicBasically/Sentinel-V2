"""Send Slack messages from Sentinel, from chat or voice.

One Slack bot token does everything: SENTINEL_SLACK_TOKEN (xoxb-...), read from the environment
or ~/.config/sentinel/.env. Optional SENTINEL_SLACK_OWNER_ID (your Slack member ID) makes
"send me a message" work.

try_slack(text) returns {"handled", "ok", "reply"} when the text asks to send a Slack message,
or None when it does not. Text that never mentions Slack (or a #channel) is never sent.
Bot scopes needed: chat:write, channels:read, groups:read, users:read, im:write.
The bot can only post to a channel it is in: type /invite @Sentinel in that channel first.
"""
import json
import os
import re
import time

import httpx

API = "https://slack.com/api/"
ENV_FILE = os.path.expanduser("~/.config/sentinel/.env")
CACHE_SECS = 600
MAX_BODY = 3000

_cache = {}


class SlackError(Exception):
    pass


def _env_value(name):
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _call(method, token, **params):
    data = {k: v for k, v in params.items() if v != ""}
    try:
        r = httpx.post(API + method, headers={"Authorization": "Bearer " + token}, data=data, timeout=15)
        body = r.json()
    except ValueError:
        raise SlackError("bad_response")
    if not body.get("ok"):
        err = body.get("error", "unknown_error")
        print("[Slack error] %s: %s" % (method, body))
        if err == "missing_scope":
            err = "missing_scope:" + str(body.get("needed", "unknown"))
        raise SlackError(err)
    return body


def _cached(key, fetch):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECS:
        return hit[1]
    val = fetch()
    _cache[key] = (time.time(), val)
    return val


def _all_channels(token):
    """List of (channel_id, {normalized names}) for channels the bot can see."""
    def fetch():
        out, cursor = [], ""
        for _ in range(10):
            d = _call("conversations.list", token, types="public_channel",
                      exclude_archived="true", limit="200", cursor=cursor)
            out += [(c["id"], {_norm(c.get("name"))}) for c in d.get("channels", [])]
            cursor = (d.get("response_metadata") or {}).get("next_cursor", "")
            if not cursor:
                break
        return out
    return _cached("channels", fetch)


def _all_users(token):
    """List of (user_id, {normalized names}) for everyone in the workspace, bots included."""
    def fetch():
        out, cursor = [], ""
        for _ in range(10):
            d = _call("users.list", token, limit="200", cursor=cursor)
            for u in d.get("members", []):
                if u.get("deleted") or u.get("id") == "USLACKBOT":
                    continue
                prof = u.get("profile") or {}
                raw = (u.get("name"), u.get("real_name"), prof.get("display_name"), prof.get("real_name"))
                out.append((u["id"], {_norm(n) for n in raw if n}))
            cursor = (d.get("response_metadata") or {}).get("next_cursor", "")
            if not cursor:
                break
        return out
    return _cached("users", fetch)


def _match(options, key, exact):
    if exact:
        hits = [v for v, names in options if key in names]
    else:
        hits = [v for v, names in options if any(key in n for n in names)] if len(key) >= 3 else []
    if len(hits) > 1:
        raise SlackError("ambiguous")
    return hits[0] if hits else None


def _open_dm(token, user_id):
    return _call("conversations.open", token, users=user_id)["channel"]["id"]


def _resolve(token, target):
    """Return (channel_id, spoken_label). Raises SlackError when nothing clear matches."""
    key = _norm(target)
    if not key:
        raise SlackError("no_target")
    if key in ("me", "myself"):
        owner = _env_value("SENTINEL_SLACK_OWNER_ID")
        if not owner:
            raise SlackError("no_owner")
        return _open_dm(token, owner), "you"
    chans = _all_channels(token)
    if target.startswith("#"):
        cid = _match(chans, key, True) or _match(chans, key, False)
        if not cid:
            raise SlackError("no_channel")
        return cid, target.lstrip("#")
    cid = _match(chans, key, True)
    if cid:
        return cid, target
    users = _all_users(token)
    uid = _match(users, key, True)
    if uid:
        return _open_dm(token, uid), target
    cid = _match(chans, key, False)
    if cid:
        return cid, target
    uid = _match(users, key, False)
    if uid:
        return _open_dm(token, uid), target
    raise SlackError("no_target")


_HELP = {
    "not_in_channel": "I'm not in that channel yet. Type /invite @Sentinel in it, then ask me again.",
    "channel_not_found": "I couldn't find that channel.",
    "no_channel": "I couldn't find a channel with that name.",
    "no_target": "I couldn't find anyone or any channel with that name on Slack.",
    "no_owner": "I don't know your Slack ID yet. Add SENTINEL_SLACK_OWNER_ID to ~/.config/sentinel/.env.",
    "ambiguous": "More than one Slack name matches that. Say the full name.",
    "invalid_auth": "Slack rejected the token. Check SENTINEL_SLACK_TOKEN.",
    "not_authed": "Slack rejected the token. Check SENTINEL_SLACK_TOKEN.",
    "token_revoked": "Slack rejected the token. Check SENTINEL_SLACK_TOKEN.",
    "missing_scope": "The Slack app is missing a permission. Add the scope it names, then reinstall it.",
    "is_archived": "That channel is archived.",
    "restricted_action": "Slack's rules don't let the bot do that here.",
    "msg_too_long": "That message is too long for Slack.",
    "bad_response": "Slack sent back something I couldn't read.",
}


def _explain(code):
    if code.startswith("missing_scope"):
        needed = code.split(":", 1)[1] if ":" in code else "unknown"
        return ("Slack needs the %s permission. Add it under OAuth and Permissions, "
                "reinstall the app, then try again." % needed)
    return _HELP.get(code, "Slack said no: %s." % code)


def _res(reply, ok=True):
    return {"handled": True, "ok": ok, "reply": reply}


_PREFIX = r"^(?:hey |ok |okay )?(?:sentinel[,:]? )?(?:please )?(?:can you |could you |would you )?(?:please )?"
_SEND = r"(?:send|post|message|msg|tell|dm|text|write|ask)"
_SEP = r"(?:\bsaying\b|\bthat\b(?!')|\bwith\b|:|,)"
_PATTERNS = [
    # "send a slack message to sam saying hi", "send sam a message on slack that hi", "post in #general saying hi"
    re.compile(_PREFIX + _SEND + r"\s+(?:a |an |the )?(?:slack )?(?:message |msg |dm )?(?:to |in |into |on )?"
               r"(?!(?:message|msg|dm|slack)\b)(?P<target>.+?)(?: on slack| in slack| via slack)?\s*" + _SEP + r"\s*(?P<body>.+)$", re.I),
    # "slack sam hi there" with a separator: "slack message to sam saying hi"
    re.compile(r"^slack\s+(?:message |msg |dm )?(?:to |in |into )?(?P<target>.+?)\s*" + _SEP + r"\s*(?P<body>.+)$", re.I),
    # "send a slack message saying hi to sam"
    re.compile(r"^(?:send|post|message|msg|tell|dm)\s+(?:a |an )?slack\s+(?:message |msg |dm )?" + _SEP +
               r"\s*(?P<body>.+?)\s+(?:to|in)\s+(?P<target>[^.!?]+?)[.!?]?$", re.I),
]


def _clean_target(t):
    t = (t or "").strip().strip(".,!?\"'").strip()
    t = re.sub(r"^channel\s+", "#", t, flags=re.I)
    t = re.sub(r"^(?:(?:to|in|into|on|the|a|an|slack|message|msg|dm)\s+)+", "", t, flags=re.I)
    t = re.sub(r"\s+(?:on|in|via) slack$", "", t, flags=re.I)
    t = re.sub(r"(?:^|\s+)(?:a |an |the )?(?:slack )?(?:message|msg|dm|direct message|channel)$", "", t, flags=re.I)
    return t.strip()


def parse_send(text):
    """Return (target, body) if the text asks to send a Slack message, else None."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return None
    for pat in _PATTERNS:
        m = pat.match(raw)
        if not m:
            continue
        target = _clean_target(m.group("target"))
        body = m.group("body").strip().strip("\"\u201c\u201d").strip()[:MAX_BODY]
        if not target or not body:
            continue
        if not (re.search(r"\bslack\b", raw, re.I) or target.startswith("#")):
            return None
        return target, body
    return None


_pending = None  # draft waiting on the user: {"stage", "channel", "label", "target", "body", "at"}
PENDING_SECS = 120
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
SLACK_MODEL = _env_value("SENTINEL_SLACK_MODEL") or "mistral:7b-instruct-v0.3-q4_K_M"

_YES = {"yes", "yeah", "yep", "yup", "sure", "send", "send it", "go", "go ahead", "do it", "ok", "okay",
        "confirm", "yes send it", "send it now", "yes please", "please send it"}
_NO = {"no", "nope", "cancel", "never mind", "nevermind", "forget it", "dont", "dont send", "dont send it",
       "stop", "no thanks", "do not send"}

_EXTRACT = (
    "You extract requests to post a Slack message. Reply with JSON only: "
    '{"send": true or false, "target": "channel or person name", "body": "the message text"}. '
    "Set send to true only if the user clearly asks to post a Slack message. "
    "Copy the target and the message exactly as the user wrote them. Never invent a target or a message. "
    "If the user did not name a target or did not say what to post, leave that field empty. "
    "Message: %s"
)

NOT_SET = ("Slack isn't set up yet. Add SENTINEL_SLACK_TOKEN to ~/.config/sentinel/.env "
           "and restart Sentinel.")
OFFLINE = "I couldn't reach Slack. Check the internet connection."


def _plain(text):
    t = (text or "").lower().replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def _in_user_text(part, raw):
    """True only when every word of `part` was actually typed by the user."""
    words = set(_plain(raw).split())
    part_words = _plain(part).split()
    return bool(part_words) and all(w in words for w in part_words)


def _ask_model(text):
    """Let the local model read the request. Returns (target, body), (\"\", \"\") when it wants a
    Slack send but gave no target, or None when the text is not a Slack send."""
    try:
        r = httpx.post(OLLAMA_URL, json={"model": SLACK_MODEL, "prompt": _EXTRACT % text, "stream": False,
                                         "format": "json", "options": {"temperature": 0}}, timeout=45)
        d = json.loads(r.json().get("response") or "{}")
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get("send"):
        return None
    target = _clean_target(str(d.get("target") or ""))
    body = str(d.get("body") or "").strip().strip("\"\u201c\u201d").strip()[:MAX_BODY]
    # only accept what the user actually typed; anything else is asked for
    if target and not _in_user_text(target.lstrip("#"), text):
        target = ""
    if body and not _in_user_text(body, text):
        body = ""
    return target, body


def _confirm_text(body, label):
    return "Post '%s' to %s on Slack, yes or no?" % (body, label)


def _start(target, body):
    """Find the channel or person now, so a bad name is caught before anything is posted."""
    global _pending
    token = _env_value("SENTINEL_SLACK_TOKEN")
    if not token:
        return _res(NOT_SET, False)
    if not target:
        _pending = {"stage": "target", "channel": None, "label": "", "target": "", "body": body,
                    "at": time.time()}
        return _res("Who should I send it to?")
    try:
        channel, label = _resolve(token, target)
    except SlackError as e:
        _pending = None
        return _res(_explain(str(e)), False)
    except httpx.HTTPError:
        _pending = None
        return _res(OFFLINE, False)
    if not body:
        _pending = {"stage": "body", "channel": channel, "label": label, "target": target, "body": "",
                    "at": time.time()}
        return _res("What should I say to %s?" % label)
    _pending = {"stage": "confirm", "channel": channel, "label": label, "target": target, "body": body,
                "at": time.time()}
    return _res(_confirm_text(body, label))


def _send(channel, label, body):
    token = _env_value("SENTINEL_SLACK_TOKEN")
    try:
        _call("chat.postMessage", token, channel=channel, text=body)
    except SlackError as e:
        return _res(_explain(str(e)), False)
    except httpx.HTTPError:
        return _res(OFFLINE, False)
    return _res("Sent to %s on Slack." % label)


def _answer_pending(raw):
    """Handle a reply to a draft. Returns a result, or None when the text is not an answer to it."""
    global _pending
    p = _pending
    if time.time() - p["at"] > PENDING_SECS:
        _pending = None
        return None
    t = _plain(raw)
    if t in _NO:
        _pending = None
        return _res("Okay, I won't send anything.")
    if p["stage"] == "target":
        return _start(_clean_target(raw), p["body"])
    if p["stage"] == "body":
        return _start(p["target"], raw.strip()[:MAX_BODY])
    if t in _YES:
        _pending = None
        return _send(p["channel"], p["label"], p["body"])
    _pending = None  # anything else drops the draft and is handled as a normal request
    return None


def try_slack(text):
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return None
    if _pending:
        ans = _answer_pending(raw)
        if ans is not None:
            return ans
    parsed = parse_send(raw)
    if parsed:
        return _start(*parsed)
    if re.search(r"\bslack\b", raw, re.I):
        found = _ask_model(raw)
        if found:
            return _start(*found)
    return None
