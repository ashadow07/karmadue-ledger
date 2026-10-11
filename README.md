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

## Bitcoin timestamps (OpenTimestamps)

Each day the workflow also runs `ots stamp heads/<date>.json`, which writes `heads/<date>.json.ots`. Only the SHA-256 digest of the
head file leaves the runner, sent to the public OpenTimestamps calendars; the calendars commit it into a Bitcoin transaction.
A new proof is pending for a few hours; later runs call `ots upgrade` until the proof carries a Bitcoin block attestation.

Verify one yourself (needs `pip install opentimestamps-client` and, for full verification, a Bitcoin node or a block explorer):

    ots info heads/2026-10-11.json.ots
    ots verify heads/2026-10-11.json.ots

This is a timestamp, nothing more: there is no token, no wallet and no on-chain credit. Credit for contributions stays in KarmaDue's
signed log; the Bitcoin anchor only proves the log head existed by a given block.

## Limits

An anchor proves the log had this head on this date and was not rewritten afterwards. It does not prove any event is true, and it
says nothing about content that never entered the log.

## Daily reference runs (GitHub Actions, public logs)

`.github/workflows/reference-runs.yml` re-runs KarmaDue's reference runs every day at 07:23 UTC (and on demand): the top-50 MCP
servers in `runner/tools50.json` are started in three runtime setups (Node 20 / Python 3.13, Node 22 / Python 3.12, Node 24 /
Python 3.11) and sent only `initialize` and `tools/list` (no tool is called); servers that need credentials are skipped. The three
reference stacks (`repo-facts-v1`, `memory-roundtrip-v1`, `local-transcription-v1`) run against their written acceptance criteria.
Raw logs and JSON results are committed to `results/<date>/run-<id>/`.

Results are posted to KarmaDue's `runner-ingest` route, signed with Ed25519 (`runner/post_ingest.sh`; the private key is the
`KD_RUNNER_KEY` Actions secret, readable only by the final job, which runs no tested code). KarmaDue labels them
"KarmaDue test runner (GitHub Actions, public logs)" with the run URL. Runs are appended, never overwritten; a run whose result
or tool list differs from the previous one is marked needs re-check, and a stack whose verdict or components change is set to
needs re-check with the new record kept in history until reviewed.
