#!/usr/bin/env python3
"""Publish an MCP reference-stack record (repo-facts-v1 or memory-roundtrip-v1).
GitHub Actions copy. Usage: publish_mcp_stack.py record.json out.json run_url part  (writes the runner-ingest body, kind stack)"""
import hashlib, json, os, re, sys
rec = json.load(open(sys.argv[1]))
RES = "kd:res:github:modelcontextprotocol/servers"
if rec["stack"] == "repo-facts-v1":
    title = "Repo facts: mcp-server-git history + server-filesystem reads → facts.json → acceptance"
    comps = [{"role": "history", "name": "mcp-server-git", "version": "2026.10.10", "resource_id": RES},
             {"role": "file access", "name": "@modelcontextprotocol/server-filesystem", "version": "1.0.0", "resource_id": RES, "gap_asks": True}]
    triggers = ["a new version of mcp-server-git or server-filesystem (re-run this stack only; needs re-check, not failed)", "git_log output format changes (the handoff parses Commit:/Message:)",
                "directory_tree output schema changes", "a new OS, arch or runtime not in tested_environments", "the acceptance criteria change"]
    known = [{"symptom": "a non-JSON line on stdout before the first message", "behavior": "strict clients (this runner) stop with malformed_output; MCP requires stdout to carry only MCP messages", "evidence_label": "KarmaDue test runner"}]
else:
    title = "Memory round trip: server-memory write → restart → read_graph → acceptance"
    comps = [{"role": "memory store", "name": "@modelcontextprotocol/server-memory", "version": "1.0.0", "resource_id": RES, "gap_asks": True}]
    triggers = ["a new version of server-memory (re-run this stack only; needs re-check, not failed)", "MEMORY_FILE_PATH format changes", "a new OS, arch or runtime not in tested_environments", "the acceptance criteria change"]
    known = [{"symptom": "a corrupt line in memory.jsonl", "behavior": "read_graph returns the other records and no error: the bad line is skipped silently", "fix": "validate the memory file yourself (each line must be JSON) before trusting a read; keep backups", "evidence_label": "KarmaDue test runner"}]
comps.append({"role": "sandbox", "name": "bwrap --unshare-net", "version": os.environ.get("KD_BWRAP_VERSION", "0.12.0")})
comps.append({"role": "acceptance check", "name": "KarmaDue " + rec["stack"] + " criteria", "version": hashlib.sha256(json.dumps(rec["criteria"], sort_keys=True).encode()).hexdigest()[:12]})
rec["known_failures"] = known
rec["reassessment_triggers"] = triggers
rec["tested_environments"] = [{"os": "linux", "arch": "x86_64", "runtime": "node " + os.environ.get("KD_NODE_MM", "22.23"), "host": os.environ.get("KD_HOST_LABEL", "KarmaDue box (Debian 13)")}]
rec["untested_environments"] = [{"os": "macos", "arch": "arm64", "runtime": "node 22"}, {"os": "windows", "arch": "x86_64", "runtime": "node 22"}]
rec["evidence_labels"] = "Every result here is KarmaDue test runner. Nothing is a submitted claim or independently reproduced yet."
body = re.sub(r"/tmp/kdstack-[a-z]+-[a-z0-9_]+", "$SCRATCH", json.dumps(rec)); rec = json.loads(body)
h = hashlib.sha256(json.dumps([{k: c[k] for k in ("role", "name", "version")} for c in comps], sort_keys=True).encode()).hexdigest()
p = {"id": rec["stack"], "title": title, "components": comps, "components_hash": h, "verdict": rec["verdict"]["result"],
     "verdict_detail": {"failed_criteria": rec["verdict"]["failed_criteria"], "plain": rec["verdict"]["plain"]}, "record": rec,
     "evidence_label": "karmadue_test_runner", "reassessment_triggers": triggers, "tested_environments": rec["tested_environments"],
     "untested_environments": rec["untested_environments"], "recorded_at": rec["recorded_at"]}
s = json.dumps({"kind": "stack", "run_url": sys.argv[3], "part": sys.argv[4], "stack": p}, ensure_ascii=False)
open(sys.argv[2], "w").write(s); print(rec["stack"], p["verdict"], len(s))
