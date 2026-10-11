#!/usr/bin/env python3
"""Publish the finalized transcription test record as a stack record (kd_stack_record_upsert).
Usage: publish_stack.py test_record_final.json out.json run_url part  (GitHub Actions copy: writes the runner-ingest body, kind stack)
Box paths are replaced with $PILOT/$WORK so the record carries no local inventory."""
import hashlib, json, os, sys

rec = json.load(open(sys.argv[1]))
c = rec["components"]
comps = [
    {"role": "recording", "name": "Pilot 1 sample + synthetic meetings", "version": "pilot1+synth-v1"},
    {"role": "decoder", "name": "ffmpeg", "version": os.environ.get("KD_FFMPEG_VERSION", c["decoder"]["version"])},
    {"role": "transcription runtime", "name": "pywhispercpp", "version": c["transcription"]["version"], "resource_id": "kd:res:github:ggml-org/whisper.cpp", "gap_asks": True},
    {"role": "transcription model", "name": "whisper " + c["transcription"]["model"], "version": c["transcription"]["model_sha256"][:16]},
    {"role": "speaker processing", "name": "sherpa-onnx", "version": c["diarization"]["version"], "resource_id": "kd:res:github:k2-fsa/sherpa-onnx"},
    {"role": "speaker models", "name": "sherpa-onnx segmentation+embedding", "version": c["diarization"]["segmentation_sha256"][:8] + "+" + c["diarization"]["embedding_sha256"][:8]},
    {"role": "summary runtime", "name": "llama-cpp-python", "version": c["summary"]["version"], "resource_id": "kd:res:github:ggml-org/llama.cpp"},
    {"role": "summary model", "name": c["summary"]["model"], "version": c["summary"]["model_sha256"][:16]},
    {"role": "sandbox", "name": "unshare --user --map-current-user --net", "version": os.environ.get("KD_UNSHARE_VERSION", "util-linux 2.41.5")},
    {"role": "acceptance check", "name": "KarmaDue transcription acceptance", "version": hashlib.sha256(json.dumps(rec["acceptance_criteria"], sort_keys=True).encode()).hexdigest()[:12]},
]
h = hashlib.sha256(json.dumps([{k: x[k] for k in ("role", "name", "version")} for x in comps], sort_keys=True).encode()).hexdigest()
body = json.dumps(rec)
for a, b in ((os.environ.get("KD_PILOT", "/nonexistent"), "$PILOT/sample"), (os.environ.get("KD_WORK", "/nonexistent"), "$WORK"), ("/workspace/karmadue/pilot-transcription", "$PILOT"), ("/workspace/env79/stack1", "$WORK"), ("/workspace/karmadue/app", "$REPO"), ("/workspace", "$BOX")):
    body = body.replace(a, b)
rec = json.loads(body)
v = rec["verdict"]
p = {"id": rec["stack"], "title": "Local transcription: ffmpeg → whisper.cpp small.en → sherpa-onnx speakers → Qwen2.5-1.5B summary → acceptance",
     "components": comps, "components_hash": h, "verdict": v["result"],
     "verdict_detail": {"failed_criteria": v["failed_criteria"], "plain": v["plain"]},
     "record": rec, "evidence_label": "karmadue_test_runner", "reassessment_triggers": rec["reassessment_triggers"],
     "tested_environments": rec["tested_environments"], "untested_environments": rec["untested_environments"], "recorded_at": rec["recorded_at"]}
s = json.dumps({"kind": "stack", "run_url": sys.argv[3], "part": sys.argv[4], "stack": p}, ensure_ascii=False)
open(sys.argv[2], "w").write(s)
print(h, len(s))
