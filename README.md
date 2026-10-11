# karmadue-ledger

Public, append-only daily anchors of KarmaDue's hash-chained event log.

Every event KarmaDue records (checks, reports, revocations, forum frames...) is a row in one append-only log, and each row carries
`prev_hash`, the hash of the row before it. Once a day KarmaDue signs the head of that chain: the latest event number (`seq`)
and its `row_hash`. This repository keeps a copy of each daily head, committed by a GitHub Actions workflow, so GitHub's commit
history is an independent timestamp. If KarmaDue ever rewrote an earlier event, every later hash would change and would no longer
match the heads recorded here.

The files hold only hashes, counts, timestamps and signatures. No names, no account ids, no content.

## Files

`heads/YYYY-MM-DD.json` (UTC date), one per day:

| field | meaning |
| --- | --- |
| `recipe` | `kd-log-head-v1` |
| `anchored_on` | UTC date of the anchor |
| `seq` | number of the latest event in the log at anchor time |
| `row_hash` | SHA-256 (hex) of that event's row; it links back through `prev_hash` |
| `signed_text` | the exact bytes signed: `kd-log-head-v1`, the date, `seq`, `row_hash`, joined by LF |
| `signature` | Ed25519 signature over the UTF-8 bytes of `signed_text`, base64url |
| `key_id` | `kd-passport-1` |

## Verify it yourself

1. Fetch the current head: https://karmadue.expo.app/.well-known/kd-log-head.json
   (live: https://ogogoizwsfaduzehkshb.supabase.co/functions/v1/public-api/.well-known/kd-log-head.json).
2. Fetch the public key `kd-passport-1` from https://karmadue.expo.app/.well-known/jwks.json (OKP / Ed25519, `x` is base64url).
3. Rebuild `signed_text` from the fields and check the Ed25519 signature: `python3 scripts/verify_head.py heads/2026-10-11.json`
   (needs `pip install cryptography`).
4. Compare chain head and count: `seq` must never go down from one day to the next (`python3 scripts/check_order.py`),
   and today's head must match what the live endpoint served for that date.
5. A committed anchor file must never change. `git log -p heads/` shows any edit.

## Automation

`.github/workflows/daily-anchor.yml` runs daily at 06:17 UTC (and on manual dispatch). It fetches the public head, keeps only the
fields above, verifies the signature and the ordering, and commits `heads/<date>.json`. It uses no secrets: only public URLs and the
workflow's own `GITHUB_TOKEN`.

## Limits

An anchor proves the log had this head on this date and was not rewritten afterwards. It does not prove any event is true, and it
says nothing about content that never entered the log.
