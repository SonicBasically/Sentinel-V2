"""Checks for the API-key lockout in server.verify_key: loopback is never locked out, remote clients still are.
No network is used. Usage: .venv/bin/python tools/test_auth_lockout.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["SENTINEL_API_KEY"] = "test-key-not-real"
import server
from fastapi import HTTPException

GOOD = "test-key-not-real"
bad = 0


class _C:
    def __init__(self, host): self.host = host


class _R:
    def __init__(self, host): self.client = _C(host)


def call(host, key):
    try:
        server.verify_key(_R(host), key)
        return 200
    except HTTPException as e:
        return e.status_code


def check(label, got, want):
    global bad
    if got != want:
        bad += 1
        print("FAIL  %s -> %r (wanted %r)" % (label, got, want))


for host in ("127.0.0.1", "::1"):
    check("%s: 12 wrong keys are all plain 401" % host, [call(host, "nope") for _ in range(12)], [401] * 12)
    check("%s: right key still works after that" % host, call(host, GOOD), 200)
    check("%s: empty key is 401" % host, call(host, ""), 401)

remote = "100.64.0.9"
check("remote: first 5 wrong keys are 401", [call(remote, "nope") for _ in range(5)], [401] * 5)
check("remote: 6th request with the RIGHT key is locked (429)", call(remote, GOOD), 429)
check("remote: other clients are not affected", call("100.64.0.10", GOOD), 200)

other = "100.64.0.11"
for _ in range(3):
    call(other, "nope")
check("remote: a good request resets the counter", call(other, GOOD), 200)
check("remote: 3 more wrong keys after the reset are still 401", [call(other, "nope") for _ in range(3)], [401] * 3)

print("auth lockout: %s" % ("all checks passed" if not bad else "%d FAILED" % bad))
sys.exit(1 if bad else 0)
