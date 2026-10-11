"""Run the transcription stack on one recording as a job. Every stage runs in its own process in an
empty network namespace (unshare --user --map-current-user --net), with the KarmaDue audit hook recording what it actually did.

Idempotency: the job key is sha256(recording) + the component lock. Re-running a finished job with the
same key returns the stored result without re-running any stage or writing new outputs.
Retries: a stage that times out or crashes is retried once; both attempts are counted in time totals.

Usage: pipeline.py <job_dir> <recording> [--timeout STAGE=SECONDS ...] [--env KEY=VAL ...]
Prints the job manifest (JSON) and exits 0 on success, 2 on a structured stage failure.
"""
import hashlib, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("KD_PY", sys.executable)
ORDER = ["decode", "asr", "diarize", "merge", "summarize"]
OUT = {"decode": "decode.json", "asr": "asr.json", "diarize": "diarize.json", "merge": "transcript.json", "summarize": "summary.json"}
DEFAULT_TIMEOUT = {"decode": 60, "asr": 600, "diarize": 300, "merge": 30, "summarize": 600}
RETRYABLE = {"timeout", "crash"}
# Not "unshare -rn": -r maps the caller to root inside the user namespace, and that root keeps
# CAP_DAC_OVERRIDE over the caller's own files, so a revoked (chmod 000) file stays readable.
# --map-current-user keeps the real uid, so capabilities drop on exec and permissions hold.
SANDBOX = os.environ.get("KD_SANDBOX", "unshare --user --map-current-user --net").split()

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def lock():
    p = os.path.join(HERE, "components.lock.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def run_stage(stage, job, args, timeout, extra_env):
    env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "audit"), KD_AUDIT_LOG=os.path.join(job, f"audit.{stage}.jsonl"),
               OMP_WAIT_POLICY="PASSIVE", HF_HUB_OFFLINE="1", **extra_env)
    cmd = [*SANDBOX, PY, os.path.join(HERE, "stages.py"), stage, job, *args]
    t = time.monotonic()
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        _, err = p.communicate(timeout=timeout); rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill(); p.communicate(); rc = None
    wall = time.monotonic() - t
    ru = None
    if rc is None:
        res = {"error": {"stage": stage, "code": "timeout", "detail": f"no result within {timeout} s"}}
        with open(os.path.join(job, OUT[stage]), "w") as f: json.dump(res, f)
    else:
        try: res = json.load(open(os.path.join(job, OUT[stage])))
        except Exception as e: res = {"error": {"stage": stage, "code": "crash", "detail": f"rc={rc}, no readable output ({e}); stderr={err.decode()[-300:]}"}}
    return res, round(wall, 2)

def main(argv):
    job, rec = argv[0], argv[1]
    timeouts, extra_env = dict(DEFAULT_TIMEOUT), {}
    i = 2
    while i < len(argv):
        k, v = argv[i + 1].split("=", 1)
        if argv[i] == "--timeout": timeouts[k] = float(v)
        elif argv[i] == "--env": extra_env[k] = v
        i += 2
    os.makedirs(job, exist_ok=True)
    try: rec_sha = sha(rec)
    except PermissionError as e:
        return {"status": "failed", "error": {"stage": "input", "code": "permission_denied", "detail": str(e)}}
    key = hashlib.sha256(json.dumps({"recording": rec_sha, "lock": lock(), "env": extra_env}, sort_keys=True).encode()).hexdigest()
    mpath = os.path.join(job, "manifest.json")
    if os.path.exists(mpath):
        m = json.load(open(mpath))
        if m.get("job_key") == key and m.get("status") == "succeeded":
            m["replayed"] = True; return m
    m = {"job_key": key, "recording": os.path.abspath(rec), "recording_sha256": rec_sha, "stages": [], "retries": 0, "replayed": False}
    t0 = time.monotonic()
    for st in ORDER:
        args = [os.path.abspath(rec)] if st == "decode" else []
        for attempt in (1, 2):
            res, wall = run_stage(st, job, args, timeouts[st], extra_env)
            err = res.get("error")
            m["stages"].append({"stage": st, "attempt": attempt, "wall_s": wall, "error": err, **res.get("_measure", {})})
            if not err or err["code"] not in RETRYABLE or attempt == 2: break
            m["retries"] += 1
        if err:
            m.update(status="failed", error=err, total_wall_s=round(time.monotonic() - t0, 2))
            break
    else:
        m.update(status="succeeded", total_wall_s=round(time.monotonic() - t0, 2))
    m["total_cpu_s"] = round(sum(s.get("cpu_s", 0) for s in m["stages"]), 2)
    m["peak_rss_mib"] = max((s.get("peak_rss_mib", 0) for s in m["stages"]), default=0)
    m["cost_usd"] = 0.0  # all components local and free; compute time is in total_wall_s
    json.dump(m, open(mpath, "w"), indent=1)
    return m

if __name__ == "__main__":
    m = main(sys.argv[1:]); print(json.dumps(m, indent=1)); sys.exit(0 if m.get("status") == "succeeded" else 2)
