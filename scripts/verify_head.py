#!/usr/bin/env python3
"""Verify one KarmaDue log-head anchor (kd-log-head-v1) against the published JWKS. Usage: verify_head.py heads/YYYY-MM-DD.json [jwks_url]
Checks: signed_text is exactly the recipe lines rebuilt from the fields, and the Ed25519 signature is valid for key kd-passport-1."""
import base64, json, sys, urllib.request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
path = sys.argv[1]; jwks_url = sys.argv[2] if len(sys.argv) > 2 else "https://karmadue.expo.app/.well-known/jwks.json"
h = json.load(open(path))
expected = "\n".join(["kd-log-head-v1", h["anchored_on"], str(h["seq"]), h["row_hash"]])
assert h["signed_text"] == expected, "signed_text does not match the fields"
req = urllib.request.Request(jwks_url, headers={"User-Agent": "karmadue-ledger-verify"})
key = next(k for k in json.load(urllib.request.urlopen(req, timeout=30))["keys"] if k.get("kid") == h["key_id"])
pub = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(key["x"] + "=" * (-len(key["x"]) % 4)))
pub.verify(base64.urlsafe_b64decode(h["signature"] + "=" * (-len(h["signature"]) % 4)), h["signed_text"].encode("utf-8"))
print(f"OK {h['anchored_on']} seq={h['seq']} row_hash={h['row_hash']}")
