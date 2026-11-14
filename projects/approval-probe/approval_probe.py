#!/usr/bin/env python3
"""approval-probe: which "don't ask again" rules does Claude Code propose for
credential-bearing shell commands, and what does it write to disk when you accept?

Runs an unmodified Claude Code native binary from npm against an in-process mock of
the Anthropic Messages API. The mock answers every turn with one Bash tool call for
the command under test. Claude Code then asks the host (stdio permission prompt) for
permission and attaches `permission_suggestions`: the rules the "Yes, and don't ask
again" button would save. Optionally the probe accepts them and reads back
.claude/settings.local.json and the global git excludes file.

The command under test is never executed: on accept, the probe approves with the command
replaced by `true`. API traffic goes only to the mock on 127.0.0.1. All secrets in the
corpus are fake strings and all hosts are reserved example names.
"""
import argparse
import base64
import hashlib
import http.server
import io
import json
import os
import select
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = "https://registry.npmjs.org"
NATIVE_PKG = "@anthropic-ai/claude-code-linux-x64"


# ---------------------------------------------------------------- mock Messages API

def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class MockAPI:
    """Minimal streaming Messages API. First turn: one Bash tool_use with self.command.
    Any turn that already carries a tool_result: a plain text answer."""

    def __init__(self):
        self.command = ""
        self.requests = []
        mock = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                mock.requests.append(("GET", self.path))
                self._json({"data": [], "has_more": False})

            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                raw = self.rfile.read(n) if n else b"{}"
                mock.requests.append(("POST", self.path))
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    body = {}
                if "count_tokens" in self.path:
                    return self._json({"input_tokens": 10})
                payload = mock.reply(body)
                if isinstance(payload, dict):
                    return self._json(payload)
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def reply(self, body):
        msgs = body.get("messages", [])
        has_result = any(
            isinstance(m.get("content"), list)
            and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in m["content"])
            for m in msgs
        )
        tools = [t.get("name") for t in body.get("tools", []) if isinstance(t, dict)]
        use_tool = "Bash" in tools and not has_result
        msg = {"id": "msg_mock", "type": "message", "role": "assistant",
               "model": body.get("model", "mock"), "content": [], "stop_reason": None,
               "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}
        if not body.get("stream"):
            msg["content"] = [{"type": "text", "text": "ok"}]
            msg["stop_reason"] = "end_turn"
            return msg
        out = [_sse("message_start", {"type": "message_start", "message": msg})]
        if use_tool:
            out += [
                _sse("content_block_start", {"type": "content_block_start", "index": 0,
                     "content_block": {"type": "tool_use", "id": "toolu_mock1", "name": "Bash", "input": {}}}),
                _sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                     "delta": {"type": "input_json_delta",
                               "partial_json": json.dumps({"command": self.command, "description": "probe"})}}),
            ]
            stop = "tool_use"
        else:
            out += [
                _sse("content_block_start", {"type": "content_block_start", "index": 0,
                     "content_block": {"type": "text", "text": ""}}),
                _sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                     "delta": {"type": "text_delta", "text": "done"}}),
            ]
            stop = "end_turn"
        out += [
            _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
            _sse("message_delta", {"type": "message_delta",
                 "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 5}}),
            _sse("message_stop", {"type": "message_stop"}),
        ]
        return b"".join(out)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


# ---------------------------------------------------------------- classification

def rule_contents(suggestions):
    """Flatten permission_suggestions into the Bash rule strings they would save."""
    out = []
    for s in suggestions or []:
        if not isinstance(s, dict) or s.get("type") != "addRules":
            continue
        for r in s.get("rules", []):
            if r.get("toolName") == "Bash" and r.get("ruleContent") is not None:
                out.append(r["ruleContent"])
    return out


def classify(command, secret, rules):
    """Return (shape, leaks).
    shape: 'none' (no Bash rule proposed), 'verbatim' (a rule equals the command),
           'wildcard' (a rule ends in a '*' or ':*' wildcard), or 'other'.
    leaks: True/False when the case has a secret, None for controls."""
    if not rules:
        shape = "none"
    elif any(r == command for r in rules):
        shape = "verbatim"
    elif any(r.endswith("*") for r in rules):
        shape = "wildcard"
    else:
        shape = "other"
    leaks = None if secret is None else any(secret in r for r in rules)
    return shape, leaks


# ---------------------------------------------------------------- binary fetch

def fetch_binary(version, cache_dir):
    """Download the linux-x64 native build for `version`, verify npm's sha512
    integrity, extract `claude`, and return its path. Cached per version."""
    dest = os.path.join(cache_dir, version)
    exe = os.path.join(dest, "claude")
    if os.path.exists(exe):
        return exe
    meta_url = f"{REGISTRY}/{NATIVE_PKG}/{version}"
    with urllib.request.urlopen(meta_url, timeout=60) as r:
        meta = json.load(r)
    dist = meta["dist"]
    algo, b64 = dist["integrity"].split("-", 1)
    if algo != "sha512":
        raise RuntimeError(f"unexpected integrity algorithm {algo}")
    with urllib.request.urlopen(dist["tarball"], timeout=600) as r:
        blob = r.read()
    if base64.b64encode(hashlib.sha512(blob).digest()).decode() != b64:
        raise RuntimeError(f"integrity mismatch for {NATIVE_PKG}@{version}")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        member = tf.getmember("package/claude")
        with tf.extractfile(member) as src, open(exe, "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.chmod(exe, 0o755)
    with open(os.path.join(dest, "integrity.txt"), "w") as f:
        f.write(dist["integrity"] + "\n")
    return exe


def binary_version(exe):
    p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, DISABLE_AUTOUPDATER="1"))
    return p.stdout.strip()


# ---------------------------------------------------------------- one probe run

def probe(exe, mock, command, accept=False, git_repo=True, pre_tracked=False, timeout=45):
    """Run one command through Claude Code in a fresh HOME and project directory.
    Returns a dict with suggestions and, when accept=True, what was persisted.
    git_repo=False: the project is a plain folder; after the run it is turned into a
    repo to test whether the settings file is ignored then.
    pre_tracked=True: an empty settings.local.json is committed before the run."""
    mock.command = command
    root = tempfile.mkdtemp(prefix="approval-probe-")
    home, proj = os.path.join(root, "home"), os.path.join(root, "proj")
    os.makedirs(home)
    os.makedirs(proj)
    if git_repo:
        subprocess.run(["git", "init", "-q", proj], check=True)
    if pre_tracked:
        os.makedirs(os.path.join(proj, ".claude"))
        with open(os.path.join(proj, ".claude", "settings.local.json"), "w") as f:
            f.write('{"permissions": {"allow": []}}\n')
        genv = dict(os.environ, HOME=home, GIT_AUTHOR_NAME="probe", GIT_AUTHOR_EMAIL="probe@example.com",
                    GIT_COMMITTER_NAME="probe", GIT_COMMITTER_EMAIL="probe@example.com")
        subprocess.run(["git", "add", ".claude/settings.local.json"], cwd=proj, env=genv, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "track settings"], cwd=proj, env=genv, check=True)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ANTHROPIC_", "CLAUDE_")) and k not in ("XDG_CONFIG_HOME",)}
    env.update(HOME=home, ANTHROPIC_BASE_URL=mock.url, ANTHROPIC_API_KEY="mock-not-a-key",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1", DISABLE_AUTOUPDATER="1")
    errlog = open(os.path.join(root, "stderr.log"), "w")
    p = subprocess.Popen([exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                          "--verbose", "--permission-prompt-tool", "stdio"],
                         cwd=proj, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=errlog, text=True)
    p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": "run it"}}) + "\n")
    p.stdin.flush()
    request, events, stderr_tail, turn_done, notices = None, [], None, None, []
    end = time.time() + timeout
    try:
        while time.time() < end:
            ready, _, _ = select.select([p.stdout], [], [], 1)
            if not ready:
                if p.poll() is not None:
                    break
                continue
            line = p.stdout.readline()
            if not line:
                break
            try:
                j = json.loads(line)
            except ValueError:
                continue
            events.append(f"{j.get('type')}:{j.get('subtype', (j.get('request') or {}).get('subtype', ''))}")
            if j.get("type") == "control_request" and (j.get("request") or {}).get("subtype") == "can_use_tool":
                request = j["request"]
                if accept:
                    resp = {"type": "control_response", "response": {
                        "subtype": "success", "request_id": j["request_id"],
                        # Approve, but swap the command for `true`: the rule is saved from
                        # updatedPermissions, and the command under test never executes.
                        "response": {"behavior": "allow",
                                     "updatedInput": {**request.get("input", {}), "command": "true"},
                                     "updatedPermissions": request.get("permission_suggestions") or []}}}
                    p.stdin.write(json.dumps(resp) + "\n")
                    p.stdin.flush()
                    # Keep reading until the turn finishes, so any settings write has happened.
                    turn_done = _wait_for_result(p, end, notices)
                break
        persisted = None
        if accept and request is not None:
            persisted = read_persisted(home, proj)
            persisted["turn_completed"] = turn_done
            persisted["notices"] = notices
            if not git_repo:
                subprocess.run(["git", "init", "-q", proj], check=True)
                persisted["ignored_after_git_init"] = read_persisted(home, proj)["git_check_ignore"]
            if pre_tracked:
                st = subprocess.run(["git", "status", "--porcelain", ".claude/settings.local.json"], cwd=proj,
                                    env=dict(os.environ, HOME=home), capture_output=True, text=True).stdout
                persisted["tracked_file_modified"] = st.strip() != ""
    finally:
        p.kill()
        p.wait(timeout=10)
        for stream in (p.stdin, p.stdout):
            stream.close()
        errlog.close()
        if request is None:
            with open(os.path.join(root, "stderr.log")) as f:
                stderr_tail = f.read()[-600:]
        shutil.rmtree(root, ignore_errors=True)
    suggestions = (request or {}).get("permission_suggestions")
    return {"command": command, "got_request": request is not None, "suggestions": suggestions,
            "rules": rule_contents(suggestions), "persisted": persisted,
            "events": events[:12] if request is None else None, "stderr_tail": stderr_tail}


def _wait_for_result(p, end, notices):
    """Read stream-json lines until the session's `result` event (True) or timeout (False).
    Appends any system notice tagged as a permission-rule message to `notices`."""
    while time.time() < end:
        ready, _, _ = select.select([p.stdout], [], [], 1)
        if not ready:
            if p.poll() is not None:
                return False
            continue
        line = p.stdout.readline()
        if not line:
            return False
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if j.get("type") == "system" and "permission_rule" in str(j.get("tag", "")):
            notices.append({"tag": j.get("tag"), "level": j.get("level"), "content": j.get("content")})
        if j.get("type") == "result":
            time.sleep(0.5)
            return True
    return False


def read_persisted(home, proj):
    settings = os.path.join(proj, ".claude", "settings.local.json")
    allow = None
    if os.path.exists(settings):
        with open(settings) as f:
            allow = ((json.load(f).get("permissions") or {}).get("allow"))
    excludes = None
    for cand in (os.path.join(home, ".config", "git", "ignore"),):
        if os.path.exists(cand):
            with open(cand) as f:
                excludes = f.read()
    repo_gitignore = os.path.exists(os.path.join(proj, ".gitignore"))
    ignored = None
    if os.path.isdir(os.path.join(proj, ".git")) and os.path.exists(settings):
        r = subprocess.run(["git", "check-ignore", "-q", ".claude/settings.local.json"], cwd=proj,
                           env=dict(os.environ, HOME=home))
        ignored = r.returncode == 0
    return {"settings_allow": allow,
            "global_excludes_has_entry": None if excludes is None else "settings.local.json" in excludes,
            "repo_gitignore_created": repo_gitignore,
            "git_check_ignore": ignored}


# ---------------------------------------------------------------- whole-corpus run

def load_corpus(path=os.path.join(HERE, "corpus.json")):
    with open(path) as f:
        return json.load(f)["cases"]


def run_corpus(exe, cases, accept_ids=()):
    results = []
    with MockAPI() as mock:
        for case in cases:
            r = probe(exe, mock, case["command"], accept=case["id"] in accept_ids)
            shape, leaks = classify(case["command"], case["secret"], r["rules"])
            r.update(id=case["id"], origin=case["origin"], has_secret=case["secret"] is not None,
                     shape=shape, leaks=leaks)
            if r["persisted"] and case["secret"]:
                allow = r["persisted"]["settings_allow"] or []
                r["persisted"]["secret_on_disk"] = any(case["secret"] in a for a in allow)
            results.append(r)
            print(f"  {case['id']:<22} {shape:<9} leaks={leaks}", file=sys.stderr)
    return results


# Git workflows from the day-77 entry, each run with a fresh HOME (a "new machine").
WORKFLOWS = [
    {"id": "wf-plain-folder-then-git-init", "command": "git push origin main", "git_repo": False, "pre_tracked": False},
    {"id": "wf-plain-folder-secret", "command": "sshpass -p FAKEPASS123 ssh root@203.0.113.7 uptime",
     "secret": "FAKEPASS123", "git_repo": False, "pre_tracked": False},
    {"id": "wf-tracked-settings-clean-rule", "command": "git push origin main", "git_repo": True, "pre_tracked": True},
    {"id": "wf-tracked-settings-secret", "command": "sshpass -p FAKEPASS123 ssh root@203.0.113.7 uptime",
     "secret": "FAKEPASS123", "git_repo": True, "pre_tracked": True},
]


def run_workflows(exe):
    out = []
    with MockAPI() as mock:
        for w in WORKFLOWS:
            r = probe(exe, mock, w["command"], accept=True, git_repo=w["git_repo"], pre_tracked=w["pre_tracked"])
            per = r["persisted"] or {}
            allow = per.get("settings_allow") or []
            rule_saved = any(x.startswith("Bash(") and x != "Bash()" for x in allow)
            row = {"id": w["id"], "command": w["command"], "rules": r["rules"], "rule_saved": rule_saved,
                   "secret_on_disk": None if not w.get("secret") else any(w["secret"] in x for x in allow),
                   "global_excludes_has_entry": per.get("global_excludes_has_entry"),
                   "ignored_after_git_init": per.get("ignored_after_git_init"),
                   "tracked_file_modified": per.get("tracked_file_modified"),
                   "notices": per.get("notices"),
                   "turn_completed": per.get("turn_completed")}
            out.append(row)
            print(f"  {w['id']:<32} saved={rule_saved} " +
                  " ".join(f"{k}={row[k]}" for k in ("ignored_after_git_init", "tracked_file_modified") if row[k] is not None),
                  file=sys.stderr)
    return out


def summarize(results):
    cred = [r for r in results if r["has_secret"]]
    ctl = [r for r in results if not r["has_secret"]]
    return {"credential_cases": len(cred), "credential_leaks": sum(1 for r in cred if r["leaks"]),
            "credential_verbatim": sum(1 for r in cred if r["shape"] == "verbatim"),
            "controls": len(ctl), "controls_verbatim": sum(1 for r in ctl if r["shape"] == "verbatim"),
            "no_request": sum(1 for r in results if not r["got_request"]),
            "accepted": sum(1 for r in results if r.get("persisted")),
            "accepted_rule_saved": sum(1 for r in results if (r.get("persisted") or {}).get("settings_allow")),
            "secret_on_disk": sum(1 for r in results if (r.get("persisted") or {}).get("secret_on_disk"))}


def diff(a, b):
    """Rows where the proposed rules differ between two result files."""
    rows = []
    bi = {r["id"]: r for r in b["results"]}
    for ra in a["results"]:
        rb = bi.get(ra["id"])
        if rb is None:
            continue
        if ra["rules"] != rb["rules"]:
            rows.append((ra["id"], ra["rules"], rb["rules"], ra["leaks"], rb["leaks"]))
    return rows


def markdown_table(res):
    lines = ["| Case | Command | Proposed rule | Shape | Secret in rule |", "|---|---|---|---|---|"]
    for r in res["results"]:
        rule = "; ".join(r["rules"]) if r["rules"] else "(none)"
        rule = "the whole command, verbatim" if r["shape"] == "verbatim" else f"`{rule}`"
        leak = "n/a" if r["leaks"] is None else ("yes" if r["leaks"] else "no")
        cmd = r["command"].replace("|", "\\|")
        lines.append(f"| {r['id']} | `{cmd}` | {rule} | {r['shape']} | {leak} |")
    return "\n".join(lines)


def _vkey(v):
    return tuple(int(x) for x in v.split("."))


def matrix(docs):
    """Markdown: one row per version, from result files."""
    docs = sorted(docs, key=lambda d: _vkey(d["version"]))
    lines = ["| Version | Secret-bearing rules proposed | ...saved to disk on accept | ...not saved, with a notice "
             "| Clean verbatim rules saved | Plain folder, then `git init`: file ignored | Tracked settings file modified |",
             "|---|---:|---:|---:|---:|---|---|"]
    for d in docs:
        res = d["results"]
        leak = [r for r in res if r["leaks"]]
        saved = [r for r in leak if (r.get("persisted") or {}).get("secret_on_disk")]
        noticed = [r for r in leak if r not in saved and (r.get("persisted") or {}).get("notices")]
        clean = [r for r in res if not r["has_secret"] and r["shape"] == "verbatim"]
        clean_saved = [r for r in clean if (r.get("persisted") or {}).get("settings_allow")]
        wf = {w["id"]: w for w in d.get("workflows", [])}
        ig = wf.get("wf-plain-folder-then-git-init", {}).get("ignored_after_git_init")
        tm = wf.get("wf-tracked-settings-clean-rule", {}).get("tracked_file_modified")
        fmt = lambda x: "n/a" if x is None else ("yes" if x else "no")
        lines.append(f"| {d['version']} | {len(leak)} | {len(saved)} of {len(leak)} "
                     f"| {len(noticed)} of {len(leak) - len(saved)} | {len(clean_saved)} of {len(clean)} "
                     f"| {fmt(ig)} | {fmt(tm)} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="probe one Claude Code version over the corpus")
    r.add_argument("--version", required=True, help="npm version, e.g. 2.1.325")
    r.add_argument("--cache", default=os.path.expanduser("~/.cache/approval-probe"))
    r.add_argument("--accept", default="all",
                   help="'all', or comma-separated case ids to accept and read back from disk ('' for none)")
    r.add_argument("--out", default=None)
    d = sub.add_parser("diff", help="compare two result files")
    d.add_argument("a")
    d.add_argument("b")
    t = sub.add_parser("table", help="markdown table for one result file")
    t.add_argument("file")
    m = sub.add_parser("matrix", help="markdown summary across result files")
    m.add_argument("files", nargs="+")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        exe = fetch_binary(args.version, args.cache)
        reported = binary_version(exe)
        print(f"probing {NATIVE_PKG}@{args.version} ({reported})", file=sys.stderr)
        cases = load_corpus()
        accept = [c["id"] for c in cases] if args.accept == "all" else [x for x in args.accept.split(",") if x]
        results = run_corpus(exe, cases, accept_ids=accept)
        workflows = run_workflows(exe)
        with open(os.path.join(args.cache, args.version, "integrity.txt")) as f:
            integrity = f.read().strip()
        doc = {"package": NATIVE_PKG, "version": args.version, "reported_version": reported,
               "integrity": integrity, "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "summary": summarize(results), "results": results, "workflows": workflows}
        out = args.out or os.path.join(HERE, "results", f"{args.version}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
        print(json.dumps(doc["summary"]))
    elif args.cmd == "diff":
        with open(args.a) as f:
            a = json.load(f)
        with open(args.b) as f:
            b = json.load(f)
        rows = diff(a, b)
        print(f"{a['version']} -> {b['version']}: {len(rows)} case(s) changed")
        for cid, ra, rb, la, lb in rows:
            print(f"- {cid}: {ra} (leaks={la}) -> {rb} (leaks={lb})")
    elif args.cmd == "matrix":
        docs = []
        for path in args.files:
            with open(path) as f:
                docs.append(json.load(f))
        print(matrix(docs))
    elif args.cmd == "table":
        with open(args.file) as f:
            print(markdown_table(json.load(f)))


if __name__ == "__main__":
    main()
