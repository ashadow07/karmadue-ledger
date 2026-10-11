#!/usr/bin/env python3
"""KarmaDue reference runs (HOSTED_APPLY_79): start each top-50 MCP server in 2-3 reference environments on KarmaDue's box and
record what happened. Read-only towards the server: initialize, notifications/initialized, tools/list. No tool is ever called.

Each run happens inside bubblewrap: the box's home and workspace are hidden (empty tmpfs), the process gets a fresh HOME and /tmp,
a clean environment (no tokens), and network access for the package download. Required credentials named by the registry entry are
set to the placeholder value "kd-placeholder" so servers that only check presence can start; no API call is made with them.

Usage: run_reference.py tools.json out.json [--envs a,b,c] [--only pkg] [--jobs 6]
"""
import hashlib, json, os, re, select, shutil, subprocess, sys, tempfile, time, urllib.request, concurrent.futures as cf, datetime, platform

HERE = os.path.dirname(os.path.abspath(__file__))
RT = os.environ.get("KD_RT", "/workspace/env79/rt")
CACHE = os.environ.get("KD_RUN_CACHE", "/workspace/env79/runcache")
UA = {"User-Agent": "KarmaDue-reference-runs/1.0 (+https://karmadue.expo.app/docs/environments.md)"}
OS_LABEL = "Linux (Debian 13)"
ENVS = {
    "ref-a": {"node": "/usr/bin", "python": "3.13", "label": {"os": OS_LABEL, "arch": "x64", "runtime": "Node.js 20.19 / Python 3.13", "node": "20.19", "python": "3.13"}},
    "ref-b": {"node": f"{RT}/node22/bin", "python": "3.12", "label": {"os": OS_LABEL, "arch": "x64", "runtime": "Node.js 22.23 / Python 3.12", "node": "22.23", "python": "3.12"}},
    "ref-c": {"node": f"{RT}/node24/bin", "python": "3.11", "label": {"os": OS_LABEL, "arch": "x64", "runtime": "Node.js 24.21 / Python 3.11", "node": "24.21", "python": "3.11"}},
}
CLIENT = "KarmaDue reference runner (raw MCP stdio)"
# GitHub Actions mode (KD_GH=1): one environment per matrix job, runtimes from actions/setup-node and setup-python, no bwrap
# (each job is a fresh GitHub-hosted VM with no secrets and a read-only token). The output format is unchanged.
GH = os.environ.get("KD_GH") == "1"
if GH:
    _node = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip().lstrip("v")
    _py = os.environ["KD_PY"]; _nmm = ".".join(_node.split(".")[:2])
    OS_LABEL = "Linux (Ubuntu 24.04, GitHub Actions)"
    ENVS = {os.environ["KD_ENV"]: {"node": os.path.dirname(shutil.which("node")), "python": _py,
            "label": {"os": OS_LABEL, "arch": "x64", "runtime": f"Node.js {_nmm} / Python {_py}", "node": _nmm, "python": _py}}}
PLACEHOLDER = "kd-placeholder"

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r: return json.load(r)
    except Exception: return None

def latest(reg, pkg):
    if reg == "npm":
        d = get(f"https://registry.npmjs.org/{pkg.replace('/', '%2f')}/latest"); return d and d.get("version"), (d or {}).get("engines")
    d = get(f"https://pypi.org/pypi/{pkg}/json"); return d and d["info"]["version"], {"python": d["info"].get("requires_python")} if d else None

def launch(tool, ver, env_key, exe=None):
    """The exact launch line (argv) for this tool, version and environment."""
    args = list(tool.get("args") or [])
    if tool["reg"] == "npm":
        return ["npx", "-y", f"{tool['pkg']}@{ver}"] + args
    py = ENVS[env_key]["python"]
    if exe and exe != tool["pkg"]:
        return ["uvx", "--python", py, "--from", f"{tool['pkg']}=={ver}", exe] + args
    return ["uvx", "--python", py, f"{tool['pkg']}=={ver}"] + args

def rpc_session(argv, env, cwd, timeout):
    """Start the server and run initialize + tools/list over stdio. Returns a dict with timings and output."""
    t0 = time.time()
    p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd, start_new_session=True)
    out_buf, err_buf = b"", b""
    closed = set()
    def send(obj): p.stdin.write((json.dumps(obj) + "\n").encode()); p.stdin.flush()
    def wait_for(rid, deadline):
        nonlocal out_buf, err_buf
        while time.time() < deadline:
            fds = [f for f in (p.stdout, p.stderr) if f not in closed]
            if not fds: return None
            r, _, _ = select.select(fds, [], [], 0.5)
            for fh in r:
                chunk = os.read(fh.fileno(), 65536)
                if not chunk: closed.add(fh); continue
                if fh is p.stdout: out_buf += chunk
                else: err_buf += chunk
            while b"\n" in out_buf:
                line, out_buf = out_buf.split(b"\n", 1)
                try: msg = json.loads(line)
                except Exception: continue
                if isinstance(msg, dict) and msg.get("id") == rid: return msg
            if p.poll() is not None and not r: return None
        return "timeout"
    res = {}
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "karmadue-reference-runner", "version": "1.0"}}})
        init = wait_for(1, t0 + timeout)
        res["init_ms"] = int((time.time() - t0) * 1000)
        if init == "timeout": res["error"] = "timeout_initialize"
        elif init is None: res["error"] = "exited_before_initialize"
        elif "error" in init: res["error"] = "initialize_error"; res["rpc_error"] = init["error"]
        else:
            res["server_info"] = init["result"].get("serverInfo"); res["protocol"] = init["result"].get("protocolVersion")
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            t1 = time.time()
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tl = wait_for(2, time.time() + 60)
            res["tools_list_ms"] = int((time.time() - t1) * 1000)
            if tl in (None, "timeout"): res["error"] = "no_tools_list"
            elif "error" in tl: res["error"] = "tools_list_error"; res["rpc_error"] = tl["error"]
            else: res["tools"] = tl["result"].get("tools", [])
    except (BrokenPipeError, OSError) as e:
        res["error"] = res.get("error") or "exited_before_initialize"
    finally:
        try: os.killpg(p.pid, 9)
        except Exception: pass
        try: _, e2 = p.communicate(timeout=5); err_buf += e2 or b""
        except Exception: pass
    res["exit_code"] = p.returncode
    res["stderr_tail"] = err_buf.decode("utf8", "replace")[-1500:]
    res["total_ms"] = int((time.time() - t0) * 1000)
    return res

REDACT = [(re.compile(r"/tmp/kdrun-[A-Za-z0-9_]+"), "$SANDBOX"), (re.compile(r"(?i)(token|key|secret|password)=\S+"), r"\1=[redacted]")]
def clean(s):
    for rx, rep in REDACT: s = rx.sub(rep, s)
    return s

def classify(res, tool):
    if res.get("tools") is not None: return "worked", None
    e = (res.get("stderr_tail") or "").lower()
    if re.search(r"not provided by package|executable .* not found|no executables are provided", e): return "failed", "entry_point"
    if re.search(r"(api[_ ]?key|token|credential|unauthori[sz]ed|401|403|missing required env|environment variable)", e): return "failed", "needs_credentials"
    if re.search(r"engine|unsupported engine|requires node|node\.js v?\d+ (or|is) |syntaxerror: unexpected token|requires-python|python>=|no solution found", e): return "failed", "runtime_version"
    if re.search(r"econnrefused|connection refused|could not connect|no such host|getaddrinfo", e): return "failed", "needs_service"
    if re.search(r"windows|win32|darwin only|macos only|not supported on linux|platform", e): return "failed", "platform"
    if re.search(r"browser|chrom(e|ium)|playwright install|executable doesn't exist", e): return "failed", "needs_browser"
    if res.get("error", "").startswith("timeout"): return "failed", "timeout"
    if re.search(r"usage:|required argument|missing argument|error: the following arguments", e): return "failed", "needs_arguments"
    return "failed", "other"

def run_one(tool, env_key, timeout=int(os.environ.get("KD_TIMEOUT", "240"))):
    E = ENVS[env_key]
    ver, engines = (tool["version"], tool.get("engines")) if tool.get("version") else latest(tool["reg"], tool["pkg"])
    scratch = tempfile.mkdtemp(prefix="kdrun-", dir="/tmp")
    os.makedirs(f"{scratch}/home", exist_ok=True); os.makedirs(f"{scratch}/work", exist_ok=True)
    for d in tool.get("make_dirs", []): os.makedirs(f"{scratch}/work/{d}", exist_ok=True)
    if tool.get("git_repo"): subprocess.run(["git", "init", "-q", f"{scratch}/work/repo"], check=False)
    npm_cache = f"{CACHE}/{env_key}/npm"; uv_cache = f"{CACHE}/uv"; os.makedirs(npm_cache, exist_ok=True); os.makedirs(uv_cache, exist_ok=True)
    env = {"PATH": os.environ["PATH"] if GH else f"{E['node']}:/usr/local/bin:/usr/bin:/bin", "HOME": f"{scratch}/home", "TMPDIR": f"{scratch}/tmp", "LANG": "C.UTF-8",
           "npm_config_cache": npm_cache, "npm_config_update_notifier": "false", "UV_CACHE_DIR": uv_cache, "UV_PYTHON_INSTALL_DIR": f"{RT}/py",
           "UV_PYTHON_PREFERENCE": "only-managed" if E["python"] != "3.13" else "system", "CI": "1", "NO_COLOR": "1"}
    os.makedirs(env["TMPDIR"], exist_ok=True)
    for name in tool.get("required_env", []): env[name] = PLACEHOLDER
    for k, v in (tool.get("set_env") or {}).items(): env[k] = v.replace("$WORK", f"{scratch}/work")
    if E["python"] == "3.13" and not GH: env["UV_PYTHON"] = "/usr/bin/python3.13"
    if GH: env["UV_PYTHON"] = E["python"]; env["UV_PYTHON_PREFERENCE"] = "only-system"; env.pop("UV_PYTHON_INSTALL_DIR", None)
    def bw(argv):
        if GH: return argv
        return ["bwrap", "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/workspace", "--tmpfs", "/root", "--tmpfs", "/tmp",
                "--bind", scratch, scratch, "--ro-bind", RT, RT, "--bind", CACHE, CACHE, "--dev", "/dev", "--proc", "/proc",
                "--unshare-pid", "--die-with-parent", "--chdir", f"{scratch}/work", "--"] + argv
    t_args = [a.replace("$WORK", f"{scratch}/work") for a in (tool.get("args") or [])]
    tool2 = dict(tool, args=t_args)
    argv = launch(tool2, ver, env_key, tool.get("exe"))
    res = rpc_session(bw(argv), env, f"{scratch}/work", timeout)
    # uvx: the package's command has a different name. Retry once with the one it names (still no tool calls).
    if tool["reg"] == "pypi" and res.get("tools") is None and not tool.get("exe"):
        m = re.search(r"provides the following executables?:\s*(.+)", res.get("stderr_tail", ""), re.I)
        if m:
            exes = [x.strip(" -*,\n") for x in re.split(r"[\s,]+", m.group(1)) if x.strip(" -*,\n")]
            pick = next((x for x in exes if "mcp" in x.lower()), exes[0] if exes else None)
            if pick:
                tool2["exe"] = pick; argv = launch(tool2, ver, env_key, pick)
                res = rpc_session(bw(argv), env, f"{scratch}/work", timeout); res["exe_retry"] = pick
    shutil.rmtree(scratch, ignore_errors=True)
    result, fclass = classify(res, tool)
    tools = res.pop("tools", None)
    rec = {"pkg": tool["pkg"], "reg": tool["reg"], "resource_id": tool["resource_id"], "version": ver, "engines": engines, "env": env_key,
           "environment": {"os": E["label"]["os"], "arch": E["label"]["arch"], "runtime": E["label"]["runtime"], "client": CLIENT},
           "launch_line": " ".join(a if a == a.strip() and " " not in a else json.dumps(a) for a in argv).replace(scratch + "/work", "$WORKDIR"),
           "required_settings": tool.get("required_env", []), "result": result, "failure_class": fclass,
           "server_info": res.get("server_info"), "protocol": res.get("protocol"), "error": res.get("error"), "rpc_error": res.get("rpc_error"),
           "init_ms": res.get("init_ms"), "tools_list_ms": res.get("tools_list_ms"), "total_ms": res.get("total_ms"), "exit_code": res.get("exit_code"),
           "stderr_tail": clean(res.get("stderr_tail", ""))[-800:], "exe": tool2.get("exe"),
           "tools_count": len(tools) if tools is not None else None,
           "tools_sha256": hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest() if tools is not None else None,
           "tools": tools, "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return rec

def main():
    tools = json.load(open(sys.argv[1])); out = sys.argv[2]
    envs = (sys.argv[sys.argv.index("--envs") + 1].split(",") if "--envs" in sys.argv else list(ENVS))
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 6
    if only: tools = [t for t in tools if t["pkg"] == only]
    if "--skip-credentials" in sys.argv:
        skipped = [t["pkg"] for t in tools if t.get("required_env")]
        tools = [t for t in tools if not t.get("required_env")]
        print("skipped (need credentials):", ", ".join(skipped), file=sys.stderr)
    # resolve each version once so all environments run the same release
    for t in tools:
        if not t.get("version"): t["version"], t["engines"] = latest(t["reg"], t["pkg"])
    work = [(t, e) for e in envs for t in tools if t.get("version")]
    recs = []
    with cf.ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(run_one, t, e): (t["pkg"], e) for t, e in work}
        for f in cf.as_completed(futs):
            try: r = f.result()
            except Exception as e: print("ERR", futs[f], e, file=sys.stderr); continue
            recs.append(r); open(out + ".jsonl", "a").write(json.dumps(r) + "\n"); print(f"{r['env']} {r['reg']}:{r['pkg']}@{r['version']} {r['result']} {r['failure_class'] or ''} tools={r['tools_count']} {r['total_ms']}ms", flush=True)
    json.dump({"runner": "kd-reference-run@1", "host": "github-actions" if GH else "karmadue-box", "envs": {k: ENVS[k]["label"] for k in envs},
               "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "runs": recs}, open(out, "w"), indent=1)

if __name__ == "__main__": main()
