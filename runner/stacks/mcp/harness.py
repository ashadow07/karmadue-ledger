"""Minimal MCP stdio client for KarmaDue stack tests. Every tool call is logged (name, args, wall ms, isError), so
records judge what tools actually did, not what anything said. Servers run under bwrap with no network, npm/uv offline."""
import json, os, select, signal, subprocess, time

RT = os.environ.get("KD_RT", "/workspace/env79/rt"); CACHE = os.environ.get("KD_RUN_CACHE", "/workspace/env79/runcache")
NODE = {"22": f"{RT}/node22/bin", "24": f"{RT}/node24/bin"}
if os.environ.get("KD_NODE_BIN"): NODE = {k: os.environ["KD_NODE_BIN"] for k in ("22", "24")}  # GitHub Actions: setup-node's node

class McpError(Exception):
    def __init__(self, code, detail): super().__init__(f"{code}: {detail}"); self.code, self.detail = code, detail

class Server:
    def __init__(self, argv, scratch, node="22", extra_env=None, binds=(), label=""):
        self.label = label or argv[-1]; self.log = []; self.buf = b""; self.stderr = b""
        env = {"PATH": f"{NODE[node]}:/usr/local/bin:/usr/bin:/bin", "HOME": f"{scratch}/home", "LANG": "C.UTF-8",
               "npm_config_cache": f"{CACHE}/ref-b/npm" if node == "22" else f"{CACHE}/ref-c/npm", "npm_config_offline": "true",
               "npm_config_update_notifier": "false", "UV_CACHE_DIR": f"{CACHE}/uv", "UV_OFFLINE": "1", "UV_PYTHON": os.environ.get("KD_UV_PYTHON", "/usr/bin/python3.13"), "NO_COLOR": "1"}
        if os.environ.get("KD_EXTRA_PATH"): env["PATH"] = env["PATH"] + ":" + os.environ["KD_EXTRA_PATH"]
        env.update(extra_env or {})
        os.makedirs(f"{scratch}/home", exist_ok=True)
        cmd = ["bwrap", "--ro-bind", "/", "/", "--tmpfs", "/home", "--tmpfs", "/tmp", "--bind", scratch, scratch,
               "--bind", CACHE, CACHE, "--dev", "/dev", "--proc", "/proc", "--unshare-net", "--unshare-pid", "--die-with-parent",
               "--chdir", scratch]
        for b in binds: cmd += ["--bind", b, b]
        self.t0 = time.monotonic()
        try:
            self.p = subprocess.Popen(cmd + ["--"] + argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except FileNotFoundError as e:
            raise McpError("unavailable", str(e))
        self.id = 0

    def _read(self, deadline):
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0: raise McpError("timeout", "no reply before deadline")
            r, _, _ = select.select([self.p.stdout, self.p.stderr], [], [], min(left, 0.5))
            for fh in r:
                chunk = os.read(fh.fileno(), 65536)
                if fh is self.p.stderr: self.stderr += chunk; continue
                if not chunk: raise McpError("unavailable", "server exited: " + self.stderr.decode(errors="replace")[-300:])
                self.buf += chunk
            if self.p.poll() is not None and not r and b"\n" not in self.buf:
                raise McpError("unavailable", "server exited: " + self.stderr.decode(errors="replace")[-300:])
        line, self.buf = self.buf.split(b"\n", 1)
        return line

    def request(self, method, params, timeout=20):
        self.id += 1; rid = self.id
        self.p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n").encode()); self.p.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            raw = self._read(deadline)
            try: msg = json.loads(raw)
            except ValueError: raise McpError("malformed_output", raw[:200].decode(errors="replace"))
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0": raise McpError("malformed_output", raw[:200].decode(errors="replace"))
            if msg.get("id") == rid:
                if "error" in msg: raise McpError("rpc_error", json.dumps(msg["error"])[:300])
                return msg["result"]

    def init(self, timeout=60):
        r = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "kd-stack-runner", "version": "1"}}, timeout)
        self.p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'); self.p.stdin.flush()
        self.info = r.get("serverInfo"); return r

    def call(self, name, args, timeout=20):
        t = time.monotonic(); err = None; res = None
        try:
            res = self.request("tools/call", {"name": name, "arguments": args}, timeout)
        except McpError as e:
            err = e
        entry = {"server": self.label, "tool": name, "args": args, "ms": round((time.monotonic() - t) * 1000),
                 "is_error": bool(res and res.get("isError")), "failure": err.code if err else None}
        self.log.append(entry)
        if err: raise err
        return res

    def stop(self):
        try: self.p.kill()
        except Exception: pass
        try: self.p.wait(5)
        except Exception: pass

def text(res):
    return "\n".join(c.get("text", "") for c in (res or {}).get("content", []) if c.get("type") == "text")

def snapshot(root):
    out = {}
    for d, _, fs in os.walk(root):
        if "/.git" in d + "/": continue
        for f in fs:
            p = os.path.join(d, f)
            try: out[os.path.relpath(p, root)] = os.stat(p).st_size
            except OSError: pass
    return out

def tree_signal(pid, sig):
    """Signal a process and every descendant (the server runs a few levels under bwrap)."""
    kids = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try: kids.setdefault(int(open(f"/proc/{d}/stat").read().rsplit(")", 1)[1].split()[1]), []).append(int(d))
            except Exception: pass
    todo, seen = [pid], []
    while todo:
        x = todo.pop(); seen.append(x); todo += kids.get(x, [])
    for x in seen:
        try: os.kill(x, sig)
        except Exception: pass
    return len(seen)
