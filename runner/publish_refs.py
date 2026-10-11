#!/usr/bin/env python3
"""Turn reference-runner output (runs.jsonl) into one kd_reference_publish batch (SQL file).

One recipe per package + exact version; one run per reference environment. Environments are written coarse
(os, arch, runtime major.minor, client) and the server re-coarsens them anyway. Only tool names, counts and the
tool-list hash are published, never the full schemas or anything from the box beyond the coarse environment.
Usage: publish_refs.py runs.jsonl out.json run_url part
GitHub Actions copy: writes the runner-ingest body (kind reference_runs) instead of SQL.
"""
import json, re, sys
from collections import OrderedDict

ENV_OS = {"Linux (Debian 13)": "linux"}

def coarse(r):
    rt = r["environment"]["runtime"]  # "Node.js 22.23 / Python 3.12"
    node, py = re.search(r"Node\.js ([\d.]+)", rt).group(1), re.search(r"Python ([\d.]+)", rt).group(1)
    runtime = f"node {node}" if r["reg"] == "npm" else f"python {py}"
    return {"os": "linux", "arch": r["environment"]["arch"], "runtime": runtime, "client": "KarmaDue reference runner"}

def fix_for(r):
    fc, tail = r.get("failure_class"), (r.get("stderr_tail") or "")
    m = re.search(r"required: \{[^}]*node: '([^']+)'", tail)
    if fc == "runtime_version":
        if m: return f"needs Node.js {m.group(1)}", f"Run it on Node.js {m.group(1)}."
        m = re.search(r"depends on Python([<>=!.\d]+)", tail)
        if m: return f"needs Python {m.group(1)}", f"Run it on Python {m.group(1)}."
        return "runtime version not supported", "Use the runtime version the package declares."
    if fc == "needs_credentials":
        keys = sorted(set(re.findall(r"\b([A-Z][A-Z0-9_]{3,}(?:_KEY|_TOKEN|_ID|_URL|_DSN|_SECRET))\b", tail)))
        return "exits without credentials", ("Set " + ", ".join(keys) + " before launch." if keys else "Supply the credentials or DSN the package documents before launch.")
    if fc == "entry_point":
        m = re.search(r"Use `([^`]+)` instead", tail)
        return "executable name differs from package name", (f"Launch with `{m.group(1)}`." if m else "Launch the executable the package actually provides.")
    if fc == "needs_browser": return "waits for interactive browser sign-in", "Not usable headless: complete the OAuth sign-in in a browser first."
    if fc == "needs_arguments":
        m = re.search(r"Install it with: uv\s+│?\s*add '([^']+)'", tail) or re.search(r"'([\w-]+\[mcp\])'", tail)
        return "MCP server needs an extra or arguments", (f"Install `{m.group(1)}`." if m else "Pass the arguments or extras the package documents.")
    if fc == "timeout": return "no initialize reply within the start timeout", "Expect a slow or blocked start; check its docs for a non-interactive mode."
    m = re.search(r"(ModuleNotFoundError: .{0,160}|could not determine executable to run)", tail)
    return "exited before initialize", "No fix known yet." + (" Error seen: " + m.group(1).strip() if m else "")

def main():
    src, out = sys.argv[1], sys.argv[2]
    run_url, part = sys.argv[3], sys.argv[4]
    rows = [json.loads(l) for l in open(src) if l.strip()]
    rec = OrderedDict()
    for r in rows:
        if not r.get("resource_id"): continue
        k = (r["pkg"], r["version"])
        g = rec.setdefault(k, {"subject_id": r["resource_id"], "version": r["version"], "runs": [], "fails": OrderedDict(), "first": r})
        env = coarse(r)
        details = {"run_key": f'{r["reg"]}:{r["pkg"]}@{r["version"]}:{r["env"]}:{r["at"]}', "package": f'{r["reg"]}:{r["pkg"]}',
                   "launch_line": r.get("launch_line"), "init_ms": r.get("init_ms"), "tools_list_ms": r.get("tools_list_ms"), "total_ms": r.get("total_ms"),
                   "protocol": r.get("protocol"), "server_info": r.get("server_info"), "reference_env": r["env"]}
        if r["result"] == "worked":
            details.update(tool_count=r.get("tools_count"), tools_sha256=r.get("tools_sha256"), tool_names=[t["name"] for t in r.get("tools") or []])
            snippet = f'initialize ok ({r.get("protocol")}), tools/list returned {r.get("tools_count")} tools'
        else:
            details.update(error=r.get("error"))
            snippet = (r.get("stderr_tail") or r.get("error") or "")[-1200:]
            details.update(failure_detail=r.get("failure_class"))
            what, fix = fix_for(r)
            g["fails"].setdefault(what, {"symptom": what, "fix": fix, "seen_in": []})["seen_in"].append(env["runtime"])
        g["runs"].append({"result": r["result"], "environment": env, "failure_class": r.get("failure_class") if r["result"] == "failed" else None,
                          "output_snippet": snippet, "note": f'KarmaDue reference runner, {r["env"]}', "at": r["at"], "details": details})
    recipes = []
    for (pkg, ver), g in rec.items():
        r0 = g["first"]; worked = [x for x in g["runs"] if x["result"] == "worked"]
        reg_url = f"https://www.npmjs.com/package/{pkg}/v/{ver}" if r0["reg"] == "npm" else f"https://pypi.org/project/{pkg}/{ver}/"
        recipes.append({
            "subject_id": g["subject_id"], "version": ver, "server_key": re.sub(r"^@[^/]+/", "", pkg)[:30],
            "title": f'Start {pkg} {ver} over stdio' + ("" if worked else " (did not start in KarmaDue reference runs)"),
            "environment": g["runs"][0]["environment"],
            "credentials": r0.get("required_settings") or [],
            "steps": [{"step": 1, "text": "Launch: " + (r0.get("launch_line") or "")},
                      {"step": 2, "text": "Send initialize, then tools/list, over stdio."},
                      {"step": 3, "text": "Reproducible: started in " + str(len(worked)) + " of " + str(len(g["runs"])) + " KarmaDue reference environments." if worked
                                          else "Not reproduced: did not start in any KarmaDue reference environment. See common failures."}],
            "expected_output": (f"initialize succeeds and tools/list returns {worked[0]['details']['tool_count']} tools (sha256 {worked[0]['details']['tools_sha256'][:12]}…)"
                                if worked else "Did not start on the reference runner; expected output is from the package docs only."),
            "common_failures": [{"symptom": f["symptom"] + " (" + ", ".join(sorted(set(f["seen_in"]))) + ")", "fix": f["fix"]} for f in g["fails"].values()],
            "source_url": reg_url, "runs": g["runs"]})
    body = json.dumps({"kind": "reference_runs", "run_url": run_url, "part": part, "recipes": recipes}, ensure_ascii=False)
    open(out, "w").write(body)
    print(len(recipes), "recipes,", sum(len(r["runs"]) for r in recipes), "runs,", len(body), "bytes")

if __name__ == "__main__":
    main()
