#!/usr/bin/env bash
# Sign a JSON body with the Ed25519 key in $KD_RUNNER_KEY (PEM) and POST it to KarmaDue's runner-ingest route.
# Usage: post_ingest.sh body.json   (prints the response; exits non-zero on HTTP error)
set -euo pipefail
BODY="$1"; URL="${KD_INGEST_URL:-https://ogogoizwsfaduzehkshb.supabase.co/functions/v1/runner-ingest}"
: "${KD_RUNNER_KEY:?KD_RUNNER_KEY is not set}"
K=$(mktemp); trap 'rm -f "$K" "$K.msg"' EXIT; printf '%s\n' "$KD_RUNNER_KEY" > "$K"
TS=$(date +%s); DIG=$(sha256sum "$BODY" | cut -d' ' -f1)
printf 'kd-runner-ingest-v1\n%s\n%s' "$TS" "$DIG" > "$K.msg"
SIG=$(openssl pkeyutl -sign -inkey "$K" -rawin -in "$K.msg" | base64 -w0)
curl -sS --fail-with-body -X POST "$URL" -H "Content-Type: application/json" -H "x-kd-key-id: kd-runner-2026-10" \
  -H "x-kd-timestamp: $TS" -H "x-kd-signature: $SIG" --data-binary @"$BODY"
echo
